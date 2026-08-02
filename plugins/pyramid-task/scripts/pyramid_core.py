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

from pyramid_assurance import (
    PROJECT_FORMAT_VERSION,
    RUNTIME_VERSION,
    asset_ids_for_file,
    assurance_blockers,
    assurance_for_tasks,
    assurance_summary,
    default_assurance,
    default_baseline,
    default_project_manifest,
    derive_legacy_bundle,
    detect_repository_mode,
    mark_assurance_stale,
    validate_assurance,
    validate_baseline,
    validate_project_manifest,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


SCHEMA_VERSION = 1
NODE_KINDS = {
    "intent",
    "outcome",
    "capability",
    "work-package",
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
        "project": meta / "project.json",
        "baseline": meta / "baseline.json",
        "assurance": meta / "assurance.json",
        "graph": meta / "graph.json",
        "ready": meta / "ready.json",
        "events": meta / "events",
        "reports": meta / "reports",
        "dossiers": meta / "dossiers",
        "archives": meta / "archives",
        "lock": meta / "lock",
        "docs": root / "docs" / "tasks",
        "html": meta / "pyramid.html",
    }


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
        return errors
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


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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

    dependency_targets: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if (
            isinstance(edge, dict)
            and edge.get("from") in node_map
            and edge.get("to") in node_map
            and edge.get("type") in AUDIT_BLOCKING
        ):
            dependency_targets[edge["from"]].add(edge["to"])

    def dependency_closure(start: str) -> set[str]:
        queue = deque([start])
        seen = {start}
        while queue:
            current = queue.popleft()
            for target in dependency_targets.get(current, set()):
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
        return seen - {start}

    for parent, children in contributing_children.items():
        primary_children = [child for child in children if child in primary_ids]
        primary_gates = [
            gate
            for gate in validators.get(parent, [])
            if gate in node_map
            and node_map[gate].get("selection") == "primary"
            and node_map[gate].get("kind") == "audit"
        ]
        branch_children = [child for child in primary_children if child not in primary_gates]
        parent_kind = node_map[parent].get("kind")
        if parent_kind == "work-package" and len(branch_children) < 2:
            errors.append(f"{parent}: work-package needs at least two primary work branches")
        if (
            node_map[parent].get("selection") == "primary"
            and parent_kind in {"intent", "outcome", "capability", "work-package"}
            and len(primary_children) >= 2
        ):
            if not primary_gates:
                errors.append(f"{parent}: multi-branch joint needs a primary validated-by audit gate")
            elif branch_children and not any(
                set(branch_children).issubset(dependency_closure(gate)) for gate in primary_gates
            ):
                errors.append(f"{parent}: no primary audit gate covers every contributing branch")

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
        errors = validate_plan(plan) + validate_state(plan, state) + assurance_validation_errors(paths, plan)
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


def task_packet(
    plan: dict[str, Any],
    state: dict[str, Any],
    nid: str,
    baseline: dict[str, Any] | None = None,
    assurance: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    packet = {
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
        "parents": [edge["to"] for edge in edges_from(plan, nid, {"contributes-to"})],
        "children": [edge["from"] for edge in edges_to(plan, nid, {"contributes-to"})],
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
    if baseline is not None and assurance is not None:
        packet["assurance"] = assurance_for_tasks(
            baseline,
            assurance,
            _covered_assurance_tasks(plan, node),
        )
    return packet


def completion_errors(
    plan: dict[str, Any],
    state: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    assurance: dict[str, Any] | None = None,
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
        errors.extend(assurance_blockers(baseline, assurance, full=True))
    return errors


def graph_snapshot(
    plan: dict[str, Any],
    state: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    assurance: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        if baseline is not None and assurance is not None:
            item["assurance"] = assurance_for_tasks(
                baseline,
                assurance,
                _covered_assurance_tasks(plan, node),
            )
        enriched.append(item)
    primary = [node for node in enriched if node["selection"] == "primary"]
    verified = sum(node["state"]["verification"] == "passed" for node in primary)
    snapshot = {
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
            "closure_ready": not completion_errors(plan, state, baseline, assurance),
            "availability": dict(sorted(counts.items())),
        },
        "nodes": enriched,
        "edges": copy.deepcopy(plan["edges"]),
        "evidence": copy.deepcopy(plan["evidence"]),
        "decisions": copy.deepcopy(plan["decisions"]),
    }
    snapshot["project"] = copy.deepcopy(manifest) if manifest else {
        "format_version": "legacy-v2",
        "mode": "legacy",
    }
    if baseline is not None and assurance is not None:
        snapshot["assurance"] = {
            "summary": assurance_summary(baseline, assurance),
            "baseline": copy.deepcopy(baseline),
            "impacts": copy.deepcopy(assurance.get("impacts", [])),
            "inspections": copy.deepcopy(assurance.get("inspections", [])),
            "findings": copy.deepcopy(assurance.get("findings", [])),
            "scope_drift": copy.deepcopy(assurance.get("scope_drift", [])),
            "controls": copy.deepcopy(assurance.get("controls", {})),
            "legacy_bridge": copy.deepcopy(assurance.get("legacy_bridge", {})),
        }
    else:
        snapshot["assurance"] = None
    return snapshot


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


def render_node_markdown(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
    node: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    assurance: dict[str, Any] | None = None,
) -> str:
    packet = task_packet(plan, state, node["id"], baseline, assurance)
    dependencies = [f"`{item['id']}` ({item['type']}, {item['verification']})" for item in packet["dependencies"]]
    criteria = [f"`{item['id']}` — {item['description']}" for item in node["acceptance_criteria"]]
    evidence = [f"`{item['id']}` ({item['type']}) — {item['description']}" for item in node["required_evidence"]]
    status = state["nodes"][node["id"]]
    assurance_section = ""
    if "assurance" in packet:
        coverage = packet["assurance"]
        assurance_section = f"""
## Brownfield Assurance

- Status: `{coverage['status']}`
- Impact records: {', '.join(f'`{item}`' for item in coverage['impact_ids']) or 'None'}
- Affected assets: {', '.join(f'`{item}`' for item in coverage['asset_ids']) or 'None'}
- Inspections: {', '.join(f'`{item}`' for item in coverage['inspection_ids']) or 'None'}

### Assurance Blockers

{_markdown_list(coverage['blockers'])}
"""
    return f"""<!-- Generated by Pyramid Task V3. Change canonical files through Pyramid Task interfaces, not this file. -->
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
{assurance_section}
"""


def compile_project(project: str | Path, *, allow_archived: bool = False) -> dict[str, Any]:
    paths, plan, state = load_project(project)
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if lifecycle_status(state) == "archived" and not allow_archived:
        raise PyramidError("Archived plans are frozen; use their existing projections or restore the plan")
    snapshot = graph_snapshot(plan, state, baseline, assurance, manifest)
    by_id = node_map(plan)
    for item in snapshot["nodes"]:
        item["source_path"] = str(node_doc_path(paths, by_id[item["id"]]).relative_to(paths["root"]))
    write_json(paths["graph"], snapshot)
    ready_packets = [
        task_packet(plan, state, node["id"], baseline, assurance)
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
        path.write_text(render_node_markdown(paths, plan, state, node, baseline, assurance), encoding="utf-8")

    intent = plan["intent"]
    intent_text = f"""<!-- Generated by Pyramid Task V3. -->
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
        "<!-- Generated by Pyramid Task V3. -->",
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
    if baseline is not None and assurance is not None:
        summary_assurance = assurance_summary(baseline, assurance)
        readme_lines.extend(
            [
                "",
                "## Brownfield Assurance",
                "",
                f"- Status: `{summary_assurance['status']}`",
                f"- Baseline: `{summary_assurance['baseline_status']}` revision `{summary_assurance['baseline_revision']}`",
                f"- Impacted assets inspected sufficiently: `{summary_assurance['sufficiently_inspected_assets']}/{summary_assurance['impacted_assets']}`",
                f"- Open scope drift: `{summary_assurance['open_scope_drift']}`",
                f"- Open material findings: `{summary_assurance['open_material_findings']}`",
            ]
        )
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


def _prepare_new_project_bundle(
    paths: dict[str, Path],
    plan: dict[str, Any],
    actor: str,
    mode: str,
    baseline_path: str | Path | None,
    assurance_path: str | Path | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    selected_mode = detect_repository_mode(paths["root"]) if mode == "auto" else mode
    if selected_mode not in {"greenfield", "brownfield"}:
        raise PyramidError("mode must be auto, greenfield, or brownfield")
    manifest = default_project_manifest(plan_id=plan["plan_id"], mode=selected_mode, actor=actor)
    if selected_mode == "greenfield":
        if baseline_path or assurance_path:
            raise PyramidError("greenfield creation cannot accept baseline or assurance files")
        return manifest, None, None
    baseline = (
        load_json(Path(baseline_path).expanduser().resolve())
        if baseline_path
        else default_baseline(actor=actor)
    )
    baseline_errors = validate_baseline(baseline)
    if baseline_errors:
        raise PyramidError("Candidate baseline is invalid:\n- " + "\n- ".join(baseline_errors))
    assurance = (
        load_json(Path(assurance_path).expanduser().resolve())
        if assurance_path
        else default_assurance(plan_id=plan["plan_id"], baseline=baseline, actor=actor)
    )
    assurance_errors = validate_assurance(assurance, plan=plan, baseline=baseline)
    if assurance_errors:
        raise PyramidError("Candidate assurance is invalid:\n- " + "\n- ".join(assurance_errors))
    return manifest, baseline, assurance


def create_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    force: bool = False,
    *,
    mode: str = "auto",
    baseline_path: str | Path | None = None,
    assurance_path: str | Path | None = None,
) -> dict[str, Any]:
    paths = project_paths(project)
    plan = load_json(Path(plan_path).expanduser().resolve())
    errors = validate_plan(plan)
    if errors:
        raise PyramidError("Candidate plan is invalid:\n- " + "\n- ".join(errors))
    manifest, baseline, assurance = _prepare_new_project_bundle(
        paths, plan, actor, mode, baseline_path, assurance_path
    )
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
        write_json(paths["project"], manifest)
        if baseline is not None and assurance is not None:
            write_json(paths["baseline"], baseline)
            write_json(paths["assurance"], assurance)
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
            "payload": {"mode": manifest["mode"], "project_format_version": PROJECT_FORMAT_VERSION},
        }
        write_json(paths["events"] / f"{event['id']}.json", event)
    compiled = compile_project(project)
    return {
        "status": "created",
        "project": str(paths["root"]),
        "mode": manifest["mode"],
        "project_format_version": PROJECT_FORMAT_VERSION,
        "event": event,
        **compiled,
    }


def check_expected_version(state: dict[str, Any], expected: int | None) -> None:
    if expected is not None and state["graph_version"] != expected:
        raise PyramidError(f"Stale graph version: expected {expected}, current {state['graph_version']}")


def _upgrade_material(
    project: str | Path,
    actor: str,
    source_version: str,
    mode: str,
) -> tuple[dict[str, Path], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    paths, plan, state = load_project(project)
    if lifecycle_status(state) == "archived":
        raise PyramidError("Restore an archived legacy project before upgrading it")
    if paths["project"].exists():
        manifest, baseline, assurance = load_assurance_bundle(paths, plan)
        return paths, plan, state, manifest or {}, baseline, assurance, {
            "status": "up-to-date",
            "project_format_version": manifest.get("format_version") if manifest else None,
        }
    selected_mode = detect_repository_mode(paths["root"]) if mode == "auto" else mode
    if selected_mode not in {"greenfield", "brownfield"}:
        raise PyramidError("upgrade mode must be auto, greenfield, or brownfield")
    migration_time = state.get("updated_at") or state.get("created_at") or utc_now()
    manifest = default_project_manifest(
        plan_id=plan["plan_id"],
        mode=selected_mode,
        actor=actor,
        created_at=state.get("created_at") or migration_time,
    )
    baseline: dict[str, Any] | None = None
    assurance: dict[str, Any] | None = None
    if selected_mode == "brownfield":
        baseline, assurance = derive_legacy_bundle(
            plan=plan,
            state=state,
            actor=actor,
            source_version=source_version,
            at=migration_time,
        )
    material = {
        "plan_sha256": canonical_sha256(plan),
        "state_sha256": canonical_sha256(state),
        "graph_version": state["graph_version"],
        "source_version": source_version,
        "target_format_version": PROJECT_FORMAT_VERSION,
        "mode": selected_mode,
        "manifest": manifest,
        "baseline": baseline,
        "assurance": assurance,
    }
    preview = {
        "schema": "pyramid-upgrade-preview-v1",
        "status": "preview",
        "plan_id": plan["plan_id"],
        "from": source_version,
        "to": PROJECT_FORMAT_VERSION,
        "graph_version": state["graph_version"],
        "preserved": {
            "plan_revision": plan["revision"],
            "nodes": len(plan["nodes"]),
            "node_states": len(state["nodes"]),
            "verified_nodes": sum(item.get("verification") == "passed" for item in state["nodes"].values()),
            "active_claims": active_claims(state),
            "immutable_events": len(list(paths["events"].glob("*.json"))) if paths["events"].exists() else 0,
        },
        "generated": {
            "mode": selected_mode,
            "assets": len(baseline.get("assets", [])) if baseline else 0,
            "impacts": len(assurance.get("impacts", [])) if assurance else 0,
            "legacy_inspections": len(assurance.get("inspections", [])) if assurance else 0,
        },
        "assurance_gaps": (
            copy.deepcopy(assurance.get("legacy_bridge", {}).get("gap_asset_ids", []))
            if assurance
            else []
        ),
        "upgrade_sha256": canonical_sha256(material),
        "approval_required": True,
    }
    return paths, plan, state, manifest, baseline, assurance, preview


def upgrade_project(
    project: str | Path,
    actor: str,
    *,
    source_version: str = "2.x-legacy",
    mode: str = "auto",
    apply: bool = False,
    approved_by: str | None = None,
    approval_reference: str | None = None,
    approved_upgrade_sha256: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    paths, plan, state, manifest, baseline, assurance, preview = _upgrade_material(
        project, actor, source_version, mode
    )
    check_expected_version(state, expected_version)
    if preview.get("status") == "up-to-date":
        return preview
    if not apply:
        return preview
    if not approved_by or not approval_reference or not approved_upgrade_sha256:
        raise PyramidError("upgrade apply requires approved-by, approval-reference, and approved-upgrade-sha256")
    if approved_upgrade_sha256 != preview["upgrade_sha256"]:
        raise PyramidError("Approved upgrade hash does not match the current preview")
    with project_lock(paths):
        current = _upgrade_material(project, actor, source_version, mode)
        paths, plan, state, manifest, baseline, assurance, current_preview = current
        check_expected_version(state, expected_version)
        if current_preview.get("status") == "up-to-date":
            return current_preview
        if current_preview["upgrade_sha256"] != approved_upgrade_sha256:
            raise PyramidError("Upgrade inputs changed after preview; preview and approve again")
        archive_id, archive_path = _create_upgrade_snapshot(
            paths,
            plan,
            state,
            actor=actor,
            reason=f"Pre-v3 upgrade snapshot from {source_version}",
            token=approved_upgrade_sha256[:12],
        )
        timestamp = utc_now()
        migration = {
            "id": f"MIGRATION-V3-{approved_upgrade_sha256[:12].upper()}",
            "from": source_version,
            "to": PROJECT_FORMAT_VERSION,
            "at": timestamp,
            "actor": actor,
            "preview_sha256": approved_upgrade_sha256,
            "archive_id": archive_id,
        }
        manifest.update(
            {
                "runtime_version": RUNTIME_VERSION,
                "last_upgraded_at": timestamp,
                "last_upgraded_by": actor,
                "upgraded_from": source_version,
                "migrations": [migration],
            }
        )
        write_json(paths["project"], manifest)
        if baseline is not None and assurance is not None:
            write_json(paths["baseline"], baseline)
            write_json(paths["assurance"], assurance)
        event = commit_event(
            paths,
            state,
            actor=actor,
            event_type="project.upgraded",
            node=plan["intent"]["id"],
            before={"project_format_version": "legacy-v2", "graph_version": preview["graph_version"]},
            after={"project_format_version": PROJECT_FORMAT_VERSION, "mode": manifest["mode"]},
            payload={
                "migration": migration,
                "approval": {
                    "approved_by": approved_by,
                    "reference": approval_reference,
                    "upgrade_sha256": approved_upgrade_sha256,
                },
                "snapshot": str(archive_path),
                "preserved": preview["preserved"],
                "generated": preview["generated"],
                "assurance_gaps": preview["assurance_gaps"],
            },
        )
    compiled = compile_project(project)
    return {
        "status": "upgraded",
        "from": source_version,
        "to": PROJECT_FORMAT_VERSION,
        "mode": manifest["mode"],
        "archive_id": archive_id,
        "archive": str(archive_path),
        "upgrade_sha256": approved_upgrade_sha256,
        "event": event,
        "preserved": preview["preserved"],
        "assurance_gaps": preview["assurance_gaps"],
        **compiled,
    }


def assess_project(
    project: str | Path,
    baseline_path: str | Path,
    actor: str,
    *,
    apply: bool = False,
    expected_version: int | None = None,
) -> dict[str, Any]:
    candidate = load_json(Path(baseline_path).expanduser().resolve())
    errors = validate_baseline(candidate)
    if errors:
        raise PyramidError("Candidate baseline is invalid:\n- " + "\n- ".join(errors))
    paths, plan, state = load_project(project)
    check_expected_version(state, expected_version)
    require_active(state, "assess the baseline")
    manifest, current, assurance = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or current is None or assurance is None:
        raise PyramidError("assess requires a v3 brownfield project; upgrade legacy projects first")
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
        paths, plan, state = load_project(project)
        check_expected_version(state, expected_version)
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
        event = commit_event(
            paths,
            state,
            actor=actor,
            event_type="assurance.baseline-assessed",
            node=plan["intent"]["id"],
            before={"baseline_id": current["baseline_id"], "revision": current["revision"]},
            after={"baseline_id": candidate["baseline_id"], "revision": candidate["revision"]},
            payload={"baseline_sha256": preview["baseline_sha256"]},
        )
    compiled = compile_project(project)
    return {**preview, "status": "applied", "event": event, **compiled}


def impact_project(
    project: str | Path,
    assurance_path: str | Path,
    actor: str,
    *,
    apply: bool = False,
    expected_version: int | None = None,
) -> dict[str, Any]:
    candidate = load_json(Path(assurance_path).expanduser().resolve())
    paths, plan, state = load_project(project)
    check_expected_version(state, expected_version)
    require_active(state, "update change impact")
    manifest, baseline, current = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or baseline is None or current is None:
        raise PyramidError("impact requires a v3 brownfield project; upgrade legacy projects first")
    errors = validate_assurance(candidate, plan=plan, baseline=baseline)
    if errors:
        raise PyramidError("Candidate assurance is invalid:\n- " + "\n- ".join(errors))
    normalized = copy.deepcopy(candidate)
    normalized["updated_at"] = utc_now()
    normalized["updated_by"] = actor
    blockers = assurance_blockers(baseline, normalized, full=True)
    normalized["status"] = "ready" if not blockers else "incomplete"
    if normalized["status"] == "ready":
        normalized["stale_reasons"] = []
    preview = {
        "status": "preview",
        "schema": "pyramid-impact-preview-v1",
        "graph_version": state["graph_version"],
        "impacts": len(normalized["impacts"]),
        "inspections": len(normalized["inspections"]),
        "findings": len(normalized["findings"]),
        "open_scope_drift": sum(item.get("status") == "open" for item in normalized["scope_drift"]),
        "assurance_status": normalized["status"],
        "blockers": blockers,
        "assurance_sha256": canonical_sha256(normalized),
    }
    if not apply:
        return preview
    with project_lock(paths):
        paths, plan, state = load_project(project)
        check_expected_version(state, expected_version)
        require_active(state, "update change impact")
        _, baseline, current_assurance = load_assurance_bundle(paths, plan)
        if baseline is None or current_assurance is None:
            raise PyramidError("Baseline disappeared before impact apply")
        errors = validate_assurance(normalized, plan=plan, baseline=baseline)
        if errors:
            raise PyramidError("Candidate assurance became invalid:\n- " + "\n- ".join(errors))
        write_json(paths["assurance"], normalized)
        event = commit_event(
            paths,
            state,
            actor=actor,
            event_type="assurance.impact-updated",
            node=plan["intent"]["id"],
            before={"assurance_sha256": canonical_sha256(current_assurance)},
            after={"assurance_sha256": canonical_sha256(normalized), "status": normalized["status"]},
            payload={"blockers": blockers},
        )
    compiled = compile_project(project)
    return {**preview, "status": "applied", "event": event, **compiled}


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
    paths, plan, state = load_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    return {
        "status": "taken",
        "event": event,
        "packet": task_packet(plan, state, nid, baseline, assurance),
    }


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
    if "changed_assets" in result and not _is_string_list(result.get("changed_assets")):
        errors.append("result.changed_assets must be a string array when provided")
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


def _record_scope_drift(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
    nid: str,
    result: dict[str, Any],
    actor: str,
) -> tuple[list[str], list[str]]:
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or baseline is None or assurance is None:
        return [], []
    expected_assets = {
        impact["asset_id"]
        for impact in assurance.get("impacts", [])
        if nid in impact.get("task_ids", []) and impact.get("status") != "dismissed"
    }
    candidates: list[tuple[str, set[str]]] = []
    for changed_file in result.get("changed_files", []):
        if isinstance(changed_file, str) and changed_file.strip():
            candidates.append((changed_file, asset_ids_for_file(baseline, changed_file)))
    known_assets = {item["id"] for item in baseline.get("assets", [])}
    for changed_asset in result.get("changed_assets", []):
        matched = {changed_asset} if changed_asset in known_assets else set()
        candidates.append((f"asset:{changed_asset}", matched))
    drift_ids: list[str] = []
    affected_assets: set[str] = set()
    for changed_file, matched_assets in candidates:
        if matched_assets and matched_assets.issubset(expected_assets):
            continue
        token = hashlib.sha256(
            f"{nid}\0{changed_file}\0{state['graph_version']}".encode("utf-8")
        ).hexdigest()[:12].upper()
        drift_id = f"DRIFT-{token}"
        if any(item.get("id") == drift_id for item in assurance.get("scope_drift", [])):
            continue
        assurance.setdefault("scope_drift", []).append(
            {
                "id": drift_id,
                "task": nid,
                "changed_file": changed_file,
                "matched_asset_ids": sorted(matched_assets),
                "status": "open",
                "detected_at": utc_now(),
                "resolved_impact_id": None,
            }
        )
        drift_ids.append(drift_id)
        affected_assets.update(matched_assets or expected_assets)
    if not drift_ids:
        return [], []
    for inspection in assurance.get("inspections", []):
        if affected_assets.intersection(inspection.get("asset_ids", [])):
            inspection["status"] = "stale"
            limitations = inspection.setdefault("limitations", [])
            message = f"Scope drift from {nid} invalidated this inspection."
            if message not in limitations:
                limitations.append(message)
    mark_assurance_stale(
        assurance,
        f"Unexpected implementation scope was recorded for {nid}: {', '.join(drift_ids)}",
        actor,
    )
    assurance["updated_at"] = utc_now()
    assurance["updated_by"] = actor
    write_json(paths["assurance"], assurance)
    invalidated = invalidate_dependent_claims(
        plan,
        state,
        nid,
        f"Scope drift for {nid} made dependent assurance stale.",
    )
    return drift_ids, invalidated


def _invalidate_inspections_for_actual_change(
    paths: dict[str, Path],
    plan: dict[str, Any],
    nid: str,
    result: dict[str, Any],
    actor: str,
) -> list[str]:
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or baseline is None or assurance is None:
        return []
    known_assets = {item["id"] for item in baseline.get("assets", [])}
    changed_assets = {
        asset_id
        for asset_id in result.get("changed_assets", [])
        if asset_id in known_assets
    }
    for changed_file in result.get("changed_files", []):
        if isinstance(changed_file, str):
            changed_assets.update(asset_ids_for_file(baseline, changed_file))
    if not changed_assets:
        return []
    stale: list[str] = []
    for inspection in assurance.get("inspections", []):
        if not changed_assets.intersection(inspection.get("asset_ids", [])):
            continue
        if inspection.get("status") == "performed":
            inspection["status"] = "stale"
            stale.append(inspection["id"])
        limitations = inspection.setdefault("limitations", [])
        message = f"Implementation result for {nid} changed covered assets after this inspection."
        if message not in limitations:
            limitations.append(message)
    mark_assurance_stale(
        assurance,
        f"Implementation for {nid} changed assets {', '.join(sorted(changed_assets))}; post-change inspection is required.",
        actor,
    )
    write_json(paths["assurance"], assurance)
    return sorted(stale)


def _invalidate_assurance_for_change(
    paths: dict[str, Path],
    plan: dict[str, Any],
    task_ids: set[str],
    actor: str,
    reason: str,
) -> list[str]:
    manifest, _, assurance = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or assurance is None:
        return []
    impacted_assets = {
        impact["asset_id"]
        for impact in assurance.get("impacts", [])
        if task_ids.intersection(impact.get("task_ids", []))
        and impact.get("status") != "dismissed"
    }
    invalidated: list[str] = []
    for inspection in assurance.get("inspections", []):
        if not (
            task_ids.intersection(inspection.get("task_ids", []))
            or impacted_assets.intersection(inspection.get("asset_ids", []))
        ):
            continue
        if inspection.get("status") == "performed":
            inspection["status"] = "stale"
            invalidated.append(inspection["id"])
        limitations = inspection.setdefault("limitations", [])
        if reason not in limitations:
            limitations.append(reason)
    mark_assurance_stale(assurance, reason, actor)
    write_json(paths["assurance"], assurance)
    return sorted(invalidated)


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
        require_active(state, "update work")
        nodes = node_map(plan)
        if nid not in nodes:
            raise PyramidError(f"Unknown node: {nid}")
        item = state["nodes"][nid]
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
            scope_drift, assurance_invalidated = _record_scope_drift(
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
        item["updated_at"] = utc_now()
        event = commit_event(
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
    compile_project(project)
    paths, plan, state = load_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    return {
        "status": status,
        "event": event,
        "packet": task_packet(plan, state, nid, baseline, assurance),
        "scope_drift": scope_drift,
        "assurance_invalidated": assurance_invalidated,
        "stale_inspections": stale_inspections,
    }


def _audit_prerequisite_errors(plan: dict[str, Any], state: dict[str, Any], node: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    item = state["nodes"][node["id"]]
    if node["kind"] in EXECUTABLE_KINDS and item["execution"] != "implemented":
        errors.append(f"{node['id']} must be implemented before audit pass")
    for edge in edges_from(plan, node["id"], AUDIT_BLOCKING | {"validated-by"}):
        if state["nodes"][edge["to"]]["verification"] != "passed":
            errors.append(f"{edge['type']} target {edge['to']} is not verified")
    if node["kind"] in {"intent", "outcome", "capability", "work-package"}:
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
    assertion = result.get("assurance")
    if assertion is not None:
        if not isinstance(assertion, dict):
            errors.append("audit assurance must be an object")
        else:
            for field in ("impact_ids", "inspection_ids", "finding_ids", "limitations"):
                if not _is_string_list(assertion.get(field)):
                    errors.append(f"audit assurance.{field} must be a string array")
            if assertion.get("scope_review") not in {"complete", "incomplete"}:
                errors.append("audit assurance.scope_review must be complete or incomplete")
    return errors


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


def _assurance_audit_errors(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
    node: dict[str, Any],
    evidence: dict[str, Any],
) -> list[str]:
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or baseline is None or assurance is None:
        return []
    if state["graph_version"] < assurance.get("enforce_from_graph_version", 1):
        return []
    assertion = evidence.get("assurance")
    if not isinstance(assertion, dict):
        return ["Brownfield audit pass requires an assurance coverage assertion"]
    errors: list[str] = []
    covered_tasks = _covered_assurance_tasks(plan, node)
    full = node["id"] == plan["intent"]["id"]
    errors.extend(
        assurance_blockers(
            baseline,
            assurance,
            task_ids=None if full else covered_tasks,
            full=full,
        )
    )
    relevant_impacts = [
        item
        for item in assurance.get("impacts", [])
        if item.get("status") != "dismissed"
        and (full or covered_tasks.intersection(item.get("task_ids", [])))
    ]
    relevant_assets = {item["asset_id"] for item in relevant_impacts}
    relevant_inspections = [
        item
        for item in assurance.get("inspections", [])
        if relevant_assets.intersection(item.get("asset_ids", []))
        and (
            full
            or not item.get("task_ids")
            or covered_tasks.intersection(item.get("task_ids", []))
        )
    ]
    expected_impacts = {item["id"] for item in relevant_impacts}
    expected_inspections = {
        item["id"]
        for item in relevant_inspections
        if item.get("required")
        or (
            item.get("status") == "performed"
            and item.get("result") == "pass"
            and item.get("sufficiency") == "sufficient"
        )
    }
    latest_implementation: dict[str, datetime] = {}
    if paths["events"].exists():
        for event_path in paths["events"].glob("*.json"):
            event = load_json(event_path)
            if event.get("type") != "task.implemented" or event.get("node") not in covered_tasks:
                continue
            timestamp = parse_time(event.get("at"))
            if timestamp is not None and (
                event["node"] not in latest_implementation
                or timestamp > latest_implementation[event["node"]]
            ):
                latest_implementation[event["node"]] = timestamp
    for inspection in relevant_inspections:
        performed_at = parse_time(inspection.get("performed_at"))
        inspected_tasks = covered_tasks.intersection(inspection.get("task_ids", []))
        stale_for = sorted(
            task_id
            for task_id in inspected_tasks
            if task_id in latest_implementation
            and (
                performed_at is None
                or performed_at < latest_implementation[task_id]
            )
        )
        if stale_for:
            errors.append(
                f"Inspection {inspection.get('id')} predates implementation for: "
                + ", ".join(stale_for)
            )
    expected_findings = {
        item["id"]
        for item in assurance.get("findings", [])
        if relevant_assets.intersection(item.get("asset_ids", []))
    }
    asserted_impacts = set(assertion.get("impact_ids", []))
    asserted_inspections = set(assertion.get("inspection_ids", []))
    asserted_findings = set(assertion.get("finding_ids", []))
    known_impacts = {item["id"] for item in assurance.get("impacts", [])}
    known_inspections = {item["id"] for item in assurance.get("inspections", [])}
    known_findings = {item["id"] for item in assurance.get("findings", [])}
    if not expected_impacts.issubset(asserted_impacts):
        errors.append(
            "Audit assurance omits impact records: "
            + ", ".join(sorted(expected_impacts - asserted_impacts))
        )
    if not expected_inspections.issubset(asserted_inspections):
        errors.append(
            "Audit assurance omits inspection records: "
            + ", ".join(sorted(expected_inspections - asserted_inspections))
        )
    if not expected_findings.issubset(asserted_findings):
        errors.append(
            "Audit assurance omits findings: "
            + ", ".join(sorted(expected_findings - asserted_findings))
        )
    for label, asserted, known in (
        ("impact", asserted_impacts, known_impacts),
        ("inspection", asserted_inspections, known_inspections),
        ("finding", asserted_findings, known_findings),
    ):
        unknown = asserted - known
        if unknown:
            errors.append(
                f"Audit assurance references unknown {label} records: "
                + ", ".join(sorted(unknown))
            )
    if assertion.get("scope_review") != "complete":
        errors.append("Audit assurance scope review is incomplete")
    return sorted(set(errors))


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
            prerequisite_errors.extend(
                _assurance_audit_errors(paths, plan, state, nodes[nid], evidence)
            )
            if prerequisite_errors:
                raise PyramidError("Audit prerequisites are not satisfied:\n- " + "\n- ".join(prerequisite_errors))
        item = state["nodes"][nid]
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
            invalidated = invalidate_dependent_claims(
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
        item["updated_at"] = utc_now()
        event = commit_event(
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
    compile_project(project)
    paths, plan, state = load_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    response = {
        "status": result_value,
        "event": event,
        "packet": task_packet(plan, state, nid, baseline, assurance),
        "invalidated": invalidated,
        "stale_inspections": stale_inspections,
    }
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


EXPANSION_PARENT_FIELDS = (
    "id",
    "title",
    "summary",
    "level",
    "wave",
    "workstream",
    "selection",
    "source_requirements",
    "acceptance_criteria",
    "required_evidence",
    "agent",
)


def expansion_parent_snapshot(node: dict[str, Any]) -> dict[str, Any]:
    return {field: copy.deepcopy(node.get(field)) for field in EXPANSION_PARENT_FIELDS}


def _expansion_errors(
    plan: dict[str, Any],
    state: dict[str, Any],
    proposal: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if proposal.get("schema") != "expansion-proposal-v1":
        errors.append("proposal.schema must be expansion-proposal-v1")
    target = proposal.get("target")
    nodes = node_map(plan)
    if not isinstance(target, str) or target not in nodes:
        errors.append(f"proposal.target is unknown: {target}")
        return errors
    parent = nodes[target]
    if parent.get("kind") not in EXECUTABLE_KINDS - {"audit"}:
        errors.append(f"{target}: only non-audit executable nodes can be expanded")
    if parent.get("selection") != "primary":
        errors.append(f"{target}: only a primary-path task can be expanded")
    if edges_to(plan, target, {"contributes-to"}):
        errors.append(f"{target}: task already has contributing children; use replan for an existing subtree")
    item = state["nodes"][target]
    if item.get("owner") or item.get("execution") == "working":
        errors.append(f"{target}: release the active claim before expansion")
    if item.get("execution") not in {"planned", "needs-rework"}:
        errors.append(f"{target}: reopen implemented or verified work before expansion")
    if proposal.get("base_graph_version") != state.get("graph_version"):
        errors.append(
            f"proposal.base_graph_version is stale: expected {state.get('graph_version')}, "
            f"got {proposal.get('base_graph_version')}"
        )
    if not isinstance(proposal.get("reason"), str) or not proposal["reason"].strip():
        errors.append("proposal.reason must be non-empty")
    if not _is_string_list(proposal.get("trigger_signals")) or not proposal.get("trigger_signals"):
        errors.append("proposal.trigger_signals must be a non-empty string array")
    evidence = proposal.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("proposal.evidence must be a non-empty array")
    else:
        for index, entry in enumerate(evidence):
            if not isinstance(entry, dict) or not all(
                isinstance(entry.get(field), str) and entry[field].strip()
                for field in ("claim", "reference")
            ):
                errors.append(f"proposal.evidence[{index}] needs non-empty claim and reference")
    if proposal.get("preserved_parent") != expansion_parent_snapshot(parent):
        errors.append(f"{target}: preserved_parent does not exactly match the current task contract")
    if not isinstance(proposal.get("user_decisions"), list):
        errors.append("proposal.user_decisions must be an array")
    else:
        for index, decision in enumerate(proposal["user_decisions"]):
            if not isinstance(decision, dict) or not all(
                isinstance(decision.get(field), str) and decision[field].strip()
                for field in ("question", "answer")
            ):
                errors.append(f"proposal.user_decisions[{index}] needs non-empty question and answer")
    impact = proposal.get("impact")
    if not isinstance(impact, dict) or not all(
        isinstance(impact.get(field), str) and impact[field].strip()
        for field in ("scope", "risk", "execution_order")
    ):
        errors.append("proposal.impact needs non-empty scope, risk, and execution_order")

    proposed_nodes = proposal.get("nodes")
    proposed_by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(proposed_nodes, list):
        errors.append("proposal.nodes must be an array")
        proposed_nodes = []
    for index, node in enumerate(proposed_nodes):
        if not isinstance(node, dict):
            errors.append(f"proposal.nodes[{index}] must be an object")
            continue
        nid = node.get("id")
        if not isinstance(nid, str) or not ID_PATTERN.match(nid):
            errors.append(f"proposal.nodes[{index}].id is invalid")
            continue
        if nid in nodes:
            errors.append(f"proposal node already exists: {nid}")
        if nid in proposed_by_id:
            errors.append(f"duplicate proposal node: {nid}")
        proposed_by_id[nid] = node
        if not isinstance(node.get("kind"), str) or node.get("kind") not in EXECUTABLE_KINDS:
            errors.append(f"{nid}: expansion children must be executable")
        if node.get("selection") != "primary":
            errors.append(f"{nid}: expansion children must be primary")
        if node.get("level") != parent.get("level") + 1:
            errors.append(f"{nid}: level must be exactly one below parent {target}")

    audit_gate = proposal.get("audit_gate")
    if not isinstance(audit_gate, str) or audit_gate not in proposed_by_id:
        errors.append("proposal.audit_gate must identify a proposed node")
    elif proposed_by_id[audit_gate].get("kind") != "audit":
        errors.append("proposal.audit_gate must have kind audit")
    audit_nodes = [nid for nid, node in proposed_by_id.items() if node.get("kind") == "audit"]
    if len(audit_nodes) != 1:
        errors.append("an expansion must add exactly one audit node")
    branch_ids = set(proposed_by_id) - ({audit_gate} if isinstance(audit_gate, str) else set())
    if len(branch_ids) < 2:
        errors.append("an expansion must add at least two executable work branches plus the audit gate")

    coverage = proposal.get("audit_coverage")
    covered: set[str] = set()
    if not isinstance(coverage, list):
        errors.append("proposal.audit_coverage must be an array")
        coverage = []
    for index, entry in enumerate(coverage):
        if not isinstance(entry, dict):
            errors.append(f"proposal.audit_coverage[{index}] must be an object")
            continue
        nid, edge_type = entry.get("node"), entry.get("type")
        if not isinstance(nid, str) or nid not in branch_ids:
            errors.append(f"proposal.audit_coverage[{index}] references a non-branch node {nid}")
        elif nid in covered:
            errors.append(f"proposal.audit_coverage duplicates {nid}")
        else:
            covered.add(nid)
        if not isinstance(edge_type, str) or edge_type not in {"integration-requires", "validation-requires"}:
            errors.append(f"proposal.audit_coverage[{index}] has invalid type {edge_type}")
    if covered != branch_ids:
        errors.append("proposal.audit_coverage must cover every non-gate branch exactly once")

    internal_edges = proposal.get("internal_edges")
    if not isinstance(internal_edges, list):
        errors.append("proposal.internal_edges must be an array")
        internal_edges = []
    internal_keys: set[tuple[str, str, str]] = set()
    for index, edge in enumerate(internal_edges):
        if not isinstance(edge, dict):
            errors.append(f"proposal.internal_edges[{index}] must be an object")
            continue
        source, destination, edge_type = edge.get("from"), edge.get("to"), edge.get("type")
        if not isinstance(source, str) or not isinstance(destination, str):
            errors.append(f"proposal.internal_edges[{index}] needs string node IDs")
        elif source not in proposed_by_id or destination not in proposed_by_id:
            errors.append(f"proposal.internal_edges[{index}] must stay inside the proposed subtree")
        if not isinstance(edge_type, str) or edge_type not in AUDIT_BLOCKING:
            errors.append(f"proposal.internal_edges[{index}] has invalid dependency type {edge_type}")
        if isinstance(source, str) and isinstance(destination, str) and isinstance(edge_type, str):
            key = (source, destination, edge_type)
            if key in internal_keys:
                errors.append(f"duplicate proposal internal edge: {source} --{edge_type}--> {destination}")
            internal_keys.add(key)

    current_dependencies = {
        (edge["to"], edge["type"])
        for edge in edges_from(plan, target, AUDIT_BLOCKING)
    }
    mappings = proposal.get("dependency_mapping")
    if not isinstance(mappings, list):
        errors.append("proposal.dependency_mapping must be an array")
        mappings = []
    mapped: set[tuple[str, str]] = set()
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            errors.append(f"proposal.dependency_mapping[{index}] must be an object")
            continue
        dependency = mapping.get("dependency")
        if not isinstance(dependency, dict):
            errors.append(f"proposal.dependency_mapping[{index}].dependency must be an object")
            continue
        dependency_target, dependency_type = dependency.get("to"), dependency.get("type")
        if not isinstance(dependency_target, str) or not isinstance(dependency_type, str):
            errors.append(f"proposal.dependency_mapping[{index}].dependency needs string to and type")
            continue
        key = (dependency_target, dependency_type)
        if key not in current_dependencies:
            errors.append(f"proposal.dependency_mapping[{index}] references a non-current dependency {key}")
        elif key in mapped:
            errors.append(f"proposal.dependency_mapping duplicates current dependency {key}")
        else:
            mapped.add(key)
        consumers = mapping.get("consumers")
        if not _is_string_list(consumers) or not consumers:
            errors.append(f"proposal.dependency_mapping[{index}].consumers must be non-empty")
        else:
            unknown = sorted(set(consumers) - set(proposed_by_id))
            if unknown:
                errors.append(
                    f"proposal.dependency_mapping[{index}] has unknown consumers: {', '.join(unknown)}"
                )
        if not isinstance(mapping.get("rationale"), str) or not mapping["rationale"].strip():
            errors.append(f"proposal.dependency_mapping[{index}].rationale must be non-empty")
    if mapped != current_dependencies:
        errors.append("proposal.dependency_mapping must account for every current task dependency exactly once")
    return errors


def prepare_expansion(
    plan: dict[str, Any],
    state: dict[str, Any],
    proposal: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    errors = _expansion_errors(plan, state, proposal)
    if errors:
        raise PyramidError("Invalid expansion proposal:\n- " + "\n- ".join(errors))
    candidate = copy.deepcopy(plan)
    target = proposal["target"]
    candidate_nodes = node_map(candidate)
    candidate_nodes[target]["kind"] = "work-package"
    candidate["nodes"].extend(copy.deepcopy(proposal["nodes"]))

    additions: list[dict[str, str]] = []
    for node in proposal["nodes"]:
        additions.append({"from": node["id"], "to": target, "type": "contributes-to"})
    additions.append({"from": target, "to": proposal["audit_gate"], "type": "validated-by"})
    additions.extend(copy.deepcopy(proposal["internal_edges"]))
    additions.extend(
        {
            "from": proposal["audit_gate"],
            "to": entry["node"],
            "type": entry["type"],
        }
        for entry in proposal["audit_coverage"]
    )
    for mapping in proposal["dependency_mapping"]:
        dependency = mapping["dependency"]
        for consumer in mapping["consumers"]:
            additions.append(
                {"from": consumer, "to": dependency["to"], "type": dependency["type"]}
            )
    candidate["edges"].extend(additions)
    candidate["revision"] = plan["revision"] + 1
    errors = validate_plan(candidate)
    if errors:
        raise PyramidError("Expanded plan is invalid:\n- " + "\n- ".join(errors))
    diff = {
        "from_revision": plan["revision"],
        "to_revision": candidate["revision"],
        "target": target,
        "target_kind_before": node_map(plan)[target]["kind"],
        "target_kind_after": "work-package",
        "added_nodes": sorted(node["id"] for node in proposal["nodes"]),
        "audit_gate": proposal["audit_gate"],
        "added_edges": [list(_edge_key(edge)) for edge in additions],
        "preserved_incoming_edges": [
            list(_edge_key(edge)) for edge in edges_to(plan, target)
        ],
        "preserved_outgoing_edges": [
            list(_edge_key(edge)) for edge in edges_from(plan, target)
        ],
    }
    return candidate, diff


def expand_project(
    project: str | Path,
    proposal_path: str | Path,
    actor: str,
    *,
    apply: bool,
    approved_by: str | None = None,
    approval_reference: str | None = None,
    approved_proposal_sha256: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    proposal = load_json(Path(proposal_path).expanduser().resolve())
    proposal_hash = canonical_sha256(proposal)
    paths, plan, state = load_project(project)
    check_expected_version(state, expected_version)
    require_active(state, "expand a task")
    candidate, diff = prepare_expansion(plan, state, proposal)
    if not apply:
        return {
            "status": "preview",
            "graph_version": state["graph_version"],
            "proposal_sha256": proposal_hash,
            "approval_required": True,
            "diff": diff,
        }
    if not approved_by or not approved_by.strip():
        raise PyramidError("Applying expansion requires --approved-by")
    if not approval_reference or not approval_reference.strip():
        raise PyramidError("Applying expansion requires --approval-reference")
    if not approved_proposal_sha256 or not approved_proposal_sha256.strip():
        raise PyramidError("Applying expansion requires --approved-proposal-sha256 from preview")
    if approved_proposal_sha256 != proposal_hash:
        raise PyramidError("Approved proposal hash does not match the current proposal; preview and approve again")
    with project_lock(paths):
        paths, current, state = load_project(project)
        check_expected_version(state, expected_version)
        require_active(state, "expand a task")
        candidate, diff = prepare_expansion(current, state, proposal)
        target = proposal["target"]
        before = {
            "revision": current["revision"],
            "graph_version": state["graph_version"],
            "node": copy.deepcopy(node_map(current)[target]),
            "state": copy.deepcopy(state["nodes"][target]),
        }
        timestamp = utc_now()
        parent_state = state["nodes"][target]
        parent_state.update(
            {
                "execution": "planned",
                "verification": "unverified",
                "health": "clear",
                "owner": None,
                "lease_expires_at": None,
                "work_origin": None,
                "blocker": None,
                "updated_at": timestamp,
            }
        )
        candidate_by_id = node_map(candidate)
        for nid in diff["added_nodes"]:
            state["nodes"][nid] = initial_node_state(candidate_by_id[nid], timestamp)
        invalidated = invalidate_dependent_claims(
            candidate,
            state,
            target,
            f"{target} was expanded; dependent verification must follow the approved subtree.",
        )
        stale_inspections = _invalidate_assurance_for_change(
            paths,
            candidate,
            {target, *diff["added_nodes"]},
            actor,
            f"Approved expansion of {target} changed assurance coverage and requires renewed impact review.",
        )
        write_json(paths["plan"], candidate)
        event = commit_event(
            paths,
            state,
            actor=actor,
            event_type="task.expanded",
            node=target,
            before=before,
            after={
                "revision": candidate["revision"],
                "node": copy.deepcopy(candidate_by_id[target]),
                "state": copy.deepcopy(parent_state),
                "added_nodes": diff["added_nodes"],
            },
            payload={
                "proposal": proposal,
                "proposal_sha256": proposal_hash,
                "approval": {
                    "approved_by": approved_by,
                    "reference": approval_reference,
                    "proposal_sha256": approved_proposal_sha256,
                },
                "diff": diff,
                "invalidated": invalidated,
                "stale_inspections": stale_inspections,
            },
        )
    compiled = compile_project(project)
    paths, applied_plan, applied_state = load_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, applied_plan)
    return {
        "status": "applied",
        "event": event,
        "proposal_sha256": proposal_hash,
        "diff": diff,
        "invalidated": invalidated,
        "stale_inspections": stale_inspections,
        "parent": task_packet(
            applied_plan,
            applied_state,
            proposal["target"],
            baseline,
            assurance,
        ),
        **compiled,
    }


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
        affected_tasks = set(diff["added_nodes"]) | set(diff["changed_nodes"]) | set(diff["superseded_nodes"])
        stale_inspections = _invalidate_assurance_for_change(
            paths,
            merged,
            affected_tasks,
            actor,
            "Replan changed task contracts or graph relations; impact and inspection evidence require review.",
        )
        event = commit_event(
            paths,
            state,
            actor=actor,
            event_type="plan.replanned",
            node=merged["intent"]["id"],
            before=before,
            after={"revision": merged["revision"]},
            payload={
                "reason": reason,
                "diff": diff,
                "stale_inspections": stale_inspections,
            },
        )
    compiled = compile_project(project)
    return {
        "status": "applied",
        "event": event,
        "diff": diff,
        "stale_inspections": stale_inspections,
        **compiled,
    }


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
                    "change_dossier": None,
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
        stale_inspections = _invalidate_assurance_for_change(
            paths,
            plan,
            {nid},
            actor,
            f"{nid} was reopened; prior change-assurance evidence is stale.",
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
                "stale_inspections": stale_inspections,
                "plan_reactivated": reactivated,
            },
        )
    compiled = compile_project(project)
    paths, plan, state = load_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    return {
        "status": "reopened",
        "event": event,
        "invalidated": invalidated,
        "stale_inspections": stale_inspections,
        "plan_reactivated": reactivated,
        "packet": task_packet(plan, state, nid, baseline, assurance),
        **compiled,
    }


def _report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "<!-- Generated by Pyramid Task V3. -->",
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


def _dossier_markdown(dossier: dict[str, Any]) -> str:
    lines = [
        "<!-- Generated by Pyramid Task V3. -->",
        f"# Change Dossier: {dossier['title']}",
        "",
        f"- Dossier: `{dossier['dossier_id']}`",
        f"- Plan: `{dossier['plan_id']}`",
        f"- Completed at: `{dossier['completed_at']}`",
        f"- Completed by: `{dossier['completed_by']}`",
        f"- Baseline: revision `{dossier['baseline_before']['revision']}` → `{dossier['baseline_after']['revision']}`",
        "",
        "## Intent",
        "",
        dossier["intent"]["statement"],
        "",
        "## Predicted Impact",
        "",
    ]
    lines.extend(
        f"- `{item['id']}` → `{item['asset_id']}` ({item['type']}, {item['status']})"
        for item in dossier["predicted_impacts"]
    )
    if not dossier["predicted_impacts"]:
        lines.append("- None recorded")
    lines.extend(["", "## Actual Changes", ""])
    lines.extend(
        f"- `{item['task']}`: `{item['file']}` → "
        + (", ".join(f"`{asset}`" for asset in item["asset_ids"]) or "unmapped")
        for item in dossier["actual_changes"]
    )
    if not dossier["actual_changes"]:
        lines.append("- None recorded")
    lines.extend(["", "## Inspections", ""])
    lines.extend(
        f"- `{item['id']}` — {item['method']} ({item['result']}, {item['sufficiency']})"
        for item in dossier["inspections"]
    )
    if not dossier["inspections"]:
        lines.append("- None recorded")
    lines.extend(["", "## Scope Drift", ""])
    lines.extend(
        f"- `{item['id']}` — `{item['changed_file']}` ({item['status']})"
        for item in dossier["scope_drift"]
    )
    if not dossier["scope_drift"]:
        lines.append("- None recorded")
    lines.extend(["", "## Findings and Residual Risk", ""])
    lines.extend(
        f"- `{item['id']}` — {item['title']} ({item['severity']}, {item['status']})"
        for item in dossier["findings"]
    )
    lines.extend(f"- {item}" for item in dossier["residual_risks"])
    if not dossier["findings"] and not dossier["residual_risks"]:
        lines.append("- None recorded")
    lines.extend(["", "## Recovery and Observation", ""])
    for name in ("rollback", "monitoring"):
        control = dossier["controls"][name]
        lines.append(f"- {name.capitalize()}: `{control['status']}`")
    lines.append("")
    return "\n".join(lines)


def _build_change_dossier(
    plan: dict[str, Any],
    state: dict[str, Any],
    baseline: dict[str, Any],
    assurance: dict[str, Any],
    actor: str,
    completed_at: str,
    dossier_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline_before = copy.deepcopy(baseline)
    baseline_after = copy.deepcopy(baseline)
    baseline_after["revision"] += 1
    baseline_after["status"] = "current"
    baseline_after["captured_at"] = completed_at
    baseline_after["captured_by"] = actor
    baseline_after["capture_method"] = "verified-change-close"
    history_id = f"HISTORY-{slugify(plan['plan_id']).upper()}-R{plan['revision']}"
    existing_history_ids = {item.get("id") for item in baseline_after.get("history", [])}
    if history_id in existing_history_ids:
        history_id = f"{history_id}-G{state['graph_version'] + 1}"
    impacted_assets = sorted(
        {item["asset_id"] for item in assurance.get("impacts", []) if item.get("status") != "dismissed"}
    )
    baseline_after.setdefault("history", []).append(
        {
            "id": history_id,
            "kind": "change",
            "summary": f"Completed {plan['title']} under dossier {dossier_id}.",
            "asset_ids": impacted_assets,
            "evidence": [dossier_id],
            "date": completed_at,
            "controls": [
                name
                for name, control in assurance.get("controls", {}).items()
                if control.get("status") == "ready"
            ],
        }
    )
    actual_changes: list[dict[str, str]] = []
    audits: list[dict[str, Any]] = []
    residual_risks: list[Any] = []
    for node in plan["nodes"]:
        item = state["nodes"][node["id"]]
        result = item.get("last_result")
        if isinstance(result, dict):
            recorded_assets: set[str] = set()
            for changed in result.get("changed_files", []):
                if not isinstance(changed, str):
                    continue
                mapped_assets = sorted(asset_ids_for_file(baseline, changed))
                recorded_assets.update(mapped_assets)
                actual_changes.append(
                    {
                        "task": node["id"],
                        "file": changed,
                        "asset_ids": mapped_assets,
                    }
                )
            for asset_id in result.get("changed_assets", []):
                if isinstance(asset_id, str) and asset_id not in recorded_assets:
                    actual_changes.append(
                        {
                            "task": node["id"],
                            "file": f"asset:{asset_id}",
                            "asset_ids": [asset_id],
                        }
                    )
            residual_risks.extend(result.get("discovered_risks", []))
        if isinstance(item.get("last_audit"), dict):
            audits.append({"node": node["id"], "audit": copy.deepcopy(item["last_audit"])})
    residual_risks.extend(
        {
            "finding": item["id"],
            "severity": item["severity"],
            "status": item["status"],
            "acceptance_reason": item.get("acceptance_reason"),
        }
        for item in assurance.get("findings", [])
        if item.get("status") == "accepted"
    )
    dossier = {
        "schema": "pyramid-change-dossier-v1",
        "dossier_id": dossier_id,
        "plan_id": plan["plan_id"],
        "title": plan["title"],
        "completed_at": completed_at,
        "completed_by": actor,
        "baseline_before": baseline_before,
        "baseline_after": copy.deepcopy(baseline_after),
        "intent": copy.deepcopy(plan["intent"]),
        "predicted_impacts": copy.deepcopy(assurance.get("impacts", [])),
        "actual_changes": actual_changes,
        "inspections": copy.deepcopy(assurance.get("inspections", [])),
        "scope_drift": copy.deepcopy(assurance.get("scope_drift", [])),
        "findings": copy.deepcopy(assurance.get("findings", [])),
        "controls": copy.deepcopy(assurance.get("controls", {})),
        "audits": audits,
        "residual_risks": residual_risks,
        "legacy_bridge": copy.deepcopy(assurance.get("legacy_bridge", {})),
    }
    return dossier, baseline_after


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
        manifest, baseline, assurance = load_assurance_bundle(paths, plan)
        errors = completion_errors(plan, state, baseline, assurance)
        if errors:
            raise PyramidError("Plan cannot close:\n- " + "\n- ".join(errors))
        completed_at = utc_now()
        report = _completion_report(plan, state, actor, completed_at)
        report_id = f"FINAL-{slugify(plan['plan_id']).upper()}-R{plan['revision']}-G{state['graph_version'] + 1}"
        report_json = paths["reports"] / f"{report_id}.json"
        report_markdown = paths["reports"] / f"{report_id}.md"
        dossier: dict[str, Any] | None = None
        baseline_after: dict[str, Any] | None = None
        dossier_json: Path | None = None
        dossier_markdown: Path | None = None
        if manifest and manifest.get("mode") == "brownfield" and baseline is not None and assurance is not None:
            dossier_id = f"DOSSIER-{slugify(plan['plan_id']).upper()}-R{plan['revision']}-G{state['graph_version'] + 1}"
            dossier_json = paths["dossiers"] / f"{dossier_id}.json"
            dossier_markdown = paths["dossiers"] / f"{dossier_id}.md"
            dossier, baseline_after = _build_change_dossier(
                plan, state, baseline, assurance, actor, completed_at, dossier_id
            )
            report["change_dossier"] = str(dossier_json.relative_to(paths["root"]))
        lifecycle = lifecycle_state(state)
        before = copy.deepcopy(lifecycle)
        lifecycle.update(
            {
                "status": "completed",
                "completed_at": completed_at,
                "completed_by": actor,
                "completion_report": str(report_json.relative_to(paths["root"])),
                "change_dossier": str(dossier_json.relative_to(paths["root"])) if dossier_json else None,
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
                "change_dossier_json": str(dossier_json.relative_to(paths["root"])) if dossier_json else None,
                "change_dossier_markdown": str(dossier_markdown.relative_to(paths["root"])) if dossier_markdown else None,
            },
        )
        write_json(report_json, report)
        report_markdown.parent.mkdir(parents=True, exist_ok=True)
        report_markdown.write_text(_report_markdown(report), encoding="utf-8")
        if dossier is not None and dossier_json is not None and dossier_markdown is not None and baseline_after is not None and assurance is not None:
            write_json(dossier_json, dossier)
            dossier_markdown.parent.mkdir(parents=True, exist_ok=True)
            dossier_markdown.write_text(_dossier_markdown(dossier), encoding="utf-8")
            next_assurance = copy.deepcopy(assurance)
            next_assurance["baseline_id"] = baseline_after["baseline_id"]
            next_assurance["baseline_revision"] = baseline_after["revision"]
            next_assurance["status"] = "passed"
            next_assurance["updated_at"] = completed_at
            next_assurance["updated_by"] = actor
            next_assurance["stale_reasons"] = []
            write_json(paths["baseline"], baseline_after)
            write_json(paths["assurance"], next_assurance)
    compiled = compile_project(project)
    return {
        "status": "completed",
        "event": event,
        "report": str(report_json),
        "report_markdown": str(report_markdown),
        "change_dossier": str(dossier_json) if dossier_json else None,
        "change_dossier_markdown": str(dossier_markdown) if dossier_markdown else None,
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
    for key in ("plan", "state", "project", "baseline", "assurance", "graph", "ready"):
        source = paths[key]
        if source.exists():
            shutil.copy2(source, archive_meta / source.name)
    for key in ("events", "reports", "dossiers"):
        source = paths[key]
        if source.exists():
            shutil.copytree(source, archive_meta / source.name)
    if paths["docs"].exists():
        archive_docs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(paths["docs"], archive_docs)
    write_json(destination / "manifest.json", manifest)


def _create_upgrade_snapshot(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
    *,
    actor: str,
    reason: str,
    token: str,
) -> tuple[str, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_id = (
        f"{slugify(plan['plan_id']).upper()}-R{plan['revision']}-"
        f"G{state['graph_version']}-PRE-UPGRADE-{token.upper()}-{stamp}"
    )
    destination = paths["archives"] / archive_id
    manifest = {
        "schema": "pyramid-archive-v1",
        "archive_id": archive_id,
        "plan_id": plan["plan_id"],
        "title": plan["title"],
        "revision": plan["revision"],
        "graph_version": state["graph_version"],
        "archived_at": utc_now(),
        "archived_by": actor,
        "previous_status": lifecycle_status(state),
        "reason": reason,
        "plan_sha256": _file_sha256(paths["plan"]),
        "state_sha256": _file_sha256(paths["state"]),
    }
    _copy_current_snapshot(paths, destination, manifest)
    validation = validate_project(destination)
    if not validation["valid"]:
        raise PyramidError("Pre-upgrade snapshot validation failed:\n- " + "\n- ".join(validation["errors"]))
    return archive_id, destination


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


def _purge_current(
    paths: dict[str, Path],
    *,
    preserve_baseline: bool = False,
    preserve_dossiers: bool = False,
) -> None:
    directory_keys = ["events", "reports", "docs"]
    if not preserve_dossiers:
        directory_keys.append("dossiers")
    for key in directory_keys:
        target = paths[key]
        if target.exists():
            shutil.rmtree(target)
    file_keys = ["plan", "state", "project", "assurance", "graph", "ready", "html"]
    if not preserve_baseline:
        file_keys.append("baseline")
    for key in file_keys:
        target = paths[key]
        if target.exists():
            target.unlink()


def _initialize_current(
    paths: dict[str, Path],
    plan: dict[str, Any],
    actor: str,
    payload: dict[str, Any],
    *,
    mode: str = "greenfield",
    baseline: dict[str, Any] | None = None,
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
    manifest = default_project_manifest(plan_id=plan["plan_id"], mode=mode, actor=actor, created_at=timestamp)
    write_json(paths["project"], manifest)
    if mode == "brownfield":
        next_baseline = copy.deepcopy(baseline) if baseline is not None else default_baseline(actor=actor)
        next_assurance = default_assurance(
            plan_id=plan["plan_id"], baseline=next_baseline, actor=actor
        )
        write_json(paths["baseline"], next_baseline)
        write_json(paths["assurance"], next_assurance)
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
        "payload": {**payload, "mode": mode, "project_format_version": PROJECT_FORMAT_VERSION},
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
    manifest, current_baseline, _ = load_assurance_bundle(paths, current)
    next_mode = manifest.get("mode") if manifest else detect_repository_mode(paths["root"])
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
        _purge_current(
            paths,
            preserve_baseline=next_mode == "brownfield" and current_baseline is not None,
            preserve_dossiers=True,
        )
        _, event = _initialize_current(
            paths,
            candidate,
            actor,
            {"reset_from_archive": archived["archive_id"], "reason": reason},
            mode=next_mode,
            baseline=current_baseline,
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
        source_dossiers = source / ".pyramid" / "dossiers"
        if source_dossiers.exists():
            shutil.copytree(source_dossiers, paths["dossiers"])
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
        "project": _file_sha256(paths["project"]) if paths["project"].exists() else None,
        "baseline": _file_sha256(paths["baseline"]) if paths["baseline"].exists() else None,
        "assurance": _file_sha256(paths["assurance"]) if paths["assurance"].exists() else None,
        "events": sorted((path.name, _file_sha256(path)) for path in paths["events"].glob("*.json")),
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
    compiled = compile_project(project)
    preserved = (
        canonical["plan"] == _file_sha256(paths["plan"])
        and canonical["state"] == _file_sha256(paths["state"])
        and canonical["project"] == (_file_sha256(paths["project"]) if paths["project"].exists() else None)
        and canonical["baseline"] == (_file_sha256(paths["baseline"]) if paths["baseline"].exists() else None)
        and canonical["assurance"] == (_file_sha256(paths["assurance"]) if paths["assurance"].exists() else None)
        and canonical["events"] == sorted((path.name, _file_sha256(path)) for path in paths["events"].glob("*.json"))
        and canonical["reports"] == (sorted((path.name, _file_sha256(path)) for path in paths["reports"].glob("*")) if paths["reports"].exists() else [])
        and canonical["dossiers"] == (sorted((path.name, _file_sha256(path)) for path in paths["dossiers"].glob("*")) if paths["dossiers"].exists() else [])
    )
    if not preserved:
        raise PyramidError("Clean safety check failed: canonical data changed")
    return {"status": "clean", "removed": removed, "canonical_preserved": True, **compiled}


def inspect_lifecycle(project: str | Path) -> dict[str, Any]:
    paths = project_paths(project)
    archives = list_archives(project)
    if not paths["plan"].exists():
        return {"schema": "pyramid-lifecycle-v1", "current": None, "archives": archives}
    paths, plan, state = load_project(project)
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    errors = (
        completion_errors(plan, state, baseline, assurance)
        if lifecycle_status(state) == "active"
        else []
    )
    return {
        "schema": "pyramid-lifecycle-v1",
        "plan_id": plan["plan_id"],
        "graph_version": state["graph_version"],
        "lifecycle": copy.deepcopy(lifecycle_state(state)),
        "closure_ready": lifecycle_status(state) == "active" and not errors,
        "closure_blockers": errors,
        "active_claims": active_claims(state),
        "project": copy.deepcopy(manifest) if manifest else {
            "format_version": "legacy-v2",
            "mode": "legacy",
        },
        "assurance": assurance_summary(baseline, assurance)
        if baseline is not None and assurance is not None
        else None,
        "archives": archives,
    }


def inspect_project(
    project: str | Path,
    *,
    summary: bool = False,
    ready: bool = False,
    blocked: bool = False,
    pending_audits: bool = False,
    assurance_view: bool = False,
    nid: str | None = None,
) -> dict[str, Any]:
    paths, plan, state = load_project(project)
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    snapshot = graph_snapshot(plan, state, baseline, assurance, manifest)
    if assurance_view:
        if baseline is None or assurance is None:
            return {
                "schema": "pyramid-assurance-query-v1",
                "mode": manifest.get("mode") if manifest else "legacy",
                "assurance": None,
                "message": "This project has no brownfield assurance bundle.",
            }
        return {
            "schema": "pyramid-assurance-query-v1",
            "mode": manifest.get("mode") if manifest else "brownfield",
            "graph_version": state["graph_version"],
            "summary": assurance_summary(baseline, assurance),
            "baseline": copy.deepcopy(baseline),
            "assurance": copy.deepcopy(assurance),
        }
    if nid:
        return task_packet(plan, state, nid, baseline, assurance)
    if ready:
        tasks = [
            task_packet(plan, state, node["id"], baseline, assurance)
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
        "project": copy.deepcopy(manifest) if manifest else {
            "format_version": "legacy-v2",
            "mode": "legacy",
        },
        "assurance": assurance_summary(baseline, assurance)
        if baseline is not None and assurance is not None
        else None,
        "closure_ready": lifecycle_status(state) == "active"
        and not completion_errors(plan, state, baseline, assurance),
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
    errors = validate_plan(plan) + validate_state(plan, state) + assurance_validation_errors(paths, plan)
    manifest = load_json(paths["project"]) if paths["project"].exists() else None
    return {
        "valid": not errors,
        "errors": errors,
        "plan_id": plan.get("plan_id"),
        "revision": plan.get("revision"),
        "graph_version": state.get("graph_version"),
        "project_format_version": manifest.get("format_version") if manifest else "legacy-v2",
        "mode": manifest.get("mode") if manifest else "legacy",
    }
