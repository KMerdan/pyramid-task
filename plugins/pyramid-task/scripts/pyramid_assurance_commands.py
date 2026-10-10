"""P3B assurance_commands boundary; no facade imports.

Existing control flow and canonical/history publication protocol are retained.
"""
from __future__ import annotations
from pathlib import Path
from pyramid_assurance import assurance_blockers
from pyramid_assurance import assurance_summary
from pyramid_assurance import mark_assurance_stale
from pyramid_assurance import validate_assurance
from pyramid_assurance import validate_baseline
from pyramid_errors import PyramidError
from pyramid_files import load_json
from pyramid_files import project_lock
from pyramid_files import write_json
from pyramid_plan_bundle import PlanPorts, default_ports
from pyramid_state import canonical_sha256
from pyramid_state import check_expected_version
from pyramid_state import context_identity
from pyramid_state import require_active
from pyramid_storage import implementation_frontier
from pyramid_storage import load_assurance_bundle
from typing import Any
import copy


def assess_project(
    project: str | Path,
    baseline_path: str | Path,
    actor: str,
    *,
    apply: bool = False,
    expected_version: int | dict[str, Any] | None = None,
    ports: PlanPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    candidate = load_json(Path(baseline_path).expanduser().resolve())
    errors = validate_baseline(candidate)
    if errors:
        raise PyramidError("Candidate baseline is invalid:\n- " + "\n- ".join(errors))
    paths, plan, state = ports.read_project(project)
    check_expected_version(plan, state, expected_version)
    require_active(state, "assess the baseline")
    manifest, current, assurance = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or current is None or assurance is None:
        raise PyramidError("assess requires a V3 brownfield project")
    if candidate["revision"] < current["revision"] or (
        candidate["revision"] == current["revision"] and current.get("status") != "incomplete"
    ):
        raise PyramidError("Candidate baseline revision must advance the current assessed baseline")
    retained_assets = {item["id"] for item in candidate["assets"]}
    referenced_assets = {
        item["asset_id"] for item in assurance.get("impacts", [])
    } | {
        asset_id
        for key in ("inspections", "findings")
        for item in assurance.get(key, [])
        for asset_id in item.get("asset_ids", [])
    } | {
        asset_id
        for node in plan.get("nodes", [])
        for output in node.get("agent", {}).get("generated_outputs", [])
        if isinstance(output, dict)
        for asset_id in output.get("asset_ids", [])
    }
    missing_references = sorted(referenced_assets - retained_assets)
    if missing_references:
        raise PyramidError(
            "Candidate baseline removes assets still referenced by assurance: "
            + ", ".join(missing_references)
            + ". Retain them as historical assets, then update impact records."
        )
    preview = {
        "status": "preview",
        "schema": "pyramid-assess-preview-v1",
        "graph_version": state["graph_version"],
        "context": context_identity(plan, state),
        "from_revision": current["revision"],
        "to_revision": candidate["revision"],
        "assets": len(candidate["assets"]),
        "relations": len(candidate["relations"]),
        "history": len(candidate["history"]),
        "unknowns": copy.deepcopy(candidate["unknowns"]),
        "baseline_sha256": canonical_sha256(candidate),
    }
    if not apply:
        return preview
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        check_expected_version(plan, state, expected_version)
        require_active(state, "assess the baseline")
        manifest, current, assurance = load_assurance_bundle(paths, plan)
        if current is None or assurance is None:
            raise PyramidError("Brownfield assurance state disappeared before apply")
        if current["revision"] != preview["from_revision"]:
            raise PyramidError("Baseline changed after preview; inspect and apply again")
        next_assurance = copy.deepcopy(assurance)
        next_assurance["baseline_id"] = candidate["baseline_id"]
        next_assurance["baseline_revision"] = candidate["revision"]
        for inspection in next_assurance.get("inspections", []):
            if inspection.get("status") == "performed":
                inspection["status"] = "stale"
                limitations = inspection.setdefault("limitations", [])
                message = "Baseline revision changed after this inspection was performed."
                if message not in limitations:
                    limitations.append(message)
        mark_assurance_stale(
            next_assurance,
            f"Baseline changed from revision {current['revision']} to {candidate['revision']}; impact and inspections require review.",
            actor,
        )
        write_json(paths["baseline"], candidate)
        write_json(paths["assurance"], next_assurance)
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type="assurance.baseline-assessed",
            node=plan["intent"]["id"],
            before={"baseline_id": current["baseline_id"], "revision": current["revision"]},
            after={"baseline_id": candidate["baseline_id"], "revision": candidate["revision"]},
            payload={"baseline_sha256": preview["baseline_sha256"]},
        )
    compiled = ports.compile_project(project)
    return {**preview, "status": "applied", "event": event, **compiled}


def _assurance_semantic_sha256(assurance: dict[str, Any]) -> str:
    material = copy.deepcopy(assurance)
    material.pop("updated_at", None)
    material.pop("updated_by", None)
    return canonical_sha256(material)


def _normalize_assurance_candidate(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    actor: str,
    frontier: dict[str, dict[str, Any]],
    *,
    stamp: bool,
    ports: PlanPorts | None = None,
) -> tuple[dict[str, Any], list[str]]:
    ports = ports or default_ports()
    normalized = copy.deepcopy(candidate)
    for inspection in normalized.get("inspections", []):
        if inspection.get("status") != "performed":
            continue
        performed_at = ports.parse_time(inspection.get("performed_at"))
        inspection["validated_through"] = {
            task: frontier[task]["event_id"]
            for task in inspection.get("task_ids", [])
            if task in frontier
            and performed_at is not None
            and ports.parse_time(frontier[task].get("at")) is not None
            and ports.parse_time(frontier[task]["at"]) <= performed_at
        }
    normalized["status"] = "incomplete"
    blockers = assurance_blockers(
        baseline,
        normalized,
        full=True,
        implementation_frontier=frontier,
    )
    normalized["status"] = "ready" if not blockers else "incomplete"
    if normalized["status"] == "ready":
        normalized["stale_reasons"] = []
    if stamp:
        normalized["updated_at"] = ports.clock()
        normalized["updated_by"] = actor
    return normalized, blockers


def impact_project(
    project: str | Path,
    assurance_path: str | Path,
    actor: str,
    *,
    apply: bool = False,
    expected_version: int | dict[str, Any] | None = None,
    ports: PlanPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    candidate = load_json(Path(assurance_path).expanduser().resolve())
    paths, plan, state = ports.read_project(project)
    check_expected_version(plan, state, expected_version)
    require_active(state, "update change impact")
    manifest, baseline, current = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or baseline is None or current is None:
        raise PyramidError("impact requires a V3 brownfield project")
    errors = validate_assurance(candidate, plan=plan, baseline=baseline)
    if errors:
        raise PyramidError("Candidate assurance is invalid:\n- " + "\n- ".join(errors))
    frontier = implementation_frontier(paths)
    normalized, blockers = _normalize_assurance_candidate(
        candidate,
        baseline,
        actor,
        frontier,
        stamp=False,
     ports=ports)
    preview = {
        "status": "preview",
        "schema": "pyramid-impact-preview-v1",
        "graph_version": state["graph_version"],
        "context": context_identity(plan, state),
        "impacts": len(normalized["impacts"]),
        "inspections": len(normalized["inspections"]),
        "findings": len(normalized["findings"]),
        "open_scope_drift": sum(item.get("status") == "open" for item in normalized["scope_drift"]),
        "assurance_status": normalized["status"],
        "blockers": blockers,
        "assurance_sha256": _assurance_semantic_sha256(normalized),
        "warnings": assurance_summary(
            baseline,
            normalized,
            implementation_frontier=frontier,
        )["warnings"],
    }
    if not apply:
        return preview
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        check_expected_version(plan, state, expected_version)
        require_active(state, "update change impact")
        _, baseline, current_assurance = load_assurance_bundle(paths, plan)
        if baseline is None or current_assurance is None:
            raise PyramidError("Baseline disappeared before impact apply")
        frontier = implementation_frontier(paths)
        normalized, blockers = _normalize_assurance_candidate(
            candidate,
            baseline,
            actor,
            frontier,
            stamp=True,
         ports=ports)
        errors = validate_assurance(normalized, plan=plan, baseline=baseline)
        if errors:
            raise PyramidError("Candidate assurance became invalid:\n- " + "\n- ".join(errors))
        write_json(paths["assurance"], normalized)
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type="assurance.impact-updated",
            node=plan["intent"]["id"],
            before={"assurance_sha256": canonical_sha256(current_assurance)},
            after={"assurance_sha256": canonical_sha256(normalized), "status": normalized["status"]},
            payload={
                "blockers": blockers,
                "candidate_sha256": _assurance_semantic_sha256(normalized),
            },
        )
    compiled = ports.compile_project(project)
    return {**preview, "status": "applied", "event": event, **compiled}
