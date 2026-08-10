from __future__ import annotations

import re
from typing import Any


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
EXECUTION_STATES = {
    "planned",
    "working",
    "paused",
    "implemented",
    "needs-rework",
    "superseded",
}
VERIFICATION_STATES = {"unverified", "pending", "passed", "failed"}
HEALTH_STATES = {"clear", "at-risk", "blocked"}
PLAN_LIFECYCLE_STATES = {"active", "completed", "archived"}
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]*$")


def node_map(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in plan["nodes"]}


def edges_from(
    plan: dict[str, Any], nid: str, types: set[str] | None = None
) -> list[dict[str, Any]]:
    return [
        edge
        for edge in plan["edges"]
        if edge["from"] == nid and (types is None or edge["type"] in types)
    ]


def edges_to(
    plan: dict[str, Any], nid: str, types: set[str] | None = None
) -> list[dict[str, Any]]:
    return [
        edge
        for edge in plan["edges"]
        if edge["to"] == nid and (types is None or edge["type"] in types)
    ]


def start_blockers(
    plan: dict[str, Any], state: dict[str, Any], node: dict[str, Any]
) -> list[str]:
    edge_types = set(START_BLOCKING)
    if node["kind"] == "audit":
        edge_types |= {"integration-requires", "validation-requires"}
    return [
        edge["to"]
        for edge in edges_from(plan, node["id"], edge_types)
        if state["nodes"][edge["to"]]["verification"] != "passed"
    ]


def availability(
    plan: dict[str, Any], state: dict[str, Any], node: dict[str, Any]
) -> str:
    item = state["nodes"][node["id"]]
    if item["verification"] == "passed":
        return "verified"
    if node["kind"] not in EXECUTABLE_KINDS:
        return "not-executable"
    if node["selection"] != "primary" or item["execution"] == "superseded":
        return "not-selected"
    if item["health"] == "blocked":
        return "blocked"
    if item["execution"] == "paused":
        return "paused"
    if item["execution"] == "working":
        return "working"
    if item["execution"] == "implemented":
        return "implemented"
    if item["execution"] == "needs-rework":
        return "locked" if start_blockers(plan, state, node) else "needs-rework"
    if start_blockers(plan, state, node):
        return "locked"
    return "ready"
