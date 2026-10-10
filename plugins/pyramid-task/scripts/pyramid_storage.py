"""Verified canonical reads and the existing event/state/head publication order.

Call mutations under the existing project lock. No projection or command imports;
history retains its independent append/fsync/repair protocol.
"""
from __future__ import annotations
import copy
from pathlib import Path
from typing import Any
from pyramid_errors import PyramidError
from pyramid_files import (UNSUPPORTED_LEGACY_PROJECT, _event_id, _file_sha256,
    load_json, write_json, project_paths, utc_now)
from pyramid_assurance_contracts import validate_project_manifest, validate_baseline, validate_assurance
from pyramid_handoff_io import handoff_validation_errors
from pyramid_state import canonical_sha256, canonical_context_id, context_identity, validate_state
from pyramid_validation import validate_plan
from pyramid_history import history_validation_errors
from pyramid_verification import VerificationError, publish_artifacts


def load_assurance_bundle(
    paths: dict[str, Path],
    plan: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    manifest = load_json(paths["project"]) if paths["project"].exists() else None
    baseline = load_json(paths["baseline"]) if paths["baseline"].exists() else None
    assurance = load_json(paths["assurance"]) if paths["assurance"].exists() else None
    if plan is not None and manifest is not None:
        errors = validate_project_manifest(manifest, plan["plan_id"])
        if manifest.get("mode") == "brownfield":
            if baseline is None:
                errors.append("brownfield project is missing .pyramid/baseline.json")
            else:
                errors.extend(validate_baseline(baseline))
            if assurance is None:
                errors.append("brownfield project is missing .pyramid/assurance.json")
            elif baseline is not None:
                errors.extend(validate_assurance(assurance, plan=plan, baseline=baseline))
        elif baseline is not None or assurance is not None:
            errors.append("greenfield projects cannot contain brownfield baseline or assurance state")
        if errors:
            raise PyramidError("Project assurance validation failed:\n- " + "\n- ".join(errors))
    return manifest, baseline, assurance


def assurance_validation_errors(
    paths: dict[str, Path],
    plan: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    try:
        manifest, baseline, assurance = load_assurance_bundle(paths)
    except PyramidError as exc:
        return [str(exc)]
    if manifest is None:
        return [UNSUPPORTED_LEGACY_PROJECT]
    errors.extend(validate_project_manifest(manifest, plan.get("plan_id")))
    if manifest.get("mode") == "brownfield":
        if baseline is None:
            errors.append("brownfield project is missing .pyramid/baseline.json")
        else:
            errors.extend(validate_baseline(baseline))
        if assurance is None:
            errors.append("brownfield project is missing .pyramid/assurance.json")
        elif baseline is not None:
            errors.extend(validate_assurance(assurance, plan=plan, baseline=baseline))
    elif baseline is not None or assurance is not None:
        errors.append("greenfield projects cannot contain baseline or assurance state")
    return errors


def implementation_frontier(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    """Return the latest immutable implementation event for each task."""
    frontier: dict[str, dict[str, Any]] = {}
    if not paths["events"].exists():
        return frontier
    for event_path in paths["events"].glob("*.json"):
        event = load_json(event_path)
        task = event.get("node")
        if event.get("type") != "task.implemented" or not isinstance(task, str):
            continue
        version = event.get("graph_version")
        current = frontier.get(task)
        if not isinstance(version, int) or (
            current is not None and version <= current["graph_version"]
        ):
            continue
        payload = event.get("payload")
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            after = event.get("after")
            result = after.get("last_result") if isinstance(after, dict) else None
        change_effect = result.get("change_effect") if isinstance(result, dict) else None
        frontier[task] = {
            "event_id": event.get("id"),
            "graph_version": version,
            "at": event.get("at"),
            "change_effect": change_effect if isinstance(change_effect, str) else None,
        }
    return frontier


def _collection_sha256(path: Path) -> str:
    entries = [
        {
            "path": str(item.relative_to(path)),
            "sha256": _file_sha256(item),
        }
        for item in sorted(path.rglob("*"))
        if item.is_file()
    ] if path.exists() else []
    return canonical_sha256(entries)


def _canonical_file_hashes(paths: dict[str, Path]) -> dict[str, str | None]:
    hashes = {
        key: _file_sha256(paths[key]) if paths[key].exists() else None
        for key in ("plan", "state", "project", "baseline", "assurance")
    }
    hashes.update(
        {
            key: _collection_sha256(paths[key])
            for key in ("events", "handoffs", "reports", "dossiers")
        }
    )
    return hashes


def _previous_event(paths: dict[str, Path]) -> tuple[str | None, str | None]:
    if paths["head"].exists():
        try:
            head = load_json(paths["head"])
            event = head.get("event", {})
            if isinstance(event, dict) and event.get("id") and event.get("sha256"):
                return event["id"], event["sha256"]
        except PyramidError:
            pass
    candidates: list[tuple[int, str, str, Path]] = []
    if paths["events"].exists():
        for event_path in paths["events"].glob("*.json"):
            try:
                event = load_json(event_path)
            except PyramidError:
                continue
            candidates.append(
                (
                    int(event.get("graph_version", 0)),
                    str(event.get("at", "")),
                    str(event.get("id", event_path.stem)),
                    event_path,
                )
            )
    if not candidates:
        return None, None
    _, _, event_id, event_path = max(candidates)
    return event_id, _file_sha256(event_path)


def _publish_head(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
    event: dict[str, Any],
    event_sha256: str,
) -> dict[str, Any]:
    context = context_identity(plan, state)
    head = {
        "schema": "pyramid-head-v1",
        "committed_at": event["at"],
        "context": context,
        "files": _canonical_file_hashes(paths),
        "event": {
            "id": event["id"],
            "sha256": event_sha256,
            "previous_sha256": event.get("previous_event_sha256"),
        },
    }
    write_json(paths["head"], head)
    return head


def _persist_event(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    previous_id, previous_sha256 = _previous_event(paths)
    # Proof blobs share the existing event/head publication and archive boundary.
    # Validation happens before this point; an interrupted publication fails the
    # canonical-head check rather than silently accepting partial evidence.
    field = {"task.implemented": "last_result", "audit.pass": "last_audit"}.get(event["type"])
    if field and plan.get("schema_version") == 2:
        record = state["nodes"][event["node"]][field]
        try:
            publish_artifacts(paths["root"], record)
        except (VerificationError, OSError) as exc:
            raise PyramidError(f"Could not publish proof artifacts: {exc}") from exc
        event["after"][field] = copy.deepcopy(record)
        event["payload"]["result" if field == "last_result" else "audit"] = copy.deepcopy(record)
    state["context_id"] = canonical_context_id(plan, state)
    context = context_identity(plan, state)
    event.update(
        {
            "plan_id": plan["plan_id"],
            "plan_revision": plan["revision"],
            "context_id": context["id"],
            "previous_event_id": previous_id,
            "previous_event_sha256": previous_sha256,
        }
    )
    paths["events"].mkdir(parents=True, exist_ok=True)
    event_path = paths["events"] / f"{event['id']}.json"
    write_json(event_path, event)
    write_json(paths["state"], state)
    _publish_head(paths, plan, state, event, _file_sha256(event_path))
    return event


def head_validation_errors(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
) -> list[str]:
    if not paths["head"].exists():
        if state.get("context_id") is not None:
            return ["context-bound state is missing .pyramid/head.json"]
        if paths["events"].exists():
            for event_path in paths["events"].glob("*.json"):
                try:
                    event = load_json(event_path)
                except PyramidError as exc:
                    return [str(exc)]
                if any(
                    key in event
                    for key in (
                        "context_id",
                        "previous_event_id",
                        "previous_event_sha256",
                    )
                ):
                    return ["context-bound event history is missing .pyramid/head.json"]
        return []
    try:
        head = load_json(paths["head"])
    except PyramidError as exc:
        return [str(exc)]
    errors: list[str] = []
    if head.get("schema") != "pyramid-head-v1":
        errors.append("head.schema must be pyramid-head-v1")
        return errors
    expected_context = context_identity(plan, state)
    if state.get("context_id") != canonical_context_id(plan, state):
        errors.append("state.context_id does not match canonical plan and state content")
    if head.get("context") != expected_context:
        errors.append("head context does not match the current plan and state")
    expected_files = _canonical_file_hashes(paths)
    if head.get("files") != expected_files:
        errors.append("canonical files do not match the atomically published head")
    event = head.get("event")
    if not isinstance(event, dict) or not event.get("id") or not event.get("sha256"):
        errors.append("head event identity is incomplete")
    else:
        event_path = paths["events"] / f"{event['id']}.json"
        if not event_path.exists():
            errors.append(f"head event is missing: {event['id']}")
        elif _file_sha256(event_path) != event["sha256"]:
            errors.append(f"head event hash mismatch: {event['id']}")
    return errors


def event_chain_validation_errors(paths: dict[str, Path]) -> list[str]:
    if not paths["events"].exists():
        return []
    records: list[tuple[int, str, str, Path, dict[str, Any]]] = []
    errors: list[str] = []
    for event_path in paths["events"].glob("*.json"):
        try:
            event = load_json(event_path)
        except PyramidError as exc:
            errors.append(str(exc))
            continue
        records.append(
            (
                int(event.get("graph_version", 0)),
                str(event.get("at", "")),
                str(event.get("id", event_path.stem)),
                event_path,
                event,
            )
        )
    records.sort(key=lambda item: (item[0], item[1], item[2]))
    prior_id: str | None = None
    prior_sha256: str | None = None
    chain_started = False
    for _, _, event_id, event_path, event in records:
        linked = "previous_event_sha256" in event or "previous_event_id" in event
        if linked:
            if event.get("previous_event_id") != prior_id:
                errors.append(f"{event_id}: previous event ID does not match the event chain")
            if event.get("previous_event_sha256") != prior_sha256:
                errors.append(f"{event_id}: previous event hash does not match the event chain")
            chain_started = True
        elif chain_started:
            errors.append(f"{event_id}: hash-chain metadata disappeared after it was introduced")
        prior_id = event_id
        prior_sha256 = _file_sha256(event_path)
    return errors


def load_project(project: str | Path, check: bool = True) -> tuple[dict[str, Path], dict[str, Any], dict[str, Any]]:
    paths = project_paths(project)
    plan = load_json(paths["plan"])
    state = load_json(paths["state"])
    if check:
        errors = (
            validate_plan(plan)
            + validate_state(plan, state)
            + assurance_validation_errors(paths, plan)
            + handoff_validation_errors(paths, plan, state)
            + head_validation_errors(paths, plan, state)
            + history_validation_errors(paths["meta"])
        )
        if errors:
            raise PyramidError("Project validation failed:\n- " + "\n- ".join(errors))
    return paths, plan, state


def commit_event(
    paths: dict[str, Path],
    state: dict[str, Any],
    *,
    actor: str,
    event_type: str,
    node: str | None,
    before: Any,
    after: Any,
    payload: dict[str, Any] | None = None,
    clock=utc_now,
    event_id=_event_id,
) -> dict[str, Any]:
    state["graph_version"] += 1
    state["updated_at"] = clock()
    plan = load_json(paths["plan"])
    event = {
        "schema": "pyramid-event-v1",
        "id": event_id(),
        "at": state["updated_at"],
        "graph_version": state["graph_version"],
        "actor": actor,
        "type": event_type,
        "node": node,
        "before": before,
        "after": after,
        "payload": payload or {},
    }
    return _persist_event(paths, plan, state, event)
