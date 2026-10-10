"""Pure replan and expansion candidates from explicit plan/state/proposal.

Returns candidates/differences or ordered errors; never reads or publishes a
project, takes a lock, obtains time, or invokes the compatibility facade.
"""
from __future__ import annotations
import copy
from typing import Any
from pyramid_errors import PyramidError
from pyramid_graph import AUDIT_BLOCKING, EXECUTABLE_KINDS, ID_PATTERN, edges_from, edges_to, node_map
from pyramid_validation import _is_string_list, validate_plan

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


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return edge["from"], edge["to"], edge["type"]


def prepare_replan(old: dict[str, Any], candidate: dict[str, Any], allow_intent_change: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    if old.get("schema_version") == 2 and candidate.get("schema_version") != 2:
        raise PyramidError("A harness-enabled plan cannot downgrade to legacy unbound verification")
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
    if item.get("owner") or item.get("execution") in {"working", "paused"}:
        errors.append(f"{target}: release the active claim, or resume the paused handoff, before expansion")
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
