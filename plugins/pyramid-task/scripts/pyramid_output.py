"""Loss-aware CLI projections. Canonical records and API results remain unchanged."""
from __future__ import annotations

import copy
import json
from typing import Any


def compact_response(data: dict[str, Any], command: str) -> dict[str, Any]:
    result = copy.deepcopy(data)
    omitted: dict[str, list[str]] = {}
    event = result.get("event")
    if isinstance(event, dict) and event.get("schema") == "pyramid-event-v1":
        removed = [key for key in ("before", "after") if key in event]
        for key in removed:
            event.pop(key)
        event["schema"] = "pyramid-event-reference-v1"
        event["path"] = f".pyramid/events/{event['id']}.json"
        omitted["event"] = removed
    # Only update preserves the contract. A concurrent mutation between commit
    # and packet assembly must fall back to a full packet, not hide new fields.
    # Take/resume always retain all constraints; amend/replan disclose changes.
    packet = result.get("packet")
    same_context = (isinstance(event, dict) and isinstance(packet, dict)
                    and event.get("context_id") is not None
                    and event.get("context_id") == packet.get("context", {}).get("id")
                    and event.get("node") == packet.get("task"))
    if command == "update" and same_context and packet.get("schema") == "agent-task-v1":
        static = (
            "title", "purpose", "kind", "level", "wave", "workstream", "selection",
            "goal_trace", "parents", "children", "required_context", "allowed_write_scope",
            "commands", "deliverables", "non_goals", "acceptance_criteria",
            "required_evidence", "audit_gates", "completion_report_schema",
        )
        removed = [key for key in static if key in packet]
        for key in removed:
            packet.pop(key)
        harness = packet.get("harness")
        if isinstance(harness, dict) and "contracts" in harness:
            harness.pop("contracts")
            omitted["packet.harness"] = ["contracts"]
        packet["schema"] = "agent-status-v1"
        omitted["packet"] = removed
    result["response_format"] = "compact-v1"
    result["omitted_fields"] = omitted
    # Preview/already-small responses need no projection. Never add reference
    # overhead merely because the caller consistently requests compact output.
    if len(json.dumps(result, indent=2, ensure_ascii=False)) >= len(json.dumps(data, indent=2, ensure_ascii=False)):
        return data
    return result
