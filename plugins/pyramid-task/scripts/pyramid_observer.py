"""Pure observer values from an already-loaded graph; no file or clock access."""
from __future__ import annotations
import copy
from typing import Any

EXECUTABLE_NODE_KINDS = {
    "research",
    "contract",
    "implementation",
    "integration",
    "risk-control",
    "audit",
}


def _check_counts(records: Any) -> dict[str, int]:
    checks = records if isinstance(records, list) else []
    counts = {"passed": 0, "failed": 0, "not_run": 0, "total": 0}
    for check in checks:
        if not isinstance(check, dict):
            continue
        result = check.get("result")
        if result == "passed":
            counts["passed"] += 1
        elif result == "failed":
            counts["failed"] += 1
        else:
            counts["not_run"] += 1
        counts["total"] += 1
    return counts


def _proof_summary(node: dict[str, Any]) -> dict[str, Any]:
    state = node.get("state", {})
    result = state.get("last_result") if isinstance(state.get("last_result"), dict) else {}
    audit = state.get("last_audit") if isinstance(state.get("last_audit"), dict) else {}
    acceptance = result.get("acceptance_evidence") if isinstance(result, dict) else []
    return {
        "verification": state.get("verification", "unverified"),
        "updated_at": state.get("updated_at"),
        "implementation_checks": _check_counts(result.get("checks")),
        "acceptance_checks": _check_counts(acceptance),
        "audit_checks": _check_counts(audit.get("checks")),
        "recommended_action": audit.get("recommended_action"),
    }


def _outcome_status(
    outcome: dict[str, Any],
    gate: dict[str, Any] | None,
    supporting: list[dict[str, Any]],
) -> str:
    related = [outcome, *supporting]
    if gate is not None:
        related.append(gate)
    if outcome.get("state", {}).get("verification") == "passed":
        return "verified"
    if any(
        item.get("state", {}).get("verification") == "failed"
        or item.get("state", {}).get("execution") == "needs-rework"
        or item.get("state", {}).get("health") == "blocked"
        for item in related
    ):
        return "needs-attention"
    if any(item.get("state", {}).get("execution") == "working" for item in related):
        return "in-progress"
    if gate is not None and (
        gate.get("state", {}).get("verification") == "pending"
        or gate.get("state", {}).get("execution") == "implemented"
    ):
        return "proof-pending"
    if gate is not None and gate.get("availability") == "ready":
        return "ready-for-proof"
    if any(item.get("availability") == "ready" for item in related):
        return "work-ready"
    return "planned"


def _target_outcome(node: dict[str, Any], node_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for candidate_id in node.get("goal_trace", []):
        candidate = node_by_id.get(candidate_id)
        if candidate and candidate.get("kind") == "outcome" and candidate.get("selection") == "primary":
            return candidate
    return None


def observer_projection(graph: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a deterministic, human-first read model without adding canonical state."""
    node_by_id = {node["id"]: node for node in nodes}
    intent = node_by_id.get(graph["intent"]["id"], {})
    primary = [node for node in nodes if node.get("selection") == "primary"]
    outcomes = sorted(
        (node for node in primary if node.get("kind") == "outcome"),
        key=lambda node: (-node.get("level", 0), node.get("wave", 0), node["id"]),
    )
    stages: list[dict[str, Any]] = []
    for outcome in outcomes:
        gate = next(
            (node_by_id.get(gate_id) for gate_id in outcome.get("audit_gates", [])),
            None,
        )
        supporting = [
            node
            for node in primary
            if node["id"] != outcome["id"] and outcome["id"] in node.get("goal_trace", [])
        ]
        stages.append(
            {
                "id": outcome["id"],
                "title": outcome["title"],
                "summary": outcome["summary"],
                "status": _outcome_status(outcome, gate, supporting),
                "verification": outcome.get("state", {}).get("verification"),
                "updated_at": outcome.get("state", {}).get("updated_at"),
                "gate": {
                    "id": gate["id"],
                    "title": gate["title"],
                    "summary": gate["summary"],
                    "availability": gate.get("availability"),
                    "verification": gate.get("state", {}).get("verification"),
                    "acceptance_criteria": gate.get("acceptance_criteria", []),
                    "required_evidence": gate.get("required_evidence", []),
                    "proof": gate.get("proof"),
                }
                if gate
                else None,
                "acceptance_criteria": outcome.get("acceptance_criteria", []),
                "required_evidence": outcome.get("required_evidence", []),
                "supporting_work": len(supporting),
                "active_work": sum(
                    node.get("state", {}).get("execution") == "working" for node in supporting
                ),
                "attention_items": sum(
                    node.get("state", {}).get("health") in {"at-risk", "blocked"}
                    or node.get("state", {}).get("verification") == "failed"
                    or node.get("state", {}).get("execution") == "needs-rework"
                    for node in supporting
                ),
            }
        )

    verified_stages = [stage for stage in stages if stage["status"] == "verified"]
    verified_stages.sort(
        key=lambda stage: (stage.get("updated_at") or "", stages.index(stage))
    )
    last_verified = verified_stages[-1] if verified_stages else None
    next_stage = next((stage for stage in stages if stage["status"] != "verified"), None)

    work_items = []
    attention = []
    for node in primary:
        state = node.get("state", {})
        target = _target_outcome(node, node_by_id)
        target_summary = (
            {"id": target["id"], "title": target["title"]} if target else None
        )
        base = {
            "id": node["id"],
            "title": node["title"],
            "summary": node["summary"],
            "kind": node["kind"],
            "owner": state.get("owner"),
            "availability": node.get("availability"),
            "updated_at": state.get("updated_at"),
            "target_outcome": target_summary,
        }
        if state.get("execution") == "working" and state.get("health") != "blocked":
            work_items.append(base)

        issue_type = None
        next_action = None
        if state.get("verification") == "failed" or state.get("execution") == "needs-rework":
            issue_type, next_action = "Failed proof", "Repair the evidence gap, then re-audit."
        elif state.get("health") == "blocked":
            issue_type, next_action = "Blocked", "Resolve the stated blocker before continuing."
        elif state.get("health") == "at-risk":
            issue_type, next_action = "At risk", "Investigate the risk before it affects the next outcome."
        elif state.get("execution") == "paused":
            issue_type, next_action = "Paused handoff", "Resume from the durable handoff or reassign it."
        if issue_type:
            attention.append(
                {
                    **base,
                    "type": issue_type,
                    "reason": state.get("blocker") or "No additional reason was recorded.",
                    "next_action": next_action,
                }
            )

    priority = {"needs-rework": 0, "working": 1, "ready": 2, "paused": 3, "blocked": 4, "locked": 5}
    executable = [node for node in primary if node.get("kind") in EXECUTABLE_NODE_KINDS]
    recommended = min(
        executable or primary or nodes,
        key=lambda node: (
            priority.get(node.get("availability"), 9),
            node.get("wave", 0),
            node.get("level", 0),
            node["id"],
        ),
        default=None,
    )
    recommended_target = _target_outcome(recommended, node_by_id) if recommended else None
    if recommended:
        availability = recommended.get("availability")
        reason = {
            "working": "Continue the active work and record its evidence.",
            "needs-rework": "Repair the failed proof before advancing dependent outcomes.",
            "ready": "This is the next executable task whose prerequisites are satisfied.",
            "paused": "Resume from the handoff before starting duplicate work.",
            "blocked": "Resolve its blocker or choose another ready task.",
            "locked": "No executable work is ready; inspect the blockers on the next outcome.",
        }.get(availability, "Inspect this task as the current planning focus.")
        recommended_view = {
            "id": recommended["id"],
            "title": recommended["title"],
            "summary": recommended["summary"],
            "availability": availability,
            "reason": reason,
            "target_outcome": (
                {"id": recommended_target["id"], "title": recommended_target["title"]}
                if recommended_target
                else None
            ),
        }
    else:
        recommended_view = None

    assurance = graph.get("assurance", {}).get("summary") if graph.get("assurance") else None
    if assurance and (
        assurance.get("status") == "blocked"
        or assurance.get("open_scope_drift", 0)
        or assurance.get("open_material_findings", 0)
    ):
        attention.append(
            {
                "id": "CHANGE-ASSURANCE",
                "title": "Change assurance needs attention",
                "summary": "Brownfield inspection, findings, or scope drift can block acceptance.",
                "kind": "assurance",
                "owner": None,
                "availability": assurance.get("status"),
                "updated_at": None,
                "target_outcome": None,
                "type": "Assurance",
                "reason": (
                    f"{assurance.get('open_scope_drift', 0)} open scope drift; "
                    f"{assurance.get('open_material_findings', 0)} material findings."
                ),
                "next_action": "Reconcile impact and inspection coverage before the affected audit.",
            }
        )

    intent_verified = intent.get("state", {}).get("verification") == "passed"
    return {
        "intent": {
            "id": graph["intent"]["id"],
            "statement": graph["intent"].get("statement") or intent.get("summary"),
            "success_evidence": graph["intent"].get("success_evidence", []),
            "verified": intent_verified,
        },
        "progress": {
            "label": (
                "Intent verified"
                if intent_verified
                else f"{len(verified_stages)} of {len(stages)} outcomes verified"
                if stages
                else f"{graph['summary']['verified_primary_nodes']} of {graph['summary']['primary_nodes']} primary nodes verified"
            ),
            "verified_outcomes": len(verified_stages),
            "outcomes": len(stages),
            "working": len(work_items),
            "attention": len(attention),
            "ready": graph.get("summary", {}).get("availability", {}).get("ready", 0),
        },
        "last_verified": last_verified,
        "next_outcome": next_stage,
        "outcomes": stages,
        "working": sorted(work_items, key=lambda item: (item["title"], item["id"])),
        "attention": sorted(
            attention,
            key=lambda item: (
                {"Failed proof": 0, "Blocked": 1, "Assurance": 2, "At risk": 3, "Paused handoff": 4}.get(item["type"], 9),
                item["title"],
            ),
        ),
        "recommended": recommended_view,
    }


def visualization_snapshot(graph: dict[str, Any]) -> dict[str, Any]:
    node_fields = (
        "id",
        "title",
        "summary",
        "kind",
        "selection",
        "level",
        "wave",
        "workstream",
        "availability",
        "blocked_by",
        "goal_trace",
        "parents",
        "children",
        "dependencies",
        "audit_gates",
        "acceptance_criteria",
        "required_evidence",
        "assurance",
        "source_path",
    )
    state_fields = (
        "execution",
        "verification",
        "health",
        "owner",
        "blocker",
        "updated_at",
        "active_handoff_id",
        "paused_at",
        "paused_by",
        "pause_mode",
        "resume_deadline",
        "last_handoff",
    )
    nodes = []
    for node in graph["nodes"]:
        item = {field: node.get(field) for field in node_fields if field in node}
        item["state"] = {
            field: node.get("state", {}).get(field)
            for field in state_fields
            if field in node.get("state", {})
        }
        item["proof"] = _proof_summary(node)
        nodes.append(item)
    assurance = graph.get("assurance")
    snapshot = {
        "schema": "pyramid-visualization-v3",
        "graph_version": graph["graph_version"],
        "context": graph.get("context"),
        "plan_id": graph.get("plan_id"),
        "title": graph["title"],
        "revision": graph["revision"],
        "intent": {
            "id": graph["intent"]["id"],
            "statement": graph["intent"].get("statement"),
            "success_evidence": graph["intent"].get("success_evidence", []),
        },
        "lifecycle": graph["lifecycle"],
        "summary": graph["summary"],
        "nodes": nodes,
        "edges": graph["edges"],
        "project": {
            "format_version": graph.get("project", {}).get("format_version"),
            "mode": graph.get("project", {}).get("mode", "legacy"),
        },
        "assurance": {"summary": assurance["summary"]} if assurance else None,
        "history": copy.deepcopy(graph.get("history", {"schema": "pyramid-history-summary-v1", "chronicles": []})),
    }
    snapshot["observer"] = observer_projection(graph, nodes)
    return snapshot
