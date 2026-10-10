"""Shared proof normalization/readiness reads, used by commands and queries.

No command/facade imports; underlying artifact/input validation retains its order.
"""
from __future__ import annotations
from pyramid_errors import PyramidError
from pyramid_verification import normalize_proofs, proof_readiness, VerificationError
from pyramid_graph import node_map, edges_from, edges_to, AUDIT_BLOCKING


def _normalize_proofs(paths, plan, state, nid, payload):
    try:
        return normalize_proofs(paths["root"], plan, state, nid, payload)
    except (VerificationError, OSError) as exc:
        raise PyramidError(f"Invalid harness proof: {exc}") from exc


def _proof_errors(paths, plan, state, targets=None):
    if plan.get("schema_version") != 2:
        return []
    selected = set(targets) if targets is not None else {
        node["id"] for node in plan["nodes"] if node["selection"] == "primary"
    }
    return [f"{nid}: {blocker}" for nid in sorted(selected)
            for blocker in proof_readiness(paths["root"], plan, state, nid)["blockers"]]


def _audit_proof_dependencies(paths, plan, state, node):
    if plan.get("schema_version") != 2:
        return []
    nodes = node_map(plan)
    seen, pending = {node["id"]}, [node["id"]]
    while pending:
        current = pending.pop()
        dependencies = {edge["to"] for edge in edges_from(plan, current, AUDIT_BLOCKING | {"validated-by"})}
        dependencies.update(edge["from"] for edge in edges_to(plan, current, {"contributes-to"}))
        for target in dependencies - seen:
            if nodes[target]["selection"] == "primary":
                seen.add(target)
                pending.append(target)
    return _proof_errors(paths, plan, state, {
        target for target in seen - {node["id"]} if state["nodes"][target]["verification"] == "passed"
    })
