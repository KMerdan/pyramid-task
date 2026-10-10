"""Deterministic state, context and guard rules over supplied values.

No project I/O or current clock. lifecycle_state, clear_active_pause and
invalidate_dependent_claims retain their declared in-place argument changes.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from collections import defaultdict, deque
from typing import Any
from pyramid_errors import PyramidError
from pyramid_graph import (AUDIT_BLOCKING, EXECUTION_STATES, HEALTH_STATES,
    PLAN_LIFECYCLE_STATES, VERIFICATION_STATES, edges_from, edges_to, node_map)
from pyramid_assurance_rules import assurance_blockers
from pyramid_verification import validate_proof_bindings

SCHEMA_VERSION = 1


def default_lifecycle() -> dict[str, Any]:
    return {
        "status": "active",
        "completed_at": None,
        "completed_by": None,
        "completion_report": None,
        "change_dossier": None,
        "archived_at": None,
        "archived_by": None,
        "archived_from_status": None,
        "archive_id": None,
        "archive_path": None,
        "restored_from": None,
    }


def lifecycle_state(state: dict[str, Any]) -> dict[str, Any]:
    lifecycle = state.setdefault("lifecycle", {})
    for key, value in default_lifecycle().items():
        lifecycle.setdefault(key, value)
    return lifecycle


def lifecycle_status(state: dict[str, Any]) -> str:
    lifecycle = state.get("lifecycle")
    return lifecycle.get("status", "active") if isinstance(lifecycle, dict) else "active"


def require_active(state: dict[str, Any], action: str) -> None:
    status = lifecycle_status(state)
    if status != "active":
        remedy = "reopen affected work" if status == "completed" else "restore or reset the archived plan"
        raise PyramidError(f"Cannot {action} while plan lifecycle is {status}; {remedy} first")


def active_claims(state: dict[str, Any]) -> list[str]:
    return sorted(
        nid
        for nid, item in state.get("nodes", {}).items()
        if item.get("execution") in {"working", "paused"} or item.get("owner")
    )


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_context_id(plan: dict[str, Any], state: dict[str, Any]) -> str:
    state_material = copy.deepcopy(state)
    state_material.pop("context_id", None)
    material = {"plan": plan, "state": state_material}
    return "CTX-" + canonical_sha256(material)[:32].upper()


def context_identity(plan: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": state.get("context_id") or canonical_context_id(plan, state),
        "plan_id": plan["plan_id"],
        "plan_revision": plan["revision"],
        "graph_version": state["graph_version"],
    }


def _guard_token(kind: str, material: dict[str, Any]) -> str:
    return f"GUARD-{kind.upper()}-" + canonical_sha256(material)[:32].upper()


def task_mutation_guard(
    plan: dict[str, Any],
    state: dict[str, Any],
    nid: str,
    baseline: dict[str, Any] | None,
    assurance: dict[str, Any] | None,
) -> str:
    nodes = node_map(plan)
    node = nodes[nid]
    dependency_ids = sorted(
        edge["to"] for edge in edges_from(plan, nid, AUDIT_BLOCKING)
    )
    impacts = []
    if assurance is not None:
        impacts = [
            item
            for item in assurance.get("impacts", [])
            if nid in item.get("task_ids", []) and item.get("status") != "dismissed"
        ]
    material = {
        "plan_id": plan["plan_id"],
        "plan_revision": plan["revision"],
        "node": node,
        "node_state": state["nodes"][nid],
        "dependency_states": {
            dep: state["nodes"][dep] for dep in dependency_ids
        },
        "lifecycle": lifecycle_state(state),
        "baseline": baseline,
        "impacts": impacts,
    }
    return _guard_token("task", material)


def audit_mutation_guard(
    plan: dict[str, Any],
    state: dict[str, Any],
    nid: str,
    baseline: dict[str, Any] | None,
    assurance: dict[str, Any] | None,
    frontier: dict[str, dict[str, Any]],
) -> str:
    node = node_map(plan)[nid]
    covered_tasks = _covered_assurance_tasks(plan, node)
    relevant_assurance: dict[str, Any] | None = None
    if assurance is not None:
        full = nid == plan["intent"]["id"]
        impacts = [
            item
            for item in assurance.get("impacts", [])
            if item.get("status") != "dismissed"
            and (full or covered_tasks.intersection(item.get("task_ids", [])))
        ]
        assets = {item.get("asset_id") for item in impacts}
        relevant_assurance = {
            "status": assurance.get("status") if full else None,
            "impacts": impacts,
            "inspections": [
                item
                for item in assurance.get("inspections", [])
                if assets.intersection(item.get("asset_ids", []))
                and (
                    full
                    or not item.get("task_ids")
                    or covered_tasks.intersection(item.get("task_ids", []))
                )
            ],
            "findings": [
                item
                for item in assurance.get("findings", [])
                if assets.intersection(item.get("asset_ids", []))
            ],
            "scope_drift": [
                item
                for item in assurance.get("scope_drift", [])
                if full or item.get("task") in covered_tasks
            ],
            "controls": assurance.get("controls") if full else None,
            "legacy_bridge": assurance.get("legacy_bridge") if full else None,
        }
    material = {
        "plan_id": plan["plan_id"],
        "plan_revision": plan["revision"],
        "node": node,
        "covered_states": {
            task: state["nodes"][task] for task in sorted(covered_tasks)
        },
        "lifecycle": lifecycle_state(state),
        "baseline": baseline,
        "assurance": relevant_assurance,
        "implementation_frontier": {
            task: frontier[task]
            for task in sorted(covered_tasks)
            if task in frontier
        },
    }
    return _guard_token("audit", material)


def check_expected_guard(actual: str, expected: str | None, label: str) -> None:
    if expected is not None and actual != expected:
        raise PyramidError(
            f"Stale {label} guard: expected {expected}, current {actual}. "
            "Refresh only this task or audit packet; unrelated global history may still be current."
        )


def initial_node_state(node: dict[str, Any], timestamp: str) -> dict[str, Any]:
    superseded = node.get("selection") == "superseded"
    return {
        "execution": "superseded" if superseded else "planned",
        "verification": "unverified",
        "health": "clear",
        "owner": None,
        "lease_expires_at": None,
        "work_origin": None,
        "active_handoff_id": None,
        "paused_at": None,
        "paused_by": None,
        "pause_mode": None,
        "resume_deadline": None,
        "last_handoff": None,
        "blocker": None,
        "updated_at": timestamp,
        "last_result": None,
        "last_audit": None,
        "last_reopen": None,
    }


def clear_active_pause(item: dict[str, Any]) -> None:
    item["active_handoff_id"] = None
    item["paused_at"] = None
    item["paused_by"] = None
    item["pause_mode"] = None
    item["resume_deadline"] = None


def validate_state(plan: dict[str, Any], state: dict[str, Any]) -> list[str]:
    errors: list[str] = validate_proof_bindings(plan, state)
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"state.schema_version must be {SCHEMA_VERSION}")
    if not isinstance(state.get("graph_version"), int) or state["graph_version"] < 1:
        errors.append("state.graph_version must be a positive integer")
    if state.get("context_id") is not None and (
        not isinstance(state["context_id"], str)
        or not re.fullmatch(r"CTX-[A-F0-9]{32}", state["context_id"])
    ):
        errors.append("state.context_id must be a CTX-prefixed 128-bit hexadecimal identity")
    lifecycle = state.get("lifecycle")
    if lifecycle is not None:
        if not isinstance(lifecycle, dict):
            errors.append("state.lifecycle must be an object")
        elif lifecycle.get("status") not in PLAN_LIFECYCLE_STATES:
            errors.append("state.lifecycle.status must be active, completed, or archived")
        elif lifecycle.get("status") == "completed" and not all(
            lifecycle.get(field) for field in ("completed_at", "completed_by", "completion_report")
        ):
            errors.append("completed lifecycle requires completed_at, completed_by, and completion_report")
        elif lifecycle.get("status") == "archived" and not all(
            lifecycle.get(field) for field in ("archived_at", "archived_by", "archived_from_status", "archive_id", "archive_path")
        ):
            errors.append("archived lifecycle requires archive identity, provenance, actor, and timestamp")
    node_states = state.get("nodes")
    if not isinstance(node_states, dict):
        return errors + ["state.nodes must be an object"]
    plan_ids = {node["id"] for node in plan["nodes"]}
    for nid in sorted(plan_ids - set(node_states)):
        errors.append(f"state is missing node {nid}")
    for nid in sorted(set(node_states) - plan_ids):
        errors.append(f"state contains unknown node {nid}")
    for nid, item in node_states.items():
        if not isinstance(item, dict):
            errors.append(f"state for {nid} must be an object")
            continue
        if item.get("execution") not in EXECUTION_STATES:
            errors.append(f"{nid}: invalid execution state")
        if item.get("verification") not in VERIFICATION_STATES:
            errors.append(f"{nid}: invalid verification state")
        if item.get("health") not in HEALTH_STATES:
            errors.append(f"{nid}: invalid health state")
        execution = item.get("execution")
        if execution == "working" and not item.get("owner"):
            errors.append(f"{nid}: working node needs an owner")
        if execution == "paused":
            if not item.get("active_handoff_id"):
                errors.append(f"{nid}: paused node needs an active_handoff_id")
            if not item.get("paused_at") or not item.get("paused_by"):
                errors.append(f"{nid}: paused node needs pause provenance")
            mode = item.get("pause_mode")
            if mode not in {"hold", "handoff"}:
                errors.append(f"{nid}: paused node needs pause_mode hold or handoff")
            if mode == "hold":
                if not item.get("owner"):
                    errors.append(f"{nid}: hold pause must retain its owner")
                elif item.get("owner") != item.get("paused_by"):
                    errors.append(f"{nid}: hold pause owner must match paused_by")
                if not item.get("resume_deadline"):
                    errors.append(f"{nid}: hold pause needs a resume deadline")
                elif item.get("lease_expires_at") != item.get("resume_deadline"):
                    errors.append(f"{nid}: hold lease must expire at its resume deadline")
            elif item.get("owner"):
                errors.append(f"{nid}: handoff pause must not retain an owner")
        elif execution != "working":
            if item.get("owner"):
                errors.append(f"{nid}: only working or hold-paused nodes may have an owner")
            if item.get("active_handoff_id"):
                errors.append(f"{nid}: only paused nodes may have an active_handoff_id")
    if lifecycle_status(state) in {"completed", "archived"} and active_claims(state):
        errors.append(f"{lifecycle_status(state)} plans cannot contain active claims")
    return errors


def completion_errors(
    plan: dict[str, Any],
    state: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    assurance: dict[str, Any] | None = None,
    frontier: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    intent_id = plan["intent"]["id"]
    if state["nodes"][intent_id]["verification"] != "passed":
        errors.append(f"Final intent {intent_id} has not passed its audit")
    incomplete = sorted(
        node["id"]
        for node in plan["nodes"]
        if node["selection"] == "primary" and state["nodes"][node["id"]]["verification"] != "passed"
    )
    if incomplete:
        errors.append("Primary nodes are not verified: " + ", ".join(incomplete))
    claims = active_claims(state)
    if claims:
        errors.append("Active claims remain: " + ", ".join(claims))
    unhealthy = sorted(
        node["id"]
        for node in plan["nodes"]
        if node["selection"] == "primary" and state["nodes"][node["id"]]["health"] != "clear"
    )
    if unhealthy:
        errors.append("Primary nodes are not clear: " + ", ".join(unhealthy))
    if baseline is not None and assurance is not None:
        errors.extend(
            assurance_blockers(
                baseline,
                assurance,
                full=True,
                implementation_frontier=frontier,
            )
        )
    return errors


def check_expected_version(
    plan: dict[str, Any],
    state: dict[str, Any],
    expected: int | dict[str, Any] | None,
) -> None:
    expected_version = expected.get("graph_version") if isinstance(expected, dict) else expected
    expected_context = expected.get("context_id") if isinstance(expected, dict) else None
    if expected_version is not None and state["graph_version"] != expected_version:
        raise PyramidError(
            f"Stale graph version: expected {expected_version}, current {state['graph_version']}"
        )
    current_context = state.get("context_id") or canonical_context_id(plan, state)
    if expected_context is not None and current_context != expected_context:
        raise PyramidError(f"Stale context: expected {expected_context}, current {current_context}")


def _covered_assurance_tasks(plan: dict[str, Any], node: dict[str, Any]) -> set[str]:
    nid = node["id"]
    if node["kind"] == "intent":
        return {item["id"] for item in plan["nodes"] if item.get("selection") == "primary"}
    if node["kind"] == "audit":
        covered = {edge["to"] for edge in edges_from(plan, nid, AUDIT_BLOCKING)}
        queue = deque(covered)
        while queue:
            current = queue.popleft()
            for edge in edges_from(plan, current, AUDIT_BLOCKING):
                if edge["to"] not in covered:
                    covered.add(edge["to"])
                    queue.append(edge["to"])
        return covered or {nid}
    if node["kind"] in {"outcome", "capability", "work-package"}:
        covered = {edge["from"] for edge in edges_to(plan, nid, {"contributes-to"})}
        queue = deque(covered)
        while queue:
            current = queue.popleft()
            for edge in edges_to(plan, current, {"contributes-to"}):
                if edge["from"] not in covered:
                    covered.add(edge["from"])
                    queue.append(edge["from"])
        return covered or {nid}
    return {nid}


def dependent_claims(plan: dict[str, Any], origin: str) -> list[str]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in plan["edges"]:
        source, target, edge_type = edge["from"], edge["to"], edge["type"]
        if edge_type == "contributes-to":
            adjacency[source].add(target)
        elif edge_type in AUDIT_BLOCKING:
            adjacency[target].add(source)
        elif edge_type == "validated-by":
            adjacency[source].add(target)
            adjacency[target].add(source)
    queue = deque([origin])
    seen = {origin}
    while queue:
        current = queue.popleft()
        for affected in sorted(adjacency.get(current, set())):
            if affected not in seen:
                seen.add(affected)
                queue.append(affected)
    return sorted(seen - {origin})


def invalidate_dependent_claims(
    plan: dict[str, Any],
    state: dict[str, Any],
    origin: str,
    reason: str,
    *,
    timestamp: str,
) -> list[str]:
    invalidated: list[str] = []
    for nid in dependent_claims(plan, origin):
        item = state["nodes"][nid]
        if item["verification"] == "unverified" and item["execution"] == "planned":
            continue
        item["verification"] = "pending" if item["execution"] == "implemented" else "unverified"
        item["health"] = "at-risk"
        item["blocker"] = reason
        item["updated_at"] = timestamp
        invalidated.append(nid)
    return invalidated
