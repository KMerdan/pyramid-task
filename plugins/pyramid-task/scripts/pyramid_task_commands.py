"""Complete task operations under the existing storage/publication protocol.

TaskPorts are immutable named bindings for existing reader/clock/compile seams.
Defaults use concrete lower modules; no facade import or global rebinding.
"""
from __future__ import annotations
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from pyramid_errors import PyramidError
from pyramid_files import project_paths, project_lock, load_json, write_json, utc_now, parse_time, _handoff_identifier
from pyramid_storage import load_project, load_assurance_bundle, implementation_frontier, commit_event
from pyramid_publication import compile_project, _compile_project_locked
from pyramid_state import (require_active, check_expected_guard, check_expected_version, task_mutation_guard,
    audit_mutation_guard, canonical_sha256, context_identity, lifecycle_status, lifecycle_state,
    invalidate_dependent_claims as invalidate_claim_values)
from pyramid_graph import node_map, availability, EXECUTABLE_KINDS, start_blockers
from pyramid_projection import task_packet
from pyramid_handoff import _validate_handoff_draft, _handoff_record_errors, _handoff_path, _handoff_markdown
from pyramid_handoff_io import _handoff_fingerprint, _handoff_drift
from pyramid_change_io import (_record_scope_drift, _invalidate_inspections_for_actual_change,
    _invalidate_assurance_for_change, _assurance_audit_errors)
from pyramid_changes import _path_matches
from pyramid_results import _validate_agent_result, _validate_audit_result, _audit_prerequisite_errors
from pyramid_proof_io import _normalize_proofs, _audit_proof_dependencies
from pyramid_amendment import prepare_amendment
from pyramid_parallel import _task_scopes, _patterns_overlap
from pyramid_assurance_rules import asset_ids_for_file
from pyramid_validation import validate_plan
from pyramid_verification import VerificationError, validate_amendment_inputs


@dataclass(frozen=True)
class TaskPorts:
    read_project: Callable
    compile_project: Callable
    compile_locked: Callable
    clock: Callable
    date_type: type
    commit: Callable
    handoff_id: Callable
    record_drift: Callable
    invalidate_claims: Callable
    parse_time: Callable


def _invalidate_claims(plan, state, origin, reason):
    return invalidate_claim_values(plan, state, origin, reason, timestamp=utc_now())


def default_ports() -> TaskPorts:
    return TaskPorts(load_project, compile_project, _compile_project_locked, utc_now,
                     datetime, commit_event, _handoff_identifier, _record_scope_drift,
                     _invalidate_claims, parse_time)


def take_task(
    project: str | Path,
    actor: str,
    nid: str | None = None,
    take_next: bool = False,
    lease_minutes: int = 120,
    expected_version: int | dict[str, Any] | None = None,
    expected_guard: str | None = None,
    *,
    ports: TaskPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    paths = project_paths(project)
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        require_active(state, "take work")
        nodes = node_map(plan)
        if take_next:
            ready = [node for node in plan["nodes"] if availability(plan, state, node) in {"ready", "needs-rework"}]
            ready.sort(key=lambda item: (availability(plan, state, item) != "needs-rework", item["wave"], item["level"], item["id"]))
            if not ready:
                raise PyramidError("No ready executable task is available")
            nid = ready[0]["id"]
        if not nid or nid not in nodes:
            raise PyramidError(f"Unknown node: {nid}")
        _, baseline, assurance = load_assurance_bundle(paths, plan)
        if expected_guard is not None:
            check_expected_guard(
                task_mutation_guard(plan, state, nid, baseline, assurance),
                expected_guard,
                "task",
            )
        else:
            check_expected_version(plan, state, expected_version)
        node = nodes[nid]
        item = state["nodes"][nid]
        expired = item["execution"] == "working" and ports.parse_time(item.get("lease_expires_at")) and ports.parse_time(item.get("lease_expires_at")) <= ports.date_type.now(timezone.utc)
        current_availability = "ready" if expired else availability(plan, state, node)
        if current_availability not in {"ready", "needs-rework"}:
            raise PyramidError(f"{nid} is {current_availability}, not ready or awaiting rework")
        before = copy.deepcopy(item)
        item["work_origin"] = (
            item["execution"]
            if item["execution"] in {"planned", "needs-rework"}
            else item.get("work_origin") or "planned"
        )
        item["execution"] = "working"
        item["owner"] = actor
        item["lease_expires_at"] = (ports.date_type.now(timezone.utc) + timedelta(minutes=lease_minutes)).isoformat().replace("+00:00", "Z")
        item["health"] = "clear"
        item["blocker"] = None
        item["updated_at"] = ports.clock()
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type="task.taken" if not expired else "task.reclaimed-expired",
            node=nid,
            before=before,
            after=copy.deepcopy(item),
            payload={"lease_minutes": lease_minutes},
        )
    ports.compile_project(project)
    paths, plan, state = ports.read_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    frontier = implementation_frontier(paths)
    return {
        "status": "taken",
        "event": event,
        "packet": task_packet(plan, state, nid, baseline, assurance, frontier),
    }


def pause_task(
    project: str | Path,
    nid: str,
    actor: str,
    reason: str,
    handoff_path: str | Path,
    *,
    mode: str = "hold",
    resume_minutes: int = 60,
    expected_version: int | dict[str, Any] | None = None,
    expected_guard: str | None = None,
    ports: TaskPorts | None = None,
) -> dict[str, Any]:
    """Pause an owned task and persist a complete, immutable continuation record."""
    ports = ports or default_ports()
    if mode not in {"hold", "handoff"}:
        raise PyramidError("pause mode must be hold or handoff")
    if not reason.strip():
        raise PyramidError("pause requires a non-empty reason")
    if mode == "hold" and resume_minutes < 1:
        raise PyramidError("resume-minutes must be positive for a hold pause")
    draft = load_json(Path(handoff_path).expanduser().resolve())
    draft_errors = _validate_handoff_draft(draft)
    if draft_errors:
        raise PyramidError("Invalid handoff draft:\n- " + "\n- ".join(draft_errors))
    paths = project_paths(project)
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        require_active(state, "pause work")
        nodes = node_map(plan)
        if nid not in nodes:
            raise PyramidError(f"Unknown node: {nid}")
        _, baseline, assurance = load_assurance_bundle(paths, plan)
        if expected_guard is not None:
            check_expected_guard(
                task_mutation_guard(plan, state, nid, baseline, assurance),
                expected_guard,
                "task",
            )
        else:
            check_expected_version(plan, state, expected_version)
        node = nodes[nid]
        item = state["nodes"][nid]
        if node["kind"] not in EXECUTABLE_KINDS:
            raise PyramidError(f"{nid} is not an executable task")
        if item.get("execution") != "working" or item.get("owner") != actor:
            raise PyramidError(f"{actor} must hold an active lease for {nid} before pausing it")
        expires_at = ports.parse_time(item.get("lease_expires_at"))
        if expires_at is not None and expires_at <= ports.date_type.now(timezone.utc):
            raise PyramidError(f"{nid} has an expired lease and cannot be paused by its former owner")

        pause_time = ports.clock()
        deadline = (
            (ports.date_type.now(timezone.utc) + timedelta(minutes=resume_minutes)).isoformat().replace("+00:00", "Z")
            if mode == "hold"
            else None
        )
        handoff_id = ports.handoff_id(nid)
        handoff = {
            "schema": "pyramid-handoff-v1",
            "id": handoff_id,
            "plan_id": plan["plan_id"],
            "task": nid,
            "graph_version": state["graph_version"] + 1,
            "actor": actor,
            "pause_mode": mode,
            "reason": reason,
            "created_at": pause_time,
            "resume_deadline": deadline,
            "summary": draft["summary"].strip(),
            "progress": copy.deepcopy(draft["progress"]),
            "changed_files": copy.deepcopy(draft["changed_files"]),
            "changed_assets": copy.deepcopy(draft["changed_assets"]),
            "checks": copy.deepcopy(draft["checks"]),
            "decisions": copy.deepcopy(draft["decisions"]),
            "assumptions": copy.deepcopy(draft["assumptions"]),
            "blockers": copy.deepcopy(draft["blockers"]),
            "risks": copy.deepcopy(draft["risks"]),
            "next_steps": copy.deepcopy(draft["next_steps"]),
            "recommended_first_action": draft["recommended_first_action"].strip(),
            "context_references": copy.deepcopy(draft["context_references"]),
            "external_session_refs": copy.deepcopy(draft["external_session_refs"]),
            "running_resources": copy.deepcopy(draft["running_resources"]),
            "fingerprint": _handoff_fingerprint(paths),
        }
        handoff_errors = _handoff_record_errors(handoff, plan_id=plan["plan_id"], nid=nid)
        if handoff_errors:
            raise PyramidError("Generated handoff is invalid:\n- " + "\n- ".join(handoff_errors))
        handoff_json = _handoff_path(paths, handoff_id)
        handoff_markdown = handoff_json.with_suffix(".md")
        write_json(handoff_json, handoff)
        handoff_markdown.write_text(_handoff_markdown(handoff), encoding="utf-8")

        before = copy.deepcopy(item)
        item["execution"] = "paused"
        item["owner"] = actor if mode == "hold" else None
        item["lease_expires_at"] = deadline if mode == "hold" else None
        item["active_handoff_id"] = handoff_id
        item["paused_at"] = pause_time
        item["paused_by"] = actor
        item["pause_mode"] = mode
        item["resume_deadline"] = deadline
        item["last_handoff"] = {
            "id": handoff_id,
            "paused_at": pause_time,
            "paused_by": actor,
            "mode": mode,
            "resumed_at": None,
            "resumed_by": None,
        }
        item["updated_at"] = pause_time
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type="task.paused",
            node=nid,
            before=before,
            after=copy.deepcopy(item),
            payload={
                "reason": reason,
                "mode": mode,
                "resume_deadline": deadline,
                "handoff_id": handoff_id,
                "handoff_path": str(handoff_json.relative_to(paths["root"])),
                "handoff_sha256": canonical_sha256(handoff),
            },
        )
    compiled = ports.compile_project(project)
    paths, plan, state = ports.read_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    frontier = implementation_frontier(paths)
    return {
        "status": "paused",
        "event": event,
        "packet": task_packet(plan, state, nid, baseline, assurance, frontier),
        "handoff": {
            "id": handoff_id,
            "json": str(handoff_json),
            "markdown": str(handoff_markdown),
            "resume_deadline": deadline,
        },
        **compiled,
    }


def resume_task(
    project: str | Path,
    nid: str,
    actor: str,
    *,
    handoff_id: str | None = None,
    lease_minutes: int = 120,
    accept_stale: bool = False,
    takeover: bool = False,
    for_recovery: bool = False,
    expected_version: int | dict[str, Any] | None = None,
    ports: TaskPorts | None = None,
) -> dict[str, Any]:
    """Resume a paused task only after its recorded continuation context is checked."""
    ports = ports or default_ports()
    if lease_minutes < 1:
        raise PyramidError("lease-minutes must be positive")
    paths = project_paths(project)
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        check_expected_version(plan, state, expected_version)
        require_active(state, "resume work")
        nodes = node_map(plan)
        if nid not in nodes:
            raise PyramidError(f"Unknown node: {nid}")
        item = state["nodes"][nid]
        if item.get("execution") != "paused":
            raise PyramidError(f"{nid} is not paused")
        active_handoff_id = item.get("active_handoff_id")
        if not isinstance(active_handoff_id, str):
            raise PyramidError(f"{nid} has no active handoff record")
        if handoff_id and handoff_id != active_handoff_id:
            raise PyramidError(f"{handoff_id} is not the active handoff for {nid}")
        handoff = load_json(_handoff_path(paths, active_handoff_id))
        errors = _handoff_record_errors(handoff, plan_id=plan["plan_id"], nid=nid)
        if errors:
            raise PyramidError("Invalid active handoff:\n- " + "\n- ".join(errors))

        mode = handoff.get("pause_mode")
        deadline = ports.parse_time(handoff.get("resume_deadline"))
        if mode == "hold" and actor != item.get("paused_by"):
            if deadline is None or deadline > ports.date_type.now(timezone.utc) or not takeover:
                raise PyramidError(
                    f"{nid} is held by {item.get('paused_by')}; only that actor may resume it before its deadline"
                )
        if item.get("health") == "blocked" and not for_recovery:
            raise PyramidError(
                f"{nid} is blocked; use --for-recovery to resume ownership for blocker resolution. "
                "Recovery preserves the blocker and all resume guards."
            )
        blocked_by = start_blockers(plan, state, nodes[nid])
        if blocked_by:
            raise PyramidError(f"{nid} cannot resume because dependencies are not verified: {', '.join(blocked_by)}")
        drift = _handoff_drift(paths, state, handoff)
        if drift and not accept_stale:
            return {
                "status": "stale-handoff",
                "task": nid,
                "handoff_id": active_handoff_id,
                "drift": drift,
                "next_action": "Review the changed graph or worktree, then resume with --accept-stale if the handoff remains safe.",
            }

        before = copy.deepcopy(item)
        resumed_at = ports.clock()
        item["execution"] = "working"
        item["owner"] = actor
        item["lease_expires_at"] = (
            ports.date_type.now(timezone.utc) + timedelta(minutes=lease_minutes)
        ).isoformat().replace("+00:00", "Z")
        item["active_handoff_id"] = None
        item["paused_at"] = None
        item["paused_by"] = None
        item["pause_mode"] = None
        item["resume_deadline"] = None
        item["last_handoff"] = {
            "id": active_handoff_id,
            "paused_at": handoff["created_at"],
            "paused_by": handoff["actor"],
            "mode": handoff["pause_mode"],
            "resumed_at": resumed_at,
            "resumed_by": actor,
            "accepted_stale_drift": drift,
        }
        item["updated_at"] = resumed_at
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type="task.resumed",
            node=nid,
            before=before,
            after=copy.deepcopy(item),
            payload={
                "handoff_id": active_handoff_id,
                "handoff_sha256": canonical_sha256(handoff),
                "lease_minutes": lease_minutes,
                "takeover": takeover,
                "for_recovery": for_recovery,
                "accepted_stale_drift": drift,
            },
        )
    ports.compile_project(project)
    paths, plan, state = ports.read_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    frontier = implementation_frontier(paths)
    packet = task_packet(plan, state, nid, baseline, assurance, frontier)
    packet["handoff"] = {
        "id": active_handoff_id,
        "path": str(_handoff_path(paths, active_handoff_id)),
        "summary": handoff["summary"],
        "progress": handoff["progress"],
        "changed_files": handoff["changed_files"],
        "checks": handoff["checks"],
        "decisions": handoff["decisions"],
        "blockers": handoff["blockers"],
        "risks": handoff["risks"],
        "next_steps": handoff["next_steps"],
        "recommended_first_action": handoff["recommended_first_action"],
        "context_references": handoff["context_references"],
        "external_session_refs": handoff["external_session_refs"],
        "running_resources": handoff["running_resources"],
        "accepted_stale_drift": drift,
    }
    return {"status": "resumed", "event": event, "packet": packet}


def update_task(
    project: str | Path,
    nid: str,
    actor: str,
    status: str,
    reason: str | None = None,
    result_path: str | Path | None = None,
    expected_version: int | dict[str, Any] | None = None,
    expected_guard: str | None = None,
    *,
    ports: TaskPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    if status not in {"implemented", "blocked", "at-risk", "clear", "release"}:
        raise PyramidError(f"Unsupported update status: {status}")
    paths = project_paths(project)
    result = load_json(Path(result_path).expanduser().resolve()) if result_path else None
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        require_active(state, "update work")
        nodes = node_map(plan)
        if nid not in nodes:
            raise PyramidError(f"Unknown node: {nid}")
        _, baseline, assurance = load_assurance_bundle(paths, plan)
        if expected_guard is not None:
            check_expected_guard(
                task_mutation_guard(plan, state, nid, baseline, assurance),
                expected_guard,
                "task",
            )
        else:
            check_expected_version(plan, state, expected_version)
        item = state["nodes"][nid]
        if item.get("execution") == "paused":
            raise PyramidError(f"{nid} is paused; resume it before recording an update")
        if item.get("owner") != actor:
            raise PyramidError(f"{actor} does not own {nid}")
        before = copy.deepcopy(item)
        scope_drift: list[str] = []
        assurance_invalidated: list[str] = []
        stale_inspections: list[str] = []
        if status == "implemented":
            if item["execution"] != "working":
                raise PyramidError(f"{nid} must be working before it can be implemented")
            if result is None:
                raise PyramidError("implemented requires --result agent-result-v1 JSON")
            result = _normalize_proofs(paths, plan, state, nid, result)
            errors = _validate_agent_result(result, nodes[nid])
            if errors:
                raise PyramidError("Invalid agent result:\n- " + "\n- ".join(errors))
            item["execution"] = "implemented"
            item["verification"] = "pending"
            item["health"] = "clear"
            item["blocker"] = None
            item["owner"] = None
            item["lease_expires_at"] = None
            item["work_origin"] = None
            item["last_result"] = result
            scope_drift, assurance_invalidated = ports.record_drift(
                paths, plan, state, nid, result, actor
            )
            stale_inspections = _invalidate_inspections_for_actual_change(
                paths, plan, nid, result, actor
            )
        elif status == "blocked":
            if not reason:
                raise PyramidError("blocked requires --reason")
            item["health"] = "blocked"
            item["blocker"] = reason
            item["last_result"] = result
        elif status == "at-risk":
            if not reason:
                raise PyramidError("at-risk requires --reason")
            item["health"] = "at-risk"
            item["blocker"] = reason
        elif status == "clear":
            item["health"] = "clear"
            item["blocker"] = None
        elif status == "release":
            if item["execution"] != "working":
                raise PyramidError(f"{nid} is not working")
            origin = item.get("work_origin") or "planned"
            item["execution"] = origin
            if origin == "needs-rework":
                item["verification"] = "failed"
                item["health"] = "at-risk"
                item["blocker"] = item.get("blocker") or "Rework was released before repair."
            else:
                item["verification"] = "unverified"
                item["health"] = "clear"
                item["blocker"] = None
            item["owner"] = None
            item["lease_expires_at"] = None
            item["work_origin"] = None
        item["updated_at"] = ports.clock()
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type=f"task.{status}",
            node=nid,
            before=before,
            after=copy.deepcopy(item),
            payload={
                "reason": reason,
                "result": result,
                "scope_drift": scope_drift,
                "assurance_invalidated": assurance_invalidated,
                "stale_inspections": stale_inspections,
            },
        )
    ports.compile_project(project)
    paths, plan, state = ports.read_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    frontier = implementation_frontier(paths)
    return {
        "status": status,
        "event": event,
        "packet": task_packet(plan, state, nid, baseline, assurance, frontier),
        "scope_drift": scope_drift,
        "assurance_invalidated": assurance_invalidated,
        "stale_inspections": stale_inspections,
    }


def audit_node(
    project: str | Path,
    nid: str,
    actor: str,
    result_value: str,
    evidence_path: str | Path,
    expected_version: int | dict[str, Any] | None = None,
    expected_guard: str | None = None,
    *,
    ports: TaskPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    if result_value not in {"pass", "fail"}:
        raise PyramidError("audit result must be pass or fail")
    evidence = load_json(Path(evidence_path).expanduser().resolve())
    paths = project_paths(project)
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        require_active(state, "record an audit")
        nodes = node_map(plan)
        if nid not in nodes:
            raise PyramidError(f"Unknown node: {nid}")
        _, baseline, assurance = load_assurance_bundle(paths, plan)
        frontier = implementation_frontier(paths)
        if expected_guard is not None:
            check_expected_guard(
                audit_mutation_guard(
                    plan, state, nid, baseline, assurance, frontier
                ),
                expected_guard,
                "audit",
            )
        else:
            check_expected_version(plan, state, expected_version)
        if result_value == "pass":
            evidence = _normalize_proofs(paths, plan, state, nid, evidence)
            prerequisite_errors = _audit_prerequisite_errors(plan, state, nodes[nid])
            prerequisite_errors.extend(_audit_proof_dependencies(paths, plan, state, nodes[nid]))
            prerequisite_errors.extend(
                _assurance_audit_errors(paths, plan, state, nodes[nid], evidence)
            )
            if prerequisite_errors:
                raise PyramidError("Audit prerequisites are not satisfied:\n- " + "\n- ".join(prerequisite_errors))
        elif evidence.get("proofs"):
            raise PyramidError("Record failed observations in checks; failed audits cannot publish passing proof runs")
        evidence_errors = _validate_audit_result(evidence, nid, result_value)
        if evidence_errors:
            raise PyramidError("Invalid audit result:\n- " + "\n- ".join(evidence_errors))
        item = state["nodes"][nid]
        if item.get("execution") == "paused":
            raise PyramidError(f"{nid} is paused; resume it before recording an audit")
        before = copy.deepcopy(item)
        invalidated: list[str] = []
        stale_inspections: list[str] = []
        item["verification"] = "passed" if result_value == "pass" else "failed"
        item["health"] = "clear" if result_value == "pass" else "at-risk"
        item["blocker"] = None if result_value == "pass" else "Audit failed; repair, approved expansion, or replan is required."
        if result_value == "fail":
            if nodes[nid]["kind"] in EXECUTABLE_KINDS:
                item["execution"] = "needs-rework"
                item["owner"] = None
                item["lease_expires_at"] = None
                item["work_origin"] = None
            invalidated = ports.invalidate_claims(
                plan,
                state,
                nid,
                f"Evidence for {nid} failed; dependent verification is stale.",
            )
            stale_inspections = _invalidate_assurance_for_change(
                paths,
                plan,
                {nid},
                actor,
                f"Audit failure for {nid} invalidated prior inspection evidence.",
            )
        item["last_audit"] = evidence
        item["updated_at"] = ports.clock()
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type=f"audit.{result_value}",
            node=nid,
            before=before,
            after=copy.deepcopy(item),
            payload={
                "audit": evidence,
                "invalidated": invalidated,
                "stale_inspections": stale_inspections,
            },
        )
    ports.compile_project(project)
    paths, plan, state = ports.read_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    frontier = implementation_frontier(paths)
    response = {
        "status": result_value,
        "event": event,
        "packet": task_packet(plan, state, nid, baseline, assurance, frontier),
        "invalidated": invalidated,
        "stale_inspections": stale_inspections,
    }
    if result_value == "pass" and nid == plan["intent"]["id"]:
        response["next_action"] = "close"
    return response


def amend_task(
    project: str | Path,
    proposal_path: str | Path,
    actor: str,
    apply: bool = False,
    expected_amendment: str | None = None,
    *,
    ports: TaskPorts | None = None,
) -> dict[str, Any]:
    """Extend one live owner's implementation context without replacing its contract."""
    ports = ports or default_ports()
    proposal = load_json(Path(proposal_path).expanduser().resolve())
    paths = project_paths(project)
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        require_active(state, "amend work")
        try:
            candidate, additions = prepare_amendment(plan, proposal)
        except ValueError as exc:
            raise PyramidError(str(exc)) from exc
        nid = proposal["task"]
        nodes = node_map(plan)
        node, item = nodes[nid], state["nodes"][nid]
        if node["kind"] not in EXECUTABLE_KINDS or node["selection"] != "primary":
            raise PyramidError("Only primary executable tasks can be amended")
        if item["execution"] != "working" or item.get("owner") != actor:
            raise PyramidError("Only the working task owner may amend; resume or claim first")
        expiry = ports.parse_time(item.get("lease_expires_at"))
        if expiry is None or expiry <= ports.date_type.now(timezone.utc):
            raise PyramidError("Amendment requires an unexpired ownership lease")
        manifest, baseline, assurance = load_assurance_bundle(paths, plan)
        for value in additions["allowed_write_scope"] + additions["required_context"]:
            path = paths["root"] / value
            if not path.is_file() or path.resolve() != path or not path.resolve().is_relative_to(paths["root"]):
                raise PyramidError(f"Amendments require existing, non-symlink repository files: {value}")
        writes = additions["allowed_write_scope"]
        for value in writes:
            if _path_matches(value, node["agent"]["allowed_write_scope"]):
                raise PyramidError(f"Write path is already permitted; no amendment needed: {value}")
        if writes and node["agent"].get("effect") == "evidence-only":
            raise PyramidError("Evidence-only write-scope changes require replan")
        try:
            validate_amendment_inputs(paths["root"], candidate, nid, writes)
        except VerificationError as exc:
            raise PyramidError(str(exc)) from exc
        for other_id, other in nodes.items():
            if other_id == nid or state["nodes"][other_id]["execution"] not in {"working", "paused"}:
                continue
            scopes = _task_scopes(other)
            if writes and (not scopes or any(_patterns_overlap(path, scope) for path in writes for scope in scopes)):
                raise PyramidError(f"Amendment conflicts with active task {other_id}; resolve ownership first")
        if writes and manifest and manifest.get("mode") == "brownfield":
            mapped = {
                impact["asset_id"] for impact in (assurance or {}).get("impacts", [])
                if nid in impact.get("task_ids", []) and impact.get("status") != "dismissed"
            }
            for value in writes:
                assets = set(asset_ids_for_file(baseline or {}, value))
                if not assets or not assets.issubset(mapped):
                    raise PyramidError(f"Amendment {value} needs impact mapping before extending scope")
        errors = validate_plan(candidate)
        if errors:
            raise PyramidError("Invalid amendment candidate:\n- " + "\n- ".join(errors))
        amendment_id = "AMEND-" + canonical_sha256({
            "context": context_identity(plan, state), "proposal": proposal, "actor": actor,
            "baseline": baseline, "assurance": assurance,
        })
        response = {
            "status": "preview", "task": nid, "context": context_identity(plan, state),
            "amendment_id": amendment_id, "additions": additions,
            "reason": proposal["reason"], "boundary_review": proposal["boundary_review"],
            "warnings": ["Boundary review is an agent assertion, not runtime proof of unchanged authority or sufficient verification."]
                        + (["Scope additions conservatively stale affected brownfield inspections."] if writes else []),
        }
        if not apply:
            return response
        if not expected_amendment or expected_amendment != amendment_id:
            raise PyramidError("Stale or missing amendment preview token; preview again before applying")
        before = {field: copy.deepcopy(node["agent"][field]) for field in additions}
        write_json(paths["plan"], candidate)
        stale = _invalidate_assurance_for_change(
            paths, candidate, {nid}, actor, f"Task {nid} write scope amended; review affected evidence."
        ) if writes else []
        item["updated_at"] = ports.clock()
        event = ports.commit(
            paths, state, actor=actor, event_type="task.amended", node=nid,
            before=before,
            after={field: node_map(candidate)[nid]["agent"][field] for field in additions},
            payload={"reason": proposal["reason"], "amendment": proposal,
                     "amendment_id": amendment_id, "stale_inspections": stale},
        )
        ports.compile_locked(project)
        _, baseline, assurance = load_assurance_bundle(paths, candidate)
        response.update({
            "status": "applied", "context": context_identity(candidate, state),
            "event": event, "stale_inspections": stale,
            "mutation_guard": task_mutation_guard(candidate, state, nid, baseline, assurance),
            "owner": item["owner"], "lease_expires_at": item["lease_expires_at"],
            "graph_version": state["graph_version"],
        })
        return response


def reopen_node(
    project: str | Path,
    nid: str,
    actor: str,
    reason: str,
    evidence_path: str | Path | None = None,
    expected_version: int | dict[str, Any] | None = None,
    *,
    ports: TaskPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    if not reason.strip():
        raise PyramidError("reopen requires a non-empty reason")
    evidence: dict[str, Any] | None = None
    evidence_reference: str | None = None
    if evidence_path:
        resolved = Path(evidence_path).expanduser().resolve()
        evidence = load_json(resolved)
        evidence_reference = str(resolved)
    paths = project_paths(project)
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        check_expected_version(plan, state, expected_version)
        status = lifecycle_status(state)
        if status == "archived":
            raise PyramidError("Cannot reopen work in an archived plan; restore it first")
        nodes = node_map(plan)
        if nid not in nodes:
            raise PyramidError(f"Unknown node: {nid}")
        node = nodes[nid]
        if node["kind"] not in EXECUTABLE_KINDS:
            raise PyramidError(f"{nid} is not executable; reopen the affected executable claim or replan")
        if node["selection"] != "primary":
            raise PyramidError(f"{nid} is not on the primary path")
        item = state["nodes"][nid]
        if item["execution"] in {"working", "paused"}:
            raise PyramidError(f"{nid} has active working or paused context; resolve it before reopening")
        lifecycle = lifecycle_state(state)
        before = {"node": copy.deepcopy(item), "lifecycle": copy.deepcopy(lifecycle)}
        reactivated = status == "completed"
        if reactivated:
            lifecycle.update(
                {
                    "status": "active",
                    "completed_at": None,
                    "completed_by": None,
                    "completion_report": None,
                    "change_dossier": None,
                }
            )
        timestamp = ports.clock()
        item.update(
            {
                "execution": "needs-rework",
                "verification": "failed",
                "health": "at-risk",
                "owner": None,
                "lease_expires_at": None,
                "work_origin": None,
                "blocker": reason,
                "updated_at": timestamp,
                "last_reopen": {
                    "at": timestamp,
                    "actor": actor,
                    "reason": reason,
                    "evidence": evidence_reference,
                },
            }
        )
        invalidated = ports.invalidate_claims(
            plan,
            state,
            nid,
            f"{nid} was reopened; dependent verification must be repeated.",
        )
        stale_inspections = _invalidate_assurance_for_change(
            paths,
            plan,
            {nid},
            actor,
            f"{nid} was reopened; prior change-assurance evidence is stale.",
        )
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type="task.reopened",
            node=nid,
            before=before,
            after={"node": copy.deepcopy(item), "lifecycle": copy.deepcopy(lifecycle)},
            payload={
                "reason": reason,
                "evidence_path": evidence_reference,
                "evidence": evidence,
                "invalidated": invalidated,
                "stale_inspections": stale_inspections,
                "plan_reactivated": reactivated,
            },
        )
    compiled = ports.compile_project(project)
    paths, plan, state = ports.read_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    frontier = implementation_frontier(paths)
    return {
        "status": "reopened",
        "event": event,
        "invalidated": invalidated,
        "stale_inspections": stale_inspections,
        "plan_reactivated": reactivated,
        "packet": task_packet(plan, state, nid, baseline, assurance, frontier),
        **compiled,
    }
