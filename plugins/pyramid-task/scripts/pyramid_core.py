from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


SCHEMA_VERSION = 1
NODE_KINDS = {
    "intent",
    "outcome",
    "capability",
    "decision",
    "research",
    "contract",
    "implementation",
    "integration",
    "risk-control",
    "audit",
}
EXECUTABLE_KINDS = {
    "research",
    "contract",
    "implementation",
    "integration",
    "risk-control",
    "audit",
}
SELECTIONS = {"primary", "alternative", "rejected", "superseded"}
EDGE_TYPES = {
    "contributes-to",
    "requires",
    "contract-requires",
    "integration-requires",
    "validation-requires",
    "validated-by",
    "alternative-to",
    "invalidates",
}
START_BLOCKING = {"requires", "contract-requires"}
AUDIT_BLOCKING = {
    "requires",
    "contract-requires",
    "integration-requires",
    "validation-requires",
}
EXECUTION_STATES = {"planned", "working", "implemented", "needs-rework", "superseded"}
VERIFICATION_STATES = {"unverified", "pending", "passed", "failed"}
HEALTH_STATES = {"clear", "at-risk", "blocked"}
PLAN_LIFECYCLE_STATES = {"active", "completed", "archived"}
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]*$")


class PyramidError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PyramidError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PyramidError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PyramidError(f"Expected a JSON object in {path}")
    return data


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=False)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def project_paths(project: str | Path) -> dict[str, Path]:
    root = Path(project).expanduser().resolve()
    meta = root / ".pyramid"
    return {
        "root": root,
        "meta": meta,
        "plan": meta / "plan.json",
        "state": meta / "state.json",
        "graph": meta / "graph.json",
        "ready": meta / "ready.json",
        "events": meta / "events",
        "reports": meta / "reports",
        "archives": meta / "archives",
        "lock": meta / "lock",
        "docs": root / "docs" / "tasks",
        "html": meta / "pyramid.html",
    }


def default_lifecycle() -> dict[str, Any]:
    return {
        "status": "active",
        "completed_at": None,
        "completed_by": None,
        "completion_report": None,
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
        if item.get("execution") == "working" or item.get("owner")
    )


@contextmanager
def project_lock(paths: dict[str, Path]):
    paths["meta"].mkdir(parents=True, exist_ok=True)
    with paths["lock"].open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _cycle(nodes: Iterable[str], adjacency: dict[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            start = stack.index(node)
            return stack[start:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for target in adjacency.get(node, []):
            found = visit(target)
            if found:
                return found
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in nodes:
        found = visit(node)
        if found:
            return found
    return None


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_top = {
        "schema_version",
        "plan_id",
        "title",
        "revision",
        "intent",
        "evidence",
        "decisions",
        "nodes",
        "edges",
    }
    missing = sorted(required_top - set(plan))
    if missing:
        errors.append(f"Missing top-level fields: {', '.join(missing)}")
        return errors
    if plan.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(plan.get("plan_id"), str) or not plan["plan_id"].strip():
        errors.append("plan_id must be a non-empty string")
    if not isinstance(plan.get("title"), str) or not plan["title"].strip():
        errors.append("title must be a non-empty string")
    if not isinstance(plan.get("revision"), int) or plan["revision"] < 1:
        errors.append("revision must be a positive integer")

    intent = plan.get("intent")
    if not isinstance(intent, dict):
        errors.append("intent must be an object")
        return errors
    for field in ("id", "statement", "success_evidence", "constraints", "non_goals", "assumptions"):
        if field not in intent:
            errors.append(f"intent is missing {field}")
    intent_id = intent.get("id")
    if not isinstance(intent_id, str) or not ID_PATTERN.match(intent_id):
        errors.append("intent.id must be an uppercase stable ID")
    if not isinstance(intent.get("statement"), str) or not intent.get("statement", "").strip():
        errors.append("intent.statement must be non-empty")
    if not _is_string_list(intent.get("constraints")):
        errors.append("intent.constraints must be a string array")
    if not _is_string_list(intent.get("non_goals")):
        errors.append("intent.non_goals must be a string array")

    success = intent.get("success_evidence")
    success_ids: set[str] = set()
    if not isinstance(success, list) or not success:
        errors.append("intent.success_evidence must be a non-empty array")
    else:
        for index, item in enumerate(success):
            if not isinstance(item, dict):
                errors.append(f"intent.success_evidence[{index}] must be an object")
                continue
            sid = item.get("id")
            if not isinstance(sid, str) or not ID_PATTERN.match(sid):
                errors.append(f"intent.success_evidence[{index}].id is invalid")
            elif sid in success_ids:
                errors.append(f"Duplicate success evidence ID: {sid}")
            else:
                success_ids.add(sid)
            if not isinstance(item.get("description"), str) or not item["description"].strip():
                errors.append(f"Success evidence {sid or index} needs a description")

    nodes = plan.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append("nodes must be a non-empty array")
        return errors
    node_map: dict[str, dict[str, Any]] = {}
    criterion_ids: set[str] = set()
    requirement_ids: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{index}] must be an object")
            continue
        nid = node.get("id")
        if not isinstance(nid, str) or not ID_PATTERN.match(nid):
            errors.append(f"nodes[{index}].id is invalid")
            continue
        if nid in node_map:
            errors.append(f"Duplicate node ID: {nid}")
            continue
        node_map[nid] = node
        if node.get("kind") not in NODE_KINDS:
            errors.append(f"{nid}: invalid kind {node.get('kind')!r}")
        if node.get("selection") not in SELECTIONS:
            errors.append(f"{nid}: invalid selection {node.get('selection')!r}")
        for field in ("title", "summary", "workstream"):
            if not isinstance(node.get(field), str) or not node[field].strip():
                errors.append(f"{nid}: {field} must be non-empty")
        for field in ("level", "wave"):
            if not isinstance(node.get(field), int) or node[field] < 0:
                errors.append(f"{nid}: {field} must be a non-negative integer")
        source_requirements = node.get("source_requirements")
        if not _is_string_list(source_requirements):
            errors.append(f"{nid}: source_requirements must be a string array")
        else:
            for requirement in source_requirements:
                requirement_ids.add(requirement)
                if requirement not in success_ids:
                    errors.append(f"{nid}: unknown source requirement {requirement}")
        criteria = node.get("acceptance_criteria")
        if not isinstance(criteria, list):
            errors.append(f"{nid}: acceptance_criteria must be an array")
            criteria = []
        if node.get("kind") in EXECUTABLE_KINDS and not criteria:
            errors.append(f"{nid}: executable node needs acceptance criteria")
        for criterion in criteria:
            if not isinstance(criterion, dict):
                errors.append(f"{nid}: acceptance criterion must be an object")
                continue
            cid = criterion.get("id")
            if not isinstance(cid, str) or not ID_PATTERN.match(cid):
                errors.append(f"{nid}: invalid acceptance criterion ID")
            elif cid in criterion_ids:
                errors.append(f"Duplicate acceptance criterion ID: {cid}")
            else:
                criterion_ids.add(cid)
            if not isinstance(criterion.get("description"), str) or not criterion["description"].strip():
                errors.append(f"{nid}: criterion {cid or '?'} needs a description")
        evidence_requirements = node.get("required_evidence")
        if not isinstance(evidence_requirements, list):
            errors.append(f"{nid}: required_evidence must be an array")
            evidence_requirements = []
        for item in evidence_requirements:
            if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip() for k in ("id", "type", "description")):
                errors.append(f"{nid}: malformed required_evidence entry")
        agent = node.get("agent")
        if not isinstance(agent, dict):
            errors.append(f"{nid}: agent must be an object")
        else:
            for field in ("required_context", "allowed_write_scope", "commands", "deliverables", "non_goals"):
                if not _is_string_list(agent.get(field)):
                    errors.append(f"{nid}: agent.{field} must be a string array")
            if node.get("kind") in EXECUTABLE_KINDS and not agent.get("deliverables"):
                errors.append(f"{nid}: executable node needs at least one deliverable")

    if intent_id in node_map:
        intent_node = node_map[intent_id]
        if intent_node.get("kind") != "intent" or intent_node.get("level") != 0:
            errors.append("The intent node must have kind intent and level 0")
    else:
        errors.append("intent.id must match a node")
    intent_nodes = [node for node in node_map.values() if node.get("kind") == "intent"]
    if len(intent_nodes) != 1:
        errors.append("The plan must contain exactly one intent node")

    assumptions = intent.get("assumptions")
    if not isinstance(assumptions, list):
        errors.append("intent.assumptions must be an array")
    else:
        assumption_ids: set[str] = set()
        for item in assumptions:
            if not isinstance(item, dict):
                errors.append("Each assumption must be an object")
                continue
            aid = item.get("id")
            if not isinstance(aid, str) or not ID_PATTERN.match(aid):
                errors.append("Assumption ID is invalid")
            elif aid in assumption_ids:
                errors.append(f"Duplicate assumption ID: {aid}")
            else:
                assumption_ids.add(aid)
            if item.get("confidence") not in {"low", "medium", "high"}:
                errors.append(f"{aid or 'assumption'}: confidence must be low, medium, or high")
            validation_node = item.get("validation_node")
            if validation_node is not None and validation_node not in node_map:
                errors.append(f"{aid or 'assumption'}: unknown validation node {validation_node}")

    evidence = plan.get("evidence")
    evidence_ids: set[str] = set()
    if not isinstance(evidence, list):
        errors.append("evidence must be an array")
        evidence = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence[{index}] must be an object")
            continue
        eid = item.get("id")
        if not isinstance(eid, str) or not ID_PATTERN.match(eid):
            errors.append(f"evidence[{index}].id is invalid")
            continue
        if eid in evidence_ids:
            errors.append(f"Duplicate evidence ID: {eid}")
        evidence_ids.add(eid)
        if item.get("confidence") not in {"low", "medium", "high"}:
            errors.append(f"{eid}: confidence must be low, medium, or high")
        for field in ("claim", "source"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{eid}: {field} must be non-empty")
        for field in ("supports", "contradicts"):
            if not _is_string_list(item.get(field)):
                errors.append(f"{eid}: {field} must be a string array")
        for supported in item.get("supports", []):
            if supported not in node_map:
                errors.append(f"{eid}: supports unknown node {supported}")

    decisions = plan.get("decisions")
    decision_ids: set[str] = set()
    if not isinstance(decisions, list):
        errors.append("decisions must be an array")
        decisions = []
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            errors.append(f"decisions[{index}] must be an object")
            continue
        did = decision.get("id")
        if not isinstance(did, str) or not ID_PATTERN.match(did):
            errors.append(f"decisions[{index}].id is invalid")
            continue
        if did in decision_ids:
            errors.append(f"Duplicate decision ID: {did}")
        decision_ids.add(did)
        for field in ("question", "choice", "rationale"):
            if not isinstance(decision.get(field), str) or not decision[field].strip():
                errors.append(f"{did}: {field} must be non-empty")
        if not _is_string_list(decision.get("alternatives")):
            errors.append(f"{did}: alternatives must be a string array")
        if not _is_string_list(decision.get("evidence")):
            errors.append(f"{did}: evidence must be a string array")
        for eid in decision.get("evidence", []):
            if eid not in evidence_ids:
                errors.append(f"{did}: references unknown evidence {eid}")

    edges = plan.get("edges")
    if not isinstance(edges, list):
        errors.append("edges must be an array")
        edges = []
    seen_edges: set[tuple[str, str, str]] = set()
    hierarchy: dict[str, list[str]] = defaultdict(list)
    hard_dependencies: dict[str, list[str]] = defaultdict(list)
    contributing_children: dict[str, list[str]] = defaultdict(list)
    validators: dict[str, list[str]] = defaultdict(list)
    primary_ids = {nid for nid, node in node_map.items() if node.get("selection") == "primary"}
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edges[{index}] must be an object")
            continue
        source, target, edge_type = edge.get("from"), edge.get("to"), edge.get("type")
        if source not in node_map:
            errors.append(f"edges[{index}] has unknown source {source}")
        if target not in node_map:
            errors.append(f"edges[{index}] has unknown target {target}")
        if edge_type not in EDGE_TYPES:
            errors.append(f"edges[{index}] has invalid type {edge_type}")
        if source == target:
            errors.append(f"edges[{index}] is a self-edge")
        key = (source, target, edge_type)
        if key in seen_edges:
            errors.append(f"Duplicate edge: {source} --{edge_type}--> {target}")
        seen_edges.add(key)
        if source not in node_map or target not in node_map or edge_type not in EDGE_TYPES:
            continue
        if edge_type == "contributes-to":
            hierarchy[source].append(target)
            contributing_children[target].append(source)
            if source in primary_ids and target in primary_ids and node_map[source]["level"] <= node_map[target]["level"]:
                errors.append(f"{source}: contributes-to parent {target} must have a lower level")
        if edge_type in START_BLOCKING and source in primary_ids and target in primary_ids:
            hard_dependencies[source].append(target)
        if edge_type == "validated-by":
            validators[source].append(target)
            if target in node_map and node_map[target].get("kind") != "audit":
                errors.append(f"{source}: validated-by target {target} must be an audit node")

    hierarchy_cycle = _cycle(primary_ids, hierarchy)
    if hierarchy_cycle:
        errors.append(f"Hierarchy cycle: {' -> '.join(hierarchy_cycle)}")
    dependency_cycle = _cycle(primary_ids, hard_dependencies)
    if dependency_cycle:
        errors.append(f"Hard dependency cycle: {' -> '.join(dependency_cycle)}")

    if isinstance(intent_id, str) and intent_id in node_map:
        for nid in sorted(primary_ids - {intent_id}):
            queue = deque([nid])
            visited = {nid}
            reaches_intent = False
            while queue:
                current = queue.popleft()
                for parent in hierarchy.get(current, []):
                    if parent == intent_id:
                        reaches_intent = True
                        queue.clear()
                        break
                    if parent not in visited:
                        visited.add(parent)
                        queue.append(parent)
            if not reaches_intent:
                errors.append(f"{nid}: primary node does not trace to {intent_id}")

    for parent, children in contributing_children.items():
        primary_children = [child for child in children if child in primary_ids]
        if node_map[parent].get("selection") == "primary" and node_map[parent].get("kind") in {"intent", "outcome", "capability"} and len(primary_children) >= 2:
            if not any(gate in node_map and node_map[gate].get("selection") == "primary" for gate in validators.get(parent, [])):
                errors.append(f"{parent}: multi-branch joint needs a primary validated-by audit gate")

    uncovered = sorted(success_ids - requirement_ids)
    if uncovered:
        errors.append(f"Intent success evidence is not traced by nodes: {', '.join(uncovered)}")
    return errors


def initial_node_state(node: dict[str, Any], now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now()
    superseded = node.get("selection") == "superseded"
    return {
        "execution": "superseded" if superseded else "planned",
        "verification": "unverified",
        "health": "clear",
        "owner": None,
        "lease_expires_at": None,
        "work_origin": None,
        "blocker": None,
        "updated_at": timestamp,
        "last_result": None,
        "last_audit": None,
        "last_reopen": None,
    }


def validate_state(plan: dict[str, Any], state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"state.schema_version must be {SCHEMA_VERSION}")
    if not isinstance(state.get("graph_version"), int) or state["graph_version"] < 1:
        errors.append("state.graph_version must be a positive integer")
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
        if item.get("execution") == "working" and not item.get("owner"):
            errors.append(f"{nid}: working node needs an owner")
        if item.get("execution") != "working" and item.get("owner"):
            errors.append(f"{nid}: only working nodes may have an owner")
    if lifecycle_status(state) in {"completed", "archived"} and active_claims(state):
        errors.append(f"{lifecycle_status(state)} plans cannot contain active claims")
    return errors


def load_project(project: str | Path, check: bool = True) -> tuple[dict[str, Path], dict[str, Any], dict[str, Any]]:
    paths = project_paths(project)
    plan = load_json(paths["plan"])
    state = load_json(paths["state"])
    if check:
        errors = validate_plan(plan) + validate_state(plan, state)
        if errors:
            raise PyramidError("Project validation failed:\n- " + "\n- ".join(errors))
    return paths, plan, state


def node_map(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in plan["nodes"]}


def edges_from(plan: dict[str, Any], nid: str, types: set[str] | None = None) -> list[dict[str, Any]]:
    return [edge for edge in plan["edges"] if edge["from"] == nid and (types is None or edge["type"] in types)]


def edges_to(plan: dict[str, Any], nid: str, types: set[str] | None = None) -> list[dict[str, Any]]:
    return [edge for edge in plan["edges"] if edge["to"] == nid and (types is None or edge["type"] in types)]


def start_blockers(plan: dict[str, Any], state: dict[str, Any], node: dict[str, Any]) -> list[str]:
    edge_types = set(START_BLOCKING)
    if node["kind"] == "audit":
        edge_types |= {"integration-requires", "validation-requires"}
    return [
        edge["to"]
        for edge in edges_from(plan, node["id"], edge_types)
        if state["nodes"][edge["to"]]["verification"] != "passed"
    ]


def availability(plan: dict[str, Any], state: dict[str, Any], node: dict[str, Any]) -> str:
    item = state["nodes"][node["id"]]
    if item["verification"] == "passed":
        return "verified"
    if node["kind"] not in EXECUTABLE_KINDS:
        return "not-executable"
    if node["selection"] != "primary" or item["execution"] == "superseded":
        return "not-selected"
    if item["health"] == "blocked":
        return "blocked"
    if item["execution"] == "working":
        return "working"
    if item["execution"] == "implemented":
        return "implemented"
    if item["execution"] == "needs-rework":
        return "locked" if start_blockers(plan, state, node) else "needs-rework"
    if start_blockers(plan, state, node):
        return "locked"
    return "ready"


def goal_trace(plan: dict[str, Any], start: str) -> list[str]:
    intent_id = plan["intent"]["id"]
    if start == intent_id:
        return [start]
    parents: dict[str, list[str]] = defaultdict(list)
    for edge in plan["edges"]:
        if edge["type"] == "contributes-to":
            parents[edge["from"]].append(edge["to"])
    queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
    visited = {start}
    while queue:
        current, path = queue.popleft()
        for parent in sorted(parents.get(current, [])):
            if parent == intent_id:
                return path + [parent]
            if parent not in visited:
                visited.add(parent)
                queue.append((parent, path + [parent]))
    return [start]


def task_packet(plan: dict[str, Any], state: dict[str, Any], nid: str) -> dict[str, Any]:
    nodes = node_map(plan)
    if nid not in nodes:
        raise PyramidError(f"Unknown node: {nid}")
    node = nodes[nid]
    dependency_edges = edges_from(plan, nid, AUDIT_BLOCKING)
    dependencies = []
    for edge in dependency_edges:
        target = nodes[edge["to"]]
        target_state = state["nodes"][target["id"]]
        dependencies.append(
            {
                "id": target["id"],
                "title": target["title"],
                "type": edge["type"],
                "execution": target_state["execution"],
                "verification": target_state["verification"],
                "availability": availability(plan, state, target),
            }
        )
    gates = [edge["to"] for edge in edges_from(plan, nid, {"validated-by"})]
    item = state["nodes"][nid]
    return {
        "schema": "agent-task-v1",
        "task": nid,
        "graph_version": state["graph_version"],
        "title": node["title"],
        "purpose": node["summary"],
        "kind": node["kind"],
        "level": node["level"],
        "wave": node["wave"],
        "workstream": node["workstream"],
        "selection": node["selection"],
        "availability": availability(plan, state, node),
        "execution": item["execution"],
        "verification": item["verification"],
        "health": item["health"],
        "blocker": item["blocker"],
        "goal_trace": goal_trace(plan, nid),
        "dependencies": dependencies,
        "blocked_by": start_blockers(plan, state, node),
        "required_context": node["agent"]["required_context"],
        "allowed_write_scope": node["agent"]["allowed_write_scope"],
        "commands": node["agent"]["commands"],
        "deliverables": node["agent"]["deliverables"],
        "non_goals": node["agent"]["non_goals"],
        "acceptance_criteria": node["acceptance_criteria"],
        "required_evidence": node["required_evidence"],
        "audit_gates": gates,
        "owner": item["owner"],
        "lease_expires_at": item["lease_expires_at"],
        "completion_report_schema": "agent-result-v1",
    }


def completion_errors(plan: dict[str, Any], state: dict[str, Any]) -> list[str]:
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
    return errors


def graph_snapshot(plan: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    nodes = node_map(plan)
    enriched = []
    counts: dict[str, int] = defaultdict(int)
    for node in sorted(plan["nodes"], key=lambda item: (item["level"], item["wave"], item["id"])):
        nid = node["id"]
        item = copy.deepcopy(node)
        item["state"] = copy.deepcopy(state["nodes"][nid])
        item["availability"] = availability(plan, state, node)
        counts[item["availability"]] += 1
        item["blocked_by"] = start_blockers(plan, state, node)
        item["goal_trace"] = goal_trace(plan, nid)
        item["parents"] = [edge["to"] for edge in edges_from(plan, nid, {"contributes-to"})]
        item["children"] = [edge["from"] for edge in edges_to(plan, nid, {"contributes-to"})]
        item["dependencies"] = [
            {"id": edge["to"], "type": edge["type"], "verification": state["nodes"][edge["to"]]["verification"]}
            for edge in edges_from(plan, nid, AUDIT_BLOCKING)
        ]
        item["audit_gates"] = [edge["to"] for edge in edges_from(plan, nid, {"validated-by"})]
        item["evidence"] = [entry["id"] for entry in plan["evidence"] if nid in entry.get("supports", [])]
        enriched.append(item)
    primary = [node for node in enriched if node["selection"] == "primary"]
    verified = sum(node["state"]["verification"] == "passed" for node in primary)
    return {
        "schema": "pyramid-graph-v1",
        "generated_at": utc_now(),
        "graph_version": state["graph_version"],
        "plan_id": plan["plan_id"],
        "title": plan["title"],
        "revision": plan["revision"],
        "intent": plan["intent"],
        "lifecycle": copy.deepcopy(lifecycle_state(state)),
        "summary": {
            "primary_nodes": len(primary),
            "verified_primary_nodes": verified,
            "closure_ready": not completion_errors(plan, state),
            "availability": dict(sorted(counts.items())),
        },
        "nodes": enriched,
        "edges": copy.deepcopy(plan["edges"]),
        "evidence": copy.deepcopy(plan["evidence"]),
        "decisions": copy.deepcopy(plan["decisions"]),
    }


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def node_doc_path(paths: dict[str, Path], node: dict[str, Any]) -> Path:
    name = f"{node['id']}-{slugify(node['title'])}.md"
    if node["kind"] in EXECUTABLE_KINDS:
        folder = f"{node['wave']:02d}-{slugify(node['workstream'])}"
        return paths["docs"] / folder / name
    return paths["docs"] / "nodes" / name


def _markdown_list(values: list[str], empty: str = "None") -> str:
    return "\n".join(f"- {value}" for value in values) if values else f"- {empty}"


def render_node_markdown(paths: dict[str, Path], plan: dict[str, Any], state: dict[str, Any], node: dict[str, Any]) -> str:
    packet = task_packet(plan, state, node["id"])
    dependencies = [f"`{item['id']}` ({item['type']}, {item['verification']})" for item in packet["dependencies"]]
    criteria = [f"`{item['id']}` — {item['description']}" for item in node["acceptance_criteria"]]
    evidence = [f"`{item['id']}` ({item['type']}) — {item['description']}" for item in node["required_evidence"]]
    status = state["nodes"][node["id"]]
    return f"""<!-- Generated by Pyramid Task V2. Edit .pyramid/plan.json through create or replan, not this file. -->
# {node['id']}: {node['title']}

## Metadata

- Kind: `{node['kind']}`
- Level: `{node['level']}`
- Wave: `{node['wave']}`
- Workstream: `{node['workstream']}`
- Selection: `{node['selection']}`
- Execution: `{status['execution']}`
- Verification: `{status['verification']}`
- Health: `{status['health']}`
- Availability: `{packet['availability']}`
- Goal trace: {' → '.join(f'`{item}`' for item in packet['goal_trace'])}

## Goal

{node['summary']}

## Deliverables

{_markdown_list(node['agent']['deliverables'])}

## Allowed Write Scope

{_markdown_list(node['agent']['allowed_write_scope'])}

## Non-Goals

{_markdown_list(node['agent']['non_goals'])}

## Dependencies

{_markdown_list(dependencies)}

## Required Context

{_markdown_list(node['agent']['required_context'])}

## Validation Commands

{_markdown_list(node['agent']['commands'])}

## Acceptance Criteria

{_markdown_list(criteria)}

## Required Evidence

{_markdown_list(evidence)}

## Audit Gates

{_markdown_list([f'`{gate}`' for gate in packet['audit_gates']])}
"""


def compile_project(project: str | Path, *, allow_archived: bool = False) -> dict[str, Any]:
    paths, plan, state = load_project(project)
    if lifecycle_status(state) == "archived" and not allow_archived:
        raise PyramidError("Archived plans are frozen; use their existing projections or restore the plan")
    snapshot = graph_snapshot(plan, state)
    by_id = node_map(plan)
    for item in snapshot["nodes"]:
        item["source_path"] = str(node_doc_path(paths, by_id[item["id"]]).relative_to(paths["root"]))
    write_json(paths["graph"], snapshot)
    ready_packets = [
        task_packet(plan, state, node["id"])
        for node in plan["nodes"]
        if availability(plan, state, node) in {"ready", "needs-rework"}
    ]
    ready_packets.sort(key=lambda item: (item["wave"], item["level"], item["task"]))
    write_json(
        paths["ready"],
        {"schema": "pyramid-ready-v1", "graph_version": state["graph_version"], "tasks": ready_packets},
    )

    paths["docs"].mkdir(parents=True, exist_ok=True)
    for node in plan["nodes"]:
        path = node_doc_path(paths, node)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_node_markdown(paths, plan, state, node), encoding="utf-8")

    intent = plan["intent"]
    intent_text = f"""<!-- Generated by Pyramid Task V2. -->
# Intent: {plan['title']}

{intent['statement']}

## Success Evidence

{_markdown_list([f"`{item['id']}` — {item['description']}" for item in intent['success_evidence']])}

## Constraints

{_markdown_list(intent['constraints'])}

## Non-Goals

{_markdown_list(intent['non_goals'])}

## Assumptions

{_markdown_list([f"`{item['id']}` ({item['confidence']}) — {item['statement']}" for item in intent['assumptions']])}
"""
    (paths["docs"] / "INTENT.md").write_text(intent_text, encoding="utf-8")

    executable = [node for node in plan["nodes"] if node["kind"] in EXECUTABLE_KINDS]
    batches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in executable:
        batches[f"{node['wave']:02d}-{slugify(node['workstream'])}"].append(node)
    for folder, batch_nodes in batches.items():
        lines = [f"# Batch {folder}\n", "## Tasks\n"]
        for node in sorted(batch_nodes, key=lambda item: item["id"]):
            lines.append(f"- [`{node['id']}`]({node_doc_path(paths, node).name}) — {node['title']}")
        lines.extend(["", "## Parallelism", "", "Use the ready index; tasks in the same batch are parallel only when their typed dependencies are verified.", ""])
        (paths["docs"] / folder / "README.md").write_text("\n".join(lines), encoding="utf-8")

    summary = snapshot["summary"]
    readme_lines = [
        "<!-- Generated by Pyramid Task V2. -->",
        f"# {plan['title']}",
        "",
        intent["statement"],
        "",
        "## Current State",
        "",
        f"- Graph version: `{state['graph_version']}`",
        f"- Plan revision: `{plan['revision']}`",
        f"- Lifecycle: `{lifecycle_status(state)}`",
        f"- Verified primary nodes: `{summary['verified_primary_nodes']}/{summary['primary_nodes']}`",
        f"- Ready tasks: `{len(ready_packets)}`",
        "",
        "## Ready Frontier",
        "",
    ]
    readme_lines.extend([f"- `{packet['task']}` — {packet['title']}" for packet in ready_packets] or ["- None"])
    readme_lines.extend(["", "## Batch Order", ""])
    readme_lines.extend([f"- [`{folder}`]({folder}/README.md)" for folder in sorted(batches)] or ["- No executable batches"])
    readme_lines.extend(
        [
            "",
            "## Dependency Rule",
            "",
            "Start work only from the generated ready frontier. Implementation completion remains unverified until its audit passes.",
            "",
            "## Definition of Done",
            "",
            "The final intent is done only when its success evidence exists, required children are verified, and its final audit passes.",
            "",
        ]
    )
    (paths["docs"] / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")
    return {
        "graph": str(paths["graph"]),
        "ready": str(paths["ready"]),
        "docs": str(paths["docs"]),
        "graph_version": state["graph_version"],
        "ready_count": len(ready_packets),
    }


def _event_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"EVENT-{stamp}-{uuid.uuid4().hex[:8].upper()}"


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
) -> dict[str, Any]:
    state["graph_version"] += 1
    state["updated_at"] = utc_now()
    event = {
        "schema": "pyramid-event-v1",
        "id": _event_id(),
        "at": state["updated_at"],
        "graph_version": state["graph_version"],
        "actor": actor,
        "type": event_type,
        "node": node,
        "before": before,
        "after": after,
        "payload": payload or {},
    }
    paths["events"].mkdir(parents=True, exist_ok=True)
    write_json(paths["events"] / f"{event['id']}.json", event)
    write_json(paths["state"], state)
    return event


def create_project(project: str | Path, plan_path: str | Path, actor: str, force: bool = False) -> dict[str, Any]:
    paths = project_paths(project)
    plan = load_json(Path(plan_path).expanduser().resolve())
    errors = validate_plan(plan)
    if errors:
        raise PyramidError("Candidate plan is invalid:\n- " + "\n- ".join(errors))
    with project_lock(paths):
        if paths["plan"].exists():
            if force:
                raise PyramidError("Unsafe replacement is disabled; use reset so the current plan is archived first")
            raise PyramidError(f"A Pyramid Task project already exists at {paths['meta']}; use replan or reset instead")
        timestamp = utc_now()
        state = {
            "schema_version": SCHEMA_VERSION,
            "graph_version": 1,
            "created_at": timestamp,
            "updated_at": timestamp,
            "lifecycle": default_lifecycle(),
            "nodes": {node["id"]: initial_node_state(node, timestamp) for node in plan["nodes"]},
        }
        paths["events"].mkdir(parents=True, exist_ok=True)
        write_json(paths["plan"], plan)
        write_json(paths["state"], state)
        event = {
            "schema": "pyramid-event-v1",
            "id": _event_id(),
            "at": timestamp,
            "graph_version": 1,
            "actor": actor,
            "type": "plan.created",
            "node": plan["intent"]["id"],
            "before": None,
            "after": {"plan_id": plan["plan_id"], "revision": plan["revision"]},
            "payload": {},
        }
        write_json(paths["events"] / f"{event['id']}.json", event)
    compiled = compile_project(project)
    return {"status": "created", "project": str(paths["root"]), "event": event, **compiled}


def check_expected_version(state: dict[str, Any], expected: int | None) -> None:
    if expected is not None and state["graph_version"] != expected:
        raise PyramidError(f"Stale graph version: expected {expected}, current {state['graph_version']}")


def take_task(
    project: str | Path,
    actor: str,
    nid: str | None = None,
    take_next: bool = False,
    lease_minutes: int = 120,
    expected_version: int | None = None,
) -> dict[str, Any]:
    paths = project_paths(project)
    with project_lock(paths):
        paths, plan, state = load_project(project)
        check_expected_version(state, expected_version)
        require_active(state, "update work")
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
        node = nodes[nid]
        item = state["nodes"][nid]
        expired = item["execution"] == "working" and parse_time(item.get("lease_expires_at")) and parse_time(item.get("lease_expires_at")) <= datetime.now(timezone.utc)
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
        item["lease_expires_at"] = (datetime.now(timezone.utc) + timedelta(minutes=lease_minutes)).isoformat().replace("+00:00", "Z")
        item["health"] = "clear"
        item["blocker"] = None
        item["updated_at"] = utc_now()
        event = commit_event(
            paths,
            state,
            actor=actor,
            event_type="task.taken" if not expired else "task.reclaimed-expired",
            node=nid,
            before=before,
            after=copy.deepcopy(item),
            payload={"lease_minutes": lease_minutes},
        )
    compile_project(project)
    _, plan, state = load_project(project)
    return {"status": "taken", "event": event, "packet": task_packet(plan, state, nid)}


def _validate_agent_result(result: dict[str, Any], node: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("schema") != "agent-result-v1":
        errors.append("result.schema must be agent-result-v1")
    if result.get("task") != node["id"]:
        errors.append(f"result.task must be {node['id']}")
    if result.get("outcome") != "implemented":
        errors.append("result.outcome must be implemented")
    for field in ("changed_files", "checks", "acceptance_evidence", "discovered_risks", "suggested_graph_changes"):
        if not isinstance(result.get(field), list):
            errors.append(f"result.{field} must be an array")
    evidence_by_id = {
        item.get("criterion"): item
        for item in result.get("acceptance_evidence", [])
        if isinstance(item, dict)
    }
    for criterion in node["acceptance_criteria"]:
        evidence = evidence_by_id.get(criterion["id"])
        if not evidence or evidence.get("result") != "passed" or not evidence.get("reference"):
            errors.append(f"Missing passing acceptance evidence for {criterion['id']}")
    return errors


def update_task(
    project: str | Path,
    nid: str,
    actor: str,
    status: str,
    reason: str | None = None,
    result_path: str | Path | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if status not in {"implemented", "blocked", "at-risk", "clear", "release"}:
        raise PyramidError(f"Unsupported update status: {status}")
    paths = project_paths(project)
    result = load_json(Path(result_path).expanduser().resolve()) if result_path else None
    with project_lock(paths):
        paths, plan, state = load_project(project)
        check_expected_version(state, expected_version)
        nodes = node_map(plan)
        if nid not in nodes:
            raise PyramidError(f"Unknown node: {nid}")
        item = state["nodes"][nid]
        if item.get("owner") != actor:
            raise PyramidError(f"{actor} does not own {nid}")
        before = copy.deepcopy(item)
        if status == "implemented":
            if item["execution"] != "working":
                raise PyramidError(f"{nid} must be working before it can be implemented")
            if result is None:
                raise PyramidError("implemented requires --result agent-result-v1 JSON")
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
        item["updated_at"] = utc_now()
        event = commit_event(
            paths,
            state,
            actor=actor,
            event_type=f"task.{status}",
            node=nid,
            before=before,
            after=copy.deepcopy(item),
            payload={"reason": reason, "result": result},
        )
    compile_project(project)
    _, plan, state = load_project(project)
    return {"status": status, "event": event, "packet": task_packet(plan, state, nid)}


def _audit_prerequisite_errors(plan: dict[str, Any], state: dict[str, Any], node: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    item = state["nodes"][node["id"]]
    if node["kind"] in EXECUTABLE_KINDS and item["execution"] != "implemented":
        errors.append(f"{node['id']} must be implemented before audit pass")
    for edge in edges_from(plan, node["id"], AUDIT_BLOCKING | {"validated-by"}):
        if state["nodes"][edge["to"]]["verification"] != "passed":
            errors.append(f"{edge['type']} target {edge['to']} is not verified")
    if node["kind"] in {"intent", "outcome", "capability"}:
        nodes = node_map(plan)
        for edge in edges_to(plan, node["id"], {"contributes-to"}):
            child = nodes[edge["from"]]
            if child["selection"] == "primary" and state["nodes"][child["id"]]["verification"] != "passed":
                errors.append(f"Contributing child {child['id']} is not verified")
    return errors


def _validate_audit_result(result: dict[str, Any], nid: str, expected_result: str) -> list[str]:
    errors: list[str] = []
    if result.get("schema") != "audit-result-v1":
        errors.append("audit schema must be audit-result-v1")
    if result.get("target") != nid:
        errors.append(f"audit target must be {nid}")
    if result.get("result") != expected_result:
        errors.append(f"audit result must be {expected_result}")
    checks = result.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("audit checks must be a non-empty array")
    else:
        statuses = [check.get("result") for check in checks if isinstance(check, dict)]
        if expected_result == "pass" and any(status != "passed" for status in statuses):
            errors.append("all checks must be passed for a passing audit")
        if expected_result == "fail" and "failed" not in statuses:
            errors.append("a failing audit must include a failed check")
    return errors


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
) -> list[str]:
    invalidated: list[str] = []
    timestamp = utc_now()
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


def audit_node(
    project: str | Path,
    nid: str,
    actor: str,
    result_value: str,
    evidence_path: str | Path,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if result_value not in {"pass", "fail"}:
        raise PyramidError("audit result must be pass or fail")
    evidence = load_json(Path(evidence_path).expanduser().resolve())
    evidence_errors = _validate_audit_result(evidence, nid, result_value)
    if evidence_errors:
        raise PyramidError("Invalid audit result:\n- " + "\n- ".join(evidence_errors))
    paths = project_paths(project)
    with project_lock(paths):
        paths, plan, state = load_project(project)
        check_expected_version(state, expected_version)
        require_active(state, "record an audit")
        nodes = node_map(plan)
        if nid not in nodes:
            raise PyramidError(f"Unknown node: {nid}")
        if result_value == "pass":
            prerequisite_errors = _audit_prerequisite_errors(plan, state, nodes[nid])
            if prerequisite_errors:
                raise PyramidError("Audit prerequisites are not satisfied:\n- " + "\n- ".join(prerequisite_errors))
        item = state["nodes"][nid]
        before = copy.deepcopy(item)
        invalidated: list[str] = []
        item["verification"] = "passed" if result_value == "pass" else "failed"
        item["health"] = "clear" if result_value == "pass" else "at-risk"
        item["blocker"] = None if result_value == "pass" else "Audit failed; repair or replan is required."
        if result_value == "fail":
            if nodes[nid]["kind"] in EXECUTABLE_KINDS:
                item["execution"] = "needs-rework"
                item["owner"] = None
                item["lease_expires_at"] = None
                item["work_origin"] = None
            invalidated = invalidate_dependent_claims(
                plan,
                state,
                nid,
                f"Evidence for {nid} failed; dependent verification is stale.",
            )
        item["last_audit"] = evidence
        item["updated_at"] = utc_now()
        event = commit_event(
            paths,
            state,
            actor=actor,
            event_type=f"audit.{result_value}",
            node=nid,
            before=before,
            after=copy.deepcopy(item),
            payload={"audit": evidence, "invalidated": invalidated},
        )
    compile_project(project)
    _, plan, state = load_project(project)
    response = {"status": result_value, "event": event, "packet": task_packet(plan, state, nid), "invalidated": invalidated}
    if result_value == "pass" and nid == plan["intent"]["id"]:
        response["next_action"] = "close"
    return response


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return edge["from"], edge["to"], edge["type"]


def prepare_replan(old: dict[str, Any], candidate: dict[str, Any], allow_intent_change: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    if candidate.get("plan_id") != old.get("plan_id"):
        raise PyramidError("A replan must preserve plan_id")
    if candidate.get("intent", {}).get("id") != old.get("intent", {}).get("id") and not allow_intent_change:
        raise PyramidError("Intent ID changed; use --allow-intent-change only after explicit approval")
    merged = copy.deepcopy(candidate)
    old_nodes = node_map(old)
    new_nodes = node_map(merged) if isinstance(merged.get("nodes"), list) else {}
    superseded: list[str] = []
    for nid, node in old_nodes.items():
        if nid not in new_nodes:
            preserved = copy.deepcopy(node)
            preserved["selection"] = "superseded"
            merged.setdefault("nodes", []).append(preserved)
            superseded.append(nid)
    merged_node_ids = {node["id"] for node in merged.get("nodes", []) if isinstance(node, dict) and "id" in node}
    existing_edges = {_edge_key(edge) for edge in merged.get("edges", []) if isinstance(edge, dict) and all(key in edge for key in ("from", "to", "type"))}
    for edge in old.get("edges", []):
        if edge["from"] in merged_node_ids and edge["to"] in merged_node_ids and (edge["from"] in superseded or edge["to"] in superseded):
            if _edge_key(edge) not in existing_edges:
                merged.setdefault("edges", []).append(copy.deepcopy(edge))
                existing_edges.add(_edge_key(edge))
    merged["revision"] = old["revision"] + 1
    errors = validate_plan(merged)
    if errors:
        raise PyramidError("Candidate replan is invalid:\n- " + "\n- ".join(errors))
    new_nodes = node_map(merged)
    added = sorted(set(new_nodes) - set(old_nodes))
    changed = sorted(nid for nid in set(new_nodes) & set(old_nodes) if new_nodes[nid] != old_nodes[nid])
    old_edges = {_edge_key(edge) for edge in old["edges"]}
    new_edges = {_edge_key(edge) for edge in merged["edges"]}
    diff = {
        "from_revision": old["revision"],
        "to_revision": merged["revision"],
        "added_nodes": added,
        "changed_nodes": changed,
        "superseded_nodes": sorted(superseded),
        "added_edges": [list(edge) for edge in sorted(new_edges - old_edges)],
        "removed_edges": [list(edge) for edge in sorted(old_edges - new_edges)],
    }
    return merged, diff


def _semantic_node(node: dict[str, Any]) -> dict[str, Any]:
    keys = {"kind", "selection", "source_requirements", "acceptance_criteria", "required_evidence", "agent"}
    return {key: copy.deepcopy(node.get(key)) for key in keys}


def replan_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    reason: str,
    apply: bool,
    allow_intent_change: bool = False,
    expected_version: int | None = None,
) -> dict[str, Any]:
    candidate = load_json(Path(plan_path).expanduser().resolve())
    paths, old, state = load_project(project)
    check_expected_version(state, expected_version)
    require_active(state, "replan")
    merged, diff = prepare_replan(old, candidate, allow_intent_change)
    if not apply:
        return {"status": "preview", "graph_version": state["graph_version"], "diff": diff}
    with project_lock(paths):
        paths, current, state = load_project(project)
        check_expected_version(state, expected_version)
        require_active(state, "replan")
        merged, diff = prepare_replan(current, candidate, allow_intent_change)
        before = {"revision": current["revision"], "graph_version": state["graph_version"]}
        current_nodes = node_map(current)
        merged_nodes = node_map(merged)
        current_edges = defaultdict(set)
        merged_edges = defaultdict(set)
        for edge in current["edges"]:
            current_edges[edge["from"]].add(_edge_key(edge))
            current_edges[edge["to"]].add(_edge_key(edge))
        for edge in merged["edges"]:
            merged_edges[edge["from"]].add(_edge_key(edge))
            merged_edges[edge["to"]].add(_edge_key(edge))
        timestamp = utc_now()
        next_states: dict[str, Any] = {}
        for nid, node in merged_nodes.items():
            if nid not in state["nodes"]:
                next_states[nid] = initial_node_state(node, timestamp)
                continue
            item = copy.deepcopy(state["nodes"][nid])
            if node["selection"] == "superseded":
                item["execution"] = "superseded"
                item["owner"] = None
                item["lease_expires_at"] = None
                item["health"] = "clear"
            elif nid in current_nodes and (
                _semantic_node(current_nodes[nid]) != _semantic_node(node)
                or current_edges[nid] != merged_edges[nid]
            ):
                if item["execution"] == "working":
                    item["execution"] = "planned"
                    item["owner"] = None
                    item["lease_expires_at"] = None
                item["verification"] = "pending" if item["execution"] == "implemented" else "unverified"
                item["health"] = "at-risk"
                item["blocker"] = "Replan changed this node's contract or graph relations; re-audit required."
            item["updated_at"] = timestamp
            next_states[nid] = item
        state["nodes"] = next_states
        write_json(paths["plan"], merged)
        event = commit_event(
            paths,
            state,
            actor=actor,
            event_type="plan.replanned",
            node=merged["intent"]["id"],
            before=before,
            after={"revision": merged["revision"]},
            payload={"reason": reason, "diff": diff},
        )
    compiled = compile_project(project)
    return {"status": "applied", "event": event, "diff": diff, **compiled}


def reopen_node(
    project: str | Path,
    nid: str,
    actor: str,
    reason: str,
    evidence_path: str | Path | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
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
        paths, plan, state = load_project(project)
        check_expected_version(state, expected_version)
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
        if item["execution"] == "working":
            raise PyramidError(f"{nid} is actively owned by {item.get('owner')}; release it before reopening")
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
                }
            )
        timestamp = utc_now()
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
        invalidated = invalidate_dependent_claims(
            plan,
            state,
            nid,
            f"{nid} was reopened; dependent verification must be repeated.",
        )
        event = commit_event(
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
                "plan_reactivated": reactivated,
            },
        )
    compiled = compile_project(project)
    _, plan, state = load_project(project)
    return {
        "status": "reopened",
        "event": event,
        "invalidated": invalidated,
        "plan_reactivated": reactivated,
        "packet": task_packet(plan, state, nid),
        **compiled,
    }


def _report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "<!-- Generated by Pyramid Task V2. -->",
        f"# Final Report: {report['title']}",
        "",
        f"- Plan: `{report['plan_id']}`",
        f"- Revision: `{report['revision']}`",
        f"- Graph version: `{report['graph_version']}`",
        f"- Completed at: `{report['completed_at']}`",
        f"- Completed by: `{report['completed_by']}`",
        "",
        "## Intent",
        "",
        report["intent"]["statement"],
        "",
        "## Success Evidence",
        "",
    ]
    for item in report["success_evidence"]:
        lines.append(f"- `{item['id']}` — {item['description']} (covered by: {', '.join(item['covered_by']) or 'none'})")
    lines.extend(["", "## Verified Primary Nodes", ""])
    lines.extend(f"- `{item['id']}` — {item['title']}" for item in report["verified_primary_nodes"])
    lines.extend(["", "## Residual Risks", ""])
    lines.extend(f"- {item}" for item in report["residual_risks"] or ["None recorded"])
    lines.append("")
    return "\n".join(lines)


def _completion_report(plan: dict[str, Any], state: dict[str, Any], actor: str, completed_at: str) -> dict[str, Any]:
    primary = [node for node in plan["nodes"] if node["selection"] == "primary"]
    success = []
    for criterion in plan["intent"]["success_evidence"]:
        success.append(
            {
                **copy.deepcopy(criterion),
                "covered_by": sorted(node["id"] for node in primary if criterion["id"] in node["source_requirements"]),
            }
        )
    risks: list[str] = []
    for node in primary:
        result = state["nodes"][node["id"]].get("last_result")
        if isinstance(result, dict):
            for risk in result.get("discovered_risks", []):
                risks.append(f"{node['id']}: {risk}")
    return {
        "schema": "pyramid-final-report-v1",
        "plan_id": plan["plan_id"],
        "title": plan["title"],
        "revision": plan["revision"],
        "graph_version": state["graph_version"] + 1,
        "completed_at": completed_at,
        "completed_by": actor,
        "intent": copy.deepcopy(plan["intent"]),
        "success_evidence": success,
        "verified_primary_nodes": [
            {"id": node["id"], "title": node["title"], "last_audit": state["nodes"][node["id"]].get("last_audit")}
            for node in primary
        ],
        "decisions": copy.deepcopy(plan["decisions"]),
        "evidence": copy.deepcopy(plan["evidence"]),
        "residual_risks": risks,
    }


def close_project(
    project: str | Path,
    actor: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    paths = project_paths(project)
    with project_lock(paths):
        paths, plan, state = load_project(project)
        check_expected_version(state, expected_version)
        status = lifecycle_status(state)
        if status == "archived":
            raise PyramidError("Cannot close an archived plan; restore it first")
        if status == "completed":
            return {
                "status": "completed",
                "graph_version": state["graph_version"],
                "report": lifecycle_state(state).get("completion_report"),
                "already_completed": True,
            }
        errors = completion_errors(plan, state)
        if errors:
            raise PyramidError("Plan cannot close:\n- " + "\n- ".join(errors))
        completed_at = utc_now()
        report = _completion_report(plan, state, actor, completed_at)
        report_id = f"FINAL-{slugify(plan['plan_id']).upper()}-R{plan['revision']}-G{state['graph_version'] + 1}"
        report_json = paths["reports"] / f"{report_id}.json"
        report_markdown = paths["reports"] / f"{report_id}.md"
        lifecycle = lifecycle_state(state)
        before = copy.deepcopy(lifecycle)
        lifecycle.update(
            {
                "status": "completed",
                "completed_at": completed_at,
                "completed_by": actor,
                "completion_report": str(report_json.relative_to(paths["root"])),
            }
        )
        event = commit_event(
            paths,
            state,
            actor=actor,
            event_type="plan.completed",
            node=plan["intent"]["id"],
            before=before,
            after=copy.deepcopy(lifecycle),
            payload={
                "report_json": str(report_json.relative_to(paths["root"])),
                "report_markdown": str(report_markdown.relative_to(paths["root"])),
            },
        )
        write_json(report_json, report)
        report_markdown.parent.mkdir(parents=True, exist_ok=True)
        report_markdown.write_text(_report_markdown(report), encoding="utf-8")
    compiled = compile_project(project)
    return {
        "status": "completed",
        "event": event,
        "report": str(report_json),
        "report_markdown": str(report_markdown),
        **compiled,
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_identifier(plan: dict[str, Any], state: dict[str, Any]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{slugify(plan['plan_id']).upper()}-R{plan['revision']}-G{state['graph_version'] + 1}-{stamp}"


def _copy_current_snapshot(paths: dict[str, Path], destination: Path, manifest: dict[str, Any]) -> None:
    if destination.exists():
        raise PyramidError(f"Archive already exists: {destination}")
    archive_meta = destination / ".pyramid"
    archive_docs = destination / "docs" / "tasks"
    archive_meta.mkdir(parents=True, exist_ok=False)
    for key in ("plan", "state", "graph", "ready"):
        source = paths[key]
        if source.exists():
            shutil.copy2(source, archive_meta / source.name)
    for key in ("events", "reports"):
        source = paths[key]
        if source.exists():
            shutil.copytree(source, archive_meta / source.name)
    if paths["docs"].exists():
        archive_docs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(paths["docs"], archive_docs)
    write_json(destination / "manifest.json", manifest)


def list_archives(project: str | Path) -> list[dict[str, Any]]:
    paths = project_paths(project)
    archives: list[dict[str, Any]] = []
    if not paths["archives"].exists():
        return archives
    for child in sorted(paths["archives"].iterdir(), reverse=True):
        manifest_path = child / "manifest.json"
        if not child.is_dir() or not manifest_path.exists():
            continue
        try:
            manifest = load_json(manifest_path)
        except PyramidError:
            continue
        manifest["path"] = str(child)
        archives.append(manifest)
    return archives


def archive_project(
    project: str | Path,
    actor: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not reason.strip():
        raise PyramidError("archive requires a non-empty reason")
    paths = project_paths(project)
    event: dict[str, Any] | None = None
    with project_lock(paths):
        paths, plan, state = load_project(project)
        check_expected_version(state, expected_version)
        claims = active_claims(state)
        if claims:
            raise PyramidError("Release active claims before archiving: " + ", ".join(claims))
        lifecycle = lifecycle_state(state)
        if lifecycle["status"] == "archived":
            archive_id = lifecycle.get("archive_id")
            previous_status = lifecycle.get("archived_from_status") or "active"
        else:
            previous_status = lifecycle["status"]
            archive_id = _archive_identifier(plan, state)
            destination = paths["archives"] / archive_id
            before = copy.deepcopy(lifecycle)
            lifecycle.update(
                {
                    "status": "archived",
                    "archived_from_status": previous_status,
                    "archived_at": utc_now(),
                    "archived_by": actor,
                    "archive_id": archive_id,
                    "archive_path": str(destination),
                }
            )
            event = commit_event(
                paths,
                state,
                actor=actor,
                event_type="plan.archived",
                node=plan["intent"]["id"],
                before=before,
                after=copy.deepcopy(lifecycle),
                payload={"reason": reason, "archive_id": archive_id},
            )
    if not archive_id:
        raise PyramidError("Archived lifecycle is missing archive_id")
    compile_project(project, allow_archived=True)
    paths, plan, state = load_project(project)
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
        }
        _copy_current_snapshot(paths, destination, manifest)
        validation = validate_project(destination)
        if not validation["valid"]:
            raise PyramidError("Archive validation failed:\n- " + "\n- ".join(validation["errors"]))
    return {
        "status": "archived",
        "archive_id": archive_id,
        "archive": str(destination),
        "event": event,
        "already_archived": event is None,
    }


def _purge_current(paths: dict[str, Path]) -> None:
    for key in ("events", "reports", "docs"):
        target = paths[key]
        if target.exists():
            shutil.rmtree(target)
    for key in ("plan", "state", "graph", "ready", "html"):
        target = paths[key]
        if target.exists():
            target.unlink()


def _initialize_current(
    paths: dict[str, Path],
    plan: dict[str, Any],
    actor: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    timestamp = utc_now()
    state = {
        "schema_version": SCHEMA_VERSION,
        "graph_version": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
        "lifecycle": default_lifecycle(),
        "nodes": {node["id"]: initial_node_state(node, timestamp) for node in plan["nodes"]},
    }
    write_json(paths["plan"], plan)
    write_json(paths["state"], state)
    event = {
        "schema": "pyramid-event-v1",
        "id": _event_id(),
        "at": timestamp,
        "graph_version": 1,
        "actor": actor,
        "type": "plan.created",
        "node": plan["intent"]["id"],
        "before": None,
        "after": {"plan_id": plan["plan_id"], "revision": plan["revision"]},
        "payload": payload,
    }
    write_json(paths["events"] / f"{event['id']}.json", event)
    return state, event


def reset_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not reason.strip():
        raise PyramidError("reset requires a non-empty reason")
    candidate = load_json(Path(plan_path).expanduser().resolve())
    errors = validate_plan(candidate)
    if errors:
        raise PyramidError("Candidate reset plan is invalid:\n- " + "\n- ".join(errors))
    paths, current, state = load_project(project)
    check_expected_version(state, expected_version)
    if candidate["plan_id"] == current["plan_id"]:
        raise PyramidError("A reset must use a new plan_id; use replan to revise the current plan")
    archived = archive_project(project, actor, f"Reset: {reason}", expected_version=expected_version)
    with project_lock(paths):
        paths, _, archived_state = load_project(project)
        if lifecycle_status(archived_state) != "archived":
            raise PyramidError("Reset safety check failed: current plan was not archived")
        if not Path(archived["archive"]).exists():
            raise PyramidError("Reset safety check failed: archive snapshot is missing")
        _purge_current(paths)
        _, event = _initialize_current(
            paths,
            candidate,
            actor,
            {"reset_from_archive": archived["archive_id"], "reason": reason},
        )
    compiled = compile_project(project)
    return {
        "status": "reset",
        "previous_archive": archived["archive_id"],
        "event": event,
        "plan_id": candidate["plan_id"],
        **compiled,
    }


def _resolve_archive(project: str | Path, reference: str) -> tuple[Path, dict[str, Any]]:
    matches = [item for item in list_archives(project) if item.get("archive_id") == reference or item.get("plan_id") == reference]
    if not matches:
        raise PyramidError(f"Unknown archive or archived plan: {reference}")
    matches.sort(key=lambda item: item.get("archived_at") or "", reverse=True)
    selected = matches[0]
    return Path(selected["path"]), selected


def restore_project(
    project: str | Path,
    archive_reference: str,
    actor: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not reason.strip():
        raise PyramidError("restore requires a non-empty reason")
    source, manifest = _resolve_archive(project, archive_reference)
    source_plan = load_json(source / ".pyramid" / "plan.json")
    source_state = load_json(source / ".pyramid" / "state.json")
    validation_errors = validate_plan(source_plan) + validate_state(source_plan, source_state)
    if validation_errors:
        raise PyramidError("Archived plan is invalid:\n- " + "\n- ".join(validation_errors))
    paths = project_paths(project)
    current_archive: dict[str, Any] | None = None
    if paths["plan"].exists():
        _, _, current_state = load_project(project)
        check_expected_version(current_state, expected_version)
        current_archive = archive_project(project, actor, f"Restore {archive_reference}: {reason}", expected_version=expected_version)
    with project_lock(paths):
        _purge_current(paths)
        shutil.copy2(source / ".pyramid" / "plan.json", paths["plan"])
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
            item["work_origin"] = None
            if item["execution"] == "working":
                item["execution"] = "planned"
        write_json(paths["state"], restored_state)
        source_events = source / ".pyramid" / "events"
        if source_events.exists():
            shutil.copytree(source_events, paths["events"])
        source_reports = source / ".pyramid" / "reports"
        if source_reports.exists():
            shutil.copytree(source_reports, paths["reports"])
        event = commit_event(
            paths,
            restored_state,
            actor=actor,
            event_type="plan.restored",
            node=source_plan["intent"]["id"],
            before={"current_archive": current_archive["archive_id"] if current_archive else None},
            after={"restored_from": manifest["archive_id"], "status": lifecycle["status"]},
            payload={"reason": reason, "archive_id": manifest["archive_id"]},
        )
    compiled = compile_project(project)
    return {
        "status": "restored",
        "restored_from": manifest["archive_id"],
        "previous_archive": current_archive["archive_id"] if current_archive else None,
        "event": event,
        **compiled,
    }


def clean_project(project: str | Path) -> dict[str, Any]:
    paths, _, state = load_project(project)
    if lifecycle_status(state) == "archived":
        raise PyramidError("Archived plans are frozen; restore before cleaning projections")
    canonical = {
        "plan": _file_sha256(paths["plan"]),
        "state": _file_sha256(paths["state"]),
        "events": sorted((path.name, _file_sha256(path)) for path in paths["events"].glob("*.json")),
        "reports": sorted((path.name, _file_sha256(path)) for path in paths["reports"].glob("*")) if paths["reports"].exists() else [],
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
    compiled = compile_project(project)
    preserved = (
        canonical["plan"] == _file_sha256(paths["plan"])
        and canonical["state"] == _file_sha256(paths["state"])
        and canonical["events"] == sorted((path.name, _file_sha256(path)) for path in paths["events"].glob("*.json"))
        and canonical["reports"] == (sorted((path.name, _file_sha256(path)) for path in paths["reports"].glob("*")) if paths["reports"].exists() else [])
    )
    if not preserved:
        raise PyramidError("Clean safety check failed: canonical data changed")
    return {"status": "clean", "removed": removed, "canonical_preserved": True, **compiled}


def inspect_lifecycle(project: str | Path) -> dict[str, Any]:
    paths = project_paths(project)
    archives = list_archives(project)
    if not paths["plan"].exists():
        return {"schema": "pyramid-lifecycle-v1", "current": None, "archives": archives}
    _, plan, state = load_project(project)
    errors = completion_errors(plan, state) if lifecycle_status(state) == "active" else []
    return {
        "schema": "pyramid-lifecycle-v1",
        "plan_id": plan["plan_id"],
        "graph_version": state["graph_version"],
        "lifecycle": copy.deepcopy(lifecycle_state(state)),
        "closure_ready": lifecycle_status(state) == "active" and not errors,
        "closure_blockers": errors,
        "active_claims": active_claims(state),
        "archives": archives,
    }


def inspect_project(
    project: str | Path,
    *,
    summary: bool = False,
    ready: bool = False,
    blocked: bool = False,
    pending_audits: bool = False,
    nid: str | None = None,
) -> dict[str, Any]:
    _, plan, state = load_project(project)
    snapshot = graph_snapshot(plan, state)
    if nid:
        return task_packet(plan, state, nid)
    if ready:
        tasks = [
            task_packet(plan, state, node["id"])
            for node in plan["nodes"]
            if availability(plan, state, node) in {"ready", "needs-rework"}
        ]
        tasks.sort(key=lambda item: (item["wave"], item["level"], item["task"]))
        return {"schema": "pyramid-query-v1", "query": "ready", "graph_version": state["graph_version"], "tasks": tasks}
    if blocked:
        nodes = [node for node in snapshot["nodes"] if node["availability"] in {"blocked", "locked"}]
        return {"schema": "pyramid-query-v1", "query": "blocked", "graph_version": state["graph_version"], "nodes": nodes}
    if pending_audits:
        nodes = [node for node in snapshot["nodes"] if node["kind"] == "audit" and node["state"]["verification"] != "passed" and node["selection"] == "primary"]
        return {"schema": "pyramid-query-v1", "query": "pending-audits", "graph_version": state["graph_version"], "nodes": nodes}
    return {
        "schema": "pyramid-summary-v1",
        "plan_id": plan["plan_id"],
        "title": plan["title"],
        "revision": plan["revision"],
        "graph_version": state["graph_version"],
        "lifecycle": copy.deepcopy(lifecycle_state(state)),
        "closure_ready": lifecycle_status(state) == "active" and not completion_errors(plan, state),
        "intent": plan["intent"],
        "summary": snapshot["summary"],
        "ready": [node["id"] for node in snapshot["nodes"] if node["availability"] in {"ready", "needs-rework"}],
        "working": [node["id"] for node in snapshot["nodes"] if node["availability"] == "working"],
        "blocked": [node["id"] for node in snapshot["nodes"] if node["availability"] in {"blocked", "locked"}],
        "pending_audits": [node["id"] for node in snapshot["nodes"] if node["kind"] == "audit" and node["state"]["verification"] != "passed" and node["selection"] == "primary"],
    }


def validate_project(project: str | Path) -> dict[str, Any]:
    paths = project_paths(project)
    plan = load_json(paths["plan"])
    state = load_json(paths["state"])
    errors = validate_plan(plan) + validate_state(plan, state)
    return {
        "valid": not errors,
        "errors": errors,
        "plan_id": plan.get("plan_id"),
        "revision": plan.get("revision"),
        "graph_version": state.get("graph_version"),
    }
