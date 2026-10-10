"""Pure plan validation: plan data in, ordered errors out.

Uses graph constants and proof-contract validation; no project I/O, clock,
process execution or canonical mutation. Existing core imports remain supported.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Iterable

from pyramid_graph import (
    AUDIT_BLOCKING, EDGE_TYPES, EXECUTABLE_KINDS, ID_PATTERN, NODE_KINDS,
    SELECTIONS, START_BLOCKING,
)
from pyramid_verification import validate_contracts


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

def _validate_plan_nodes(nodes, success_ids, errors):
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
            if agent.get("effect", "mixed") not in {
                "source-change",
                "evidence-only",
                "mixed",
            }:
                errors.append(f"{nid}: agent.effect is invalid")
            if "evidence_outputs" in agent and not _is_string_list(
                agent.get("evidence_outputs")
            ):
                errors.append(f"{nid}: agent.evidence_outputs must be a string array")
            generated_outputs = agent.get("generated_outputs", [])
            if not isinstance(generated_outputs, list):
                errors.append(f"{nid}: agent.generated_outputs must be an array")
            else:
                for output_index, output in enumerate(generated_outputs):
                    output_path = f"{nid}: agent.generated_outputs[{output_index}]"
                    if not isinstance(output, dict):
                        errors.append(f"{output_path} must be an object")
                        continue
                    if not isinstance(output.get("pattern"), str) or not output[
                        "pattern"
                    ].strip():
                        errors.append(f"{output_path}.pattern must be non-empty")
                    if not _is_string_list(output.get("asset_ids")) or not output.get(
                        "asset_ids"
                    ):
                        errors.append(
                            f"{output_path}.asset_ids must be a non-empty string array"
                        )
            if node.get("kind") in EXECUTABLE_KINDS and not agent.get("deliverables"):
                errors.append(f"{nid}: executable node needs at least one deliverable")
    return node_map, criterion_ids, requirement_ids

def _validate_plan_assumptions(intent, node_map, errors):
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

def _validate_plan_evidence(plan, node_map, errors):
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
    return evidence_ids

def _validate_plan_decisions(plan, evidence_ids, errors):
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

def _validate_plan_relations(edges, node_map, errors):
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
    return primary_ids, hierarchy, hard_dependencies, contributing_children, validators

def _validate_plan_paths(primary_ids, hierarchy, hard_dependencies, intent_id, node_map, errors):
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

def _validate_plan_joint_gates(edges, node_map, primary_ids, contributing_children, validators, errors):
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
    if plan.get("schema_version") not in (1, 2):
        errors.append("plan.schema_version must be 1 (legacy) or 2 (candidate-bound harness)")
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
    node_map, criterion_ids, requirement_ids = _validate_plan_nodes(nodes, success_ids, errors)
    if intent_id in node_map:
        intent_node = node_map[intent_id]
        if intent_node.get("kind") != "intent" or intent_node.get("level") != 0:
            errors.append("The intent node must have kind intent and level 0")
    else:
        errors.append("intent.id must match a node")
    _validate_plan_assumptions(intent, node_map, errors)
    evidence_ids = _validate_plan_evidence(plan, node_map, errors)
    _validate_plan_decisions(plan, evidence_ids, errors)
    edges = plan.get("edges")
    if not isinstance(edges, list):
        errors.append("edges must be an array")
        edges = []
    primary_ids, hierarchy, hard_dependencies, contributing_children, validators = _validate_plan_relations(edges, node_map, errors)
    _validate_plan_paths(primary_ids, hierarchy, hard_dependencies, intent_id, node_map, errors)
    _validate_plan_joint_gates(edges, node_map, primary_ids, contributing_children, validators, errors)
    uncovered = sorted(success_ids - requirement_ids)
    if uncovered:
        errors.append(f"Intent success evidence is not traced by nodes: {', '.join(uncovered)}")
    if not errors:
        errors.extend(validate_contracts(plan))
    return errors
