"""Loss-aware CLI projections. Canonical records and API results remain unchanged."""
from __future__ import annotations

import copy
import json
from typing import Any


def readiness_summary(data: dict[str, Any], project: str, *, stale_reason_count: int = 0) -> dict[str, Any]:
    """Project a fully computed readiness result; never infer or change ready."""
    result = {key: copy.deepcopy(data[key]) for key in (
        'target', 'graph_version', 'context', 'audit_guard', 'ready', 'harness_query',
    )}
    result['schema'] = 'pyramid-audit-readiness-summary-v1'
    counts, omitted = {'global_stale_reasons': stale_reason_count}, {}
    for key, limit, width in (
        ('blockers', 4, 240), ('covered_task_ids', 8, None),
        ('refresh_inspection_ids', 8, None),
    ):
        values = data[key]
        shown = [value if width is None or len(value) <= width else value[:width] + '…'
                 for value in values[:limit]]
        result[key] = shown
        counts[key] = len(values)
        # Count an omitted or abbreviated value once, not every lost character.
        missing = len(values) - len(shown) + sum(a != b for a, b in zip(values, shown))
        if missing:
            omitted[key] = missing
    assurance = data['assurance']
    result['assurance'] = None
    if assurance is not None:
        fields = ('task_ids', 'impact_ids', 'asset_ids', 'inspection_ids',
                  'finding_ids', 'scope_drift_ids', 'blockers')
        result['assurance'] = {'status': assurance['status'],
                               'counts': {key: len(assurance.get(key, [])) for key in fields}}
        for key in fields:
            if assurance.get(key):
                omitted['assurance.' + key] = len(assurance[key])
    result['counts'] = counts
    result['omitted_fields'] = omitted
    result['omitted_count'] = sum(omitted.values())
    result['details_complete'] = not omitted
    result['details_query'] = {
        'command': 'inspect',
        'arguments': ['--project', project, '--audit-readiness', data['target'], '--full', '--json'],
        'observed_context': copy.deepcopy(data['context']),
    }
    result['limitations'] = [
        'Summary presentation does not change readiness; omitted_count counts omitted or abbreviated list values.',
        'Details recompute current readiness. Compare context; source or external state can also change without a context change.',
    ]
    return result


def compact_response(data: dict[str, Any], command: str) -> dict[str, Any]:
    if data.get('schema') == 'pyramid-audit-readiness-summary-v1':
        # This explicit projection already owns its loss accounting.
        return data
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
