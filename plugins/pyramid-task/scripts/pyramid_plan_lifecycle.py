"""P3B plan_lifecycle boundary; no facade imports.

Existing control flow and canonical/history publication protocol are retained.
"""
from __future__ import annotations
from pathlib import Path
from pyramid_assurance_contracts import RUNTIME_VERSION
from pyramid_assurance_io import detect_repository_mode
from pyramid_errors import PyramidError
from pyramid_files import _file_sha256
from pyramid_files import load_json
from pyramid_files import project_lock
from pyramid_files import project_paths
from pyramid_files import require_supported_project
from pyramid_files import write_json
from pyramid_history import HistoryError
from pyramid_history import history_chronicles
from pyramid_history import history_contains_plan
from pyramid_history import record_intent_chronicle
from pyramid_plan_bundle import PlanPorts, default_ports
from pyramid_plan_bundle import _archive_identifier
from pyramid_plan_bundle import _copy_current_snapshot
from pyramid_plan_bundle import _initialize_current
from pyramid_plan_bundle import _purge_current
from pyramid_plan_bundle import _resolve_archive
from pyramid_plan_commands import create_project
from pyramid_state import active_claims
from pyramid_state import canonical_sha256
from pyramid_state import check_expected_version
from pyramid_state import context_identity
from pyramid_state import default_lifecycle
from pyramid_state import lifecycle_state
from pyramid_state import lifecycle_status
from pyramid_state import validate_state
from pyramid_storage import load_assurance_bundle
from pyramid_validation import validate_plan
from typing import Any
import copy
import shutil


def archive_project(
    project: str | Path,
    actor: str,
    reason: str,
    expected_version: int | dict[str, Any] | None = None,
    *,
    ports: PlanPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    if not reason.strip():
        raise PyramidError("archive requires a non-empty reason")
    paths = project_paths(project)
    event: dict[str, Any] | None = None
    chronicle: dict[str, Any] | None = None
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        check_expected_version(plan, state, expected_version)
        claims = active_claims(state)
        if claims:
            raise PyramidError("Resolve active claims (working or paused) before archiving: " + ", ".join(claims))
        lifecycle = lifecycle_state(state)
        if lifecycle["status"] == "archived":
            archive_id = lifecycle.get("archive_id")
            previous_status = lifecycle.get("archived_from_status") or "active"
        else:
            previous_status = lifecycle["status"]
            archive_id = _archive_identifier(plan, state, ports=ports)
            destination = paths["archives"] / archive_id
            before = copy.deepcopy(lifecycle)
            lifecycle.update(
                {
                    "status": "archived",
                    "archived_from_status": previous_status,
                    "archived_at": ports.clock(),
                    "archived_by": actor,
                    "archive_id": archive_id,
                    "archive_path": str(destination),
                }
            )
            event = ports.commit(
                paths,
                state,
                actor=actor,
                event_type="plan.archived",
                node=plan["intent"]["id"],
                before=before,
                after=copy.deepcopy(lifecycle),
                payload={"reason": reason, "archive_id": archive_id},
            )
            existing = [
                item
                for item in history_chronicles(paths["meta"])
                if item.get("plan_id") == plan["plan_id"]
            ]
            if previous_status == "completed" and existing:
                chronicle = existing[-1]
            else:
                report_reference = before.get("completion_report") if previous_status == "completed" else None
                dossier_reference = before.get("change_dossier") if previous_status == "completed" else None
                try:
                    chronicle = record_intent_chronicle(
                        paths["meta"],
                        paths["root"],
                        plan,
                        state,
                        actor,
                        outcome="completed" if previous_status == "completed" else "archived-incomplete",
                        reason=reason,
                        report_path=(paths["root"] / report_reference) if report_reference else None,
                        dossier_path=(paths["root"] / dossier_reference) if dossier_reference else None,
                        closing_event=event,
                    )
                except HistoryError as exc:
                    raise PyramidError(str(exc)) from exc
        if chronicle is None:
            matching = [
                item
                for item in history_chronicles(paths["meta"])
                if item.get("plan_id") == plan["plan_id"]
            ]
            chronicle = matching[-1] if matching else None
        if chronicle is None:
            report_reference = lifecycle.get("completion_report") if previous_status == "completed" else None
            dossier_reference = lifecycle.get("change_dossier") if previous_status == "completed" else None
            try:
                chronicle = record_intent_chronicle(
                    paths["meta"],
                    paths["root"],
                    plan,
                    state,
                    actor,
                    outcome="completed" if previous_status == "completed" else "archived-incomplete",
                    reason=f"Backfilled from an existing archive: {reason}",
                    report_path=(paths["root"] / report_reference) if report_reference else None,
                    dossier_path=(paths["root"] / dossier_reference) if dossier_reference else None,
                    closing_event={
                        "id": "HISTORY-BACKFILL",
                        "type": "history.backfilled",
                        "at": lifecycle.get("archived_at"),
                    },
                )
            except HistoryError as exc:
                raise PyramidError(str(exc)) from exc
    if not archive_id:
        raise PyramidError("Archived lifecycle is missing archive_id")
    ports.compile_project(project, allow_archived=True)
    paths, plan, state = ports.read_project(project)
    destination = paths["archives"] / archive_id
    if not destination.exists():
        manifest = {
            "schema": "pyramid-archive-v1",
            "archive_id": archive_id,
            "plan_id": plan["plan_id"],
            "title": plan["title"],
            "revision": plan["revision"],
            "graph_version": state["graph_version"],
            "archived_at": lifecycle_state(state)["archived_at"],
            "archived_by": lifecycle_state(state)["archived_by"],
            "previous_status": previous_status,
            "reason": reason,
            "plan_sha256": _file_sha256(paths["plan"]),
            "state_sha256": _file_sha256(paths["state"]),
            "chronicle_id": chronicle.get("chronicle_id") if chronicle else None,
        }
        _copy_current_snapshot(paths, destination, manifest)
        validation = ports.validate_query(destination)
        if not validation["valid"]:
            raise PyramidError("Archive validation failed:\n- " + "\n- ".join(validation["errors"]))
    return {
        "status": "archived",
        "archive_id": archive_id,
        "archive": str(destination),
        "event": event,
        "chronicle": chronicle.get("chronicle_id") if chronicle else None,
        "already_archived": event is None,
    }


def reset_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    reason: str,
    expected_version: int | dict[str, Any] | None = None,
    transition_approval: dict[str, Any] | None = None,
    *,
    ports: PlanPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    if not reason.strip():
        raise PyramidError("reset requires a non-empty reason")
    candidate = load_json(Path(plan_path).expanduser().resolve())
    errors = validate_plan(candidate)
    if errors:
        raise PyramidError("Candidate reset plan is invalid:\n- " + "\n- ".join(errors))
    paths, current, state = ports.read_project(project)
    manifest, current_baseline, _ = load_assurance_bundle(paths, current)
    next_mode = manifest["mode"]
    check_expected_version(current, state, expected_version)
    if candidate["plan_id"] == current["plan_id"]:
        raise PyramidError("A reset must use a new plan_id; use replan to revise the current plan")
    if history_contains_plan(paths["meta"], candidate["plan_id"]):
        raise PyramidError(
            f"Plan ID {candidate['plan_id']} already exists in immutable intent history; "
            "use a new plan_id or restore its archive"
        )
    archived = archive_project(project, actor, f"Reset: {reason}", expected_version=expected_version, ports=ports)
    with project_lock(paths):
        paths, _, archived_state = ports.read_project(project)
        if lifecycle_status(archived_state) != "archived":
            raise PyramidError("Reset safety check failed: current plan was not archived")
        if not Path(archived["archive"]).exists():
            raise PyramidError("Reset safety check failed: archive snapshot is missing")
        _purge_current(
            paths,
            preserve_baseline=next_mode == "brownfield" and current_baseline is not None,
            preserve_dossiers=True,
        )
        _, event = _initialize_current(
            paths,
            candidate,
            actor,
            {
                "reset_from_archive": archived["archive_id"],
                "reason": reason,
                **({"transition_approval": transition_approval} if transition_approval else {}),
            },
            mode=next_mode,
            baseline=current_baseline,
         ports=ports)
    compiled = ports.compile_project(project)
    return {
        "status": "reset",
        "previous_archive": archived["archive_id"],
        "event": event,
        "plan_id": candidate["plan_id"],
        **compiled,
    }


def _new_intent_material(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    reason: str,
    *,
    mode: str,
    expected_version: int | dict[str, Any] | None,
    ports: PlanPorts | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    ports = ports or default_ports()
    if not reason.strip():
        raise PyramidError("new-intent requires a non-empty reason")
    candidate_path = Path(plan_path).expanduser().resolve()
    candidate = load_json(candidate_path)
    errors = validate_plan(candidate)
    if errors:
        raise PyramidError("Candidate new-intent plan is invalid:\n- " + "\n- ".join(errors))

    paths = project_paths(project)
    route = ports.transition_route(project)
    current: dict[str, Any] | None = None
    selected_mode = detect_repository_mode(paths["root"]) if mode == "auto" else mode
    if selected_mode not in {"greenfield", "brownfield"}:
        raise PyramidError("new-intent mode must be auto, greenfield, or brownfield")

    if paths["plan"].exists():
        paths, current_plan, state = ports.read_project(project)
        check_expected_version(current_plan, state, expected_version)
        if candidate["plan_id"] == current_plan["plan_id"]:
            raise PyramidError("A new intent must use a new plan_id; use replan for the current intent")
        manifest = load_json(paths["project"])
        selected_mode = manifest["mode"]
        current = {
            "plan_id": current_plan["plan_id"],
            "project_format_version": manifest["format_version"],
            "lifecycle": lifecycle_status(state),
            "graph_version": state["graph_version"],
            "context": context_identity(current_plan, state),
            "active_claims": active_claims(state),
            "plan_sha256": _file_sha256(paths["plan"]),
            "state_sha256": _file_sha256(paths["state"]),
        }

    material = {
        "actor": actor,
        "reason": reason,
        "mode": selected_mode,
        "current": current,
        "candidate": {
            "plan_id": candidate["plan_id"],
            "title": candidate["title"],
            "plan_sha256": _file_sha256(candidate_path),
        },
        "transition": route["transition"],
        "blockers": route["blockers"],
        "warnings": route["warnings"],
    }
    approval_required = current is not None
    preview = {
        "schema": "pyramid-new-intent-preview-v1",
        "status": "preview" if route["can_start_new_intent"] else "blocked",
        "runtime_version": RUNTIME_VERSION,
        "mode": selected_mode,
        "current": current,
        "candidate": copy.deepcopy(material["candidate"]),
        "transition": copy.deepcopy(route["transition"]),
        "preserves": [
            "canonical plan and node history in a restorable archive",
            "events, reports, dossiers, and completed evidence",
            *(["the current brownfield baseline for the next assurance cycle"] if selected_mode == "brownfield" else []),
        ],
        "blockers": copy.deepcopy(route["blockers"]),
        "warnings": copy.deepcopy(route["warnings"]),
        "approval_required": approval_required,
        "new_intent_sha256": canonical_sha256(material),
    }
    return preview, current


def new_intent_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    reason: str,
    *,
    mode: str = "auto",
    apply: bool = False,
    approved_by: str | None = None,
    approval_reference: str | None = None,
    approved_new_intent_sha256: str | None = None,
    expected_version: int | dict[str, Any] | None = None,
    ports: PlanPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    preview, current = _new_intent_material(
        project,
        plan_path,
        actor,
        reason,
        mode=mode,
        expected_version=expected_version,
        ports=ports,
    )
    if not apply:
        return preview
    if preview["status"] == "blocked":
        raise PyramidError("New intent is blocked:\n- " + "\n- ".join(preview["blockers"]))

    if current is None:
        created = create_project(project, plan_path, actor, mode=mode, ports=ports)
        return {
            "schema": "pyramid-new-intent-result-v1",
            "status": "started",
            "transition": ["create"],
            "new_intent_sha256": preview["new_intent_sha256"],
            "reset": None,
            "created": created,
        }

    if not approved_by or not approval_reference or not approved_new_intent_sha256:
        raise PyramidError(
            "new-intent apply requires approved-by, approval-reference, and approved-new-intent-sha256"
        )
    if approved_new_intent_sha256 != preview["new_intent_sha256"]:
        raise PyramidError("Approved new-intent hash does not match the current preview")

    approval = {
        "approved_by": approved_by,
        "reference": approval_reference,
        "new_intent_sha256": approved_new_intent_sha256,
    }
    reset_result = reset_project(
        project,
        plan_path,
        actor,
        reason,
        expected_version={
            "graph_version": current["graph_version"],
            "context_id": current["context"]["id"],
        },
        transition_approval=approval,
        ports=ports,
    )
    return {
        "schema": "pyramid-new-intent-result-v1",
        "status": "started",
        "transition": preview["transition"],
        "new_intent_sha256": approved_new_intent_sha256,
        "approval": approval,
        "reset": reset_result,
        "plan_id": reset_result["plan_id"],
        "previous_archive": reset_result["previous_archive"],
        "graph_version": reset_result["graph_version"],
    }


def restore_project(
    project: str | Path,
    archive_reference: str,
    actor: str,
    reason: str,
    expected_version: int | dict[str, Any] | None = None,
    *,
    ports: PlanPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    if not reason.strip():
        raise PyramidError("restore requires a non-empty reason")
    source, manifest = _resolve_archive(project, archive_reference)
    require_supported_project(project_paths(source))
    source_plan = load_json(source / ".pyramid" / "plan.json")
    source_state = load_json(source / ".pyramid" / "state.json")
    validation_errors = validate_plan(source_plan) + validate_state(source_plan, source_state)
    if validation_errors:
        raise PyramidError("Archived plan is invalid:\n- " + "\n- ".join(validation_errors))
    paths = project_paths(project)
    current_archive: dict[str, Any] | None = None
    if paths["plan"].exists():
        _, current_plan, current_state = ports.read_project(project)
        check_expected_version(current_plan, current_state, expected_version)
        current_archive = archive_project(project, actor, f"Restore {archive_reference}: {reason}", expected_version=expected_version, ports=ports)
    with project_lock(paths):
        _purge_current(paths)
        shutil.copy2(source / ".pyramid" / "plan.json", paths["plan"])
        for key in ("project", "baseline", "assurance"):
            source_file = source / ".pyramid" / paths[key].name
            if source_file.exists():
                shutil.copy2(source_file, paths[key])
        restored_state = copy.deepcopy(source_state)
        lifecycle = lifecycle_state(restored_state)
        completion = {
            key: lifecycle.get(key)
            for key in ("completed_at", "completed_by", "completion_report")
        }
        restored_status = manifest.get("previous_status", "active")
        lifecycle.update(default_lifecycle())
        lifecycle["status"] = restored_status if restored_status in {"active", "completed"} else "active"
        if lifecycle["status"] == "completed":
            lifecycle.update(completion)
        lifecycle["restored_from"] = manifest["archive_id"]
        for item in restored_state["nodes"].values():
            item["owner"] = None
            item["lease_expires_at"] = None
            if item["execution"] in {"working", "paused"}:
                item["execution"] = item.get("work_origin") or "planned"
            item["work_origin"] = None
            item["active_handoff_id"] = None
            item["paused_at"] = None
            item["paused_by"] = None
            item["pause_mode"] = None
            item["resume_deadline"] = None
        write_json(paths["state"], restored_state)
        source_events = source / ".pyramid" / "events"
        if source_events.exists():
            shutil.copytree(source_events, paths["events"])
        source_handoffs = source / ".pyramid" / "handoffs"
        if source_handoffs.exists():
            shutil.copytree(source_handoffs, paths["handoffs"])
        source_reports = source / ".pyramid" / "reports"
        if source_reports.exists():
            shutil.copytree(source_reports, paths["reports"])
        source_dossiers = source / ".pyramid" / "dossiers"
        if source_dossiers.exists():
            shutil.copytree(source_dossiers, paths["dossiers"])
        event = ports.commit(
            paths,
            restored_state,
            actor=actor,
            event_type="plan.restored",
            node=source_plan["intent"]["id"],
            before={"current_archive": current_archive["archive_id"] if current_archive else None},
            after={"restored_from": manifest["archive_id"], "status": lifecycle["status"]},
            payload={"reason": reason, "archive_id": manifest["archive_id"]},
        )
    compiled = ports.compile_project(project)
    return {
        "status": "restored",
        "restored_from": manifest["archive_id"],
        "previous_archive": current_archive["archive_id"] if current_archive else None,
        "event": event,
        **compiled,
    }


def clean_project(project: str | Path, *, ports: PlanPorts | None = None) -> dict[str, Any]:
    ports = ports or default_ports()
    paths = project_paths(project)
    with project_lock(paths):
        paths, _, state = ports.read_project(project)
        if lifecycle_status(state) == "archived":
            raise PyramidError("Archived plans are frozen; restore before cleaning projections")
        canonical = {
            "plan": _file_sha256(paths["plan"]),
            "state": _file_sha256(paths["state"]),
            "head": _file_sha256(paths["head"]),
            "project": _file_sha256(paths["project"]) if paths["project"].exists() else None,
            "baseline": _file_sha256(paths["baseline"]) if paths["baseline"].exists() else None,
            "assurance": _file_sha256(paths["assurance"]) if paths["assurance"].exists() else None,
            "events": sorted((path.name, _file_sha256(path)) for path in paths["events"].glob("*.json")),
            "handoffs": sorted((path.name, _file_sha256(path)) for path in paths["handoffs"].glob("*")) if paths["handoffs"].exists() else [],
            "reports": sorted((path.name, _file_sha256(path)) for path in paths["reports"].glob("*")) if paths["reports"].exists() else [],
            "dossiers": sorted((path.name, _file_sha256(path)) for path in paths["dossiers"].glob("*")) if paths["dossiers"].exists() else [],
        }
        removed = []
        for key in ("graph", "ready", "html", "docs"):
            target = paths[key]
            if target.exists():
                removed.append(str(target))
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
        compiled = ports.compile_locked(project)
        preserved = (
            canonical["plan"] == _file_sha256(paths["plan"])
            and canonical["state"] == _file_sha256(paths["state"])
            and canonical["head"] == _file_sha256(paths["head"])
            and canonical["project"] == (_file_sha256(paths["project"]) if paths["project"].exists() else None)
            and canonical["baseline"] == (_file_sha256(paths["baseline"]) if paths["baseline"].exists() else None)
            and canonical["assurance"] == (_file_sha256(paths["assurance"]) if paths["assurance"].exists() else None)
            and canonical["events"] == sorted((path.name, _file_sha256(path)) for path in paths["events"].glob("*.json"))
            and canonical["handoffs"] == (sorted((path.name, _file_sha256(path)) for path in paths["handoffs"].glob("*")) if paths["handoffs"].exists() else [])
            and canonical["reports"] == (sorted((path.name, _file_sha256(path)) for path in paths["reports"].glob("*")) if paths["reports"].exists() else [])
            and canonical["dossiers"] == (sorted((path.name, _file_sha256(path)) for path in paths["dossiers"].glob("*")) if paths["dossiers"].exists() else [])
        )
        if not preserved:
            raise PyramidError("Clean safety check failed: canonical data changed")
        return {"status": "clean", "removed": removed, "canonical_preserved": True, **compiled}
