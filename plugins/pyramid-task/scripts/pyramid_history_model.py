"""Pure chronicle, summary, query and index values from loaded records."""
from __future__ import annotations
import copy
from typing import Any
from pyramid_history_contracts import HistoryError, _nonempty_string

def _change_bindings(plan: dict[str, Any], state: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bindings = []
    for node in plan.get("nodes", []):
        item = state.get("nodes", {}).get(node.get("id"), {})
        result = item.get("last_result")
        if not isinstance(result, dict):
            continue
        bindings.append(
            {
                "task": node["id"],
                "purpose": node.get("summary"),
                "changed_files": sorted(set(result.get("changed_files", []))),
                "changed_assets": sorted(set(result.get("changed_assets", []))),
                "implementation_events": [
                    event["id"]
                    for event in events
                    if event.get("node") == node["id"]
                    and event.get("type") == "task.implemented"
                ],
                "checks": copy.deepcopy(result.get("checks", [])),
                "acceptance_evidence": copy.deepcopy(result.get("acceptance_evidence", [])),
            }
        )
    return bindings




def _journey(plan: dict[str, Any], state: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = []
    for node in sorted(plan.get("nodes", []), key=lambda item: (item.get("wave", 0), item.get("level", 0), item.get("id", ""))):
        if node.get("selection") != "primary" or node.get("kind") != "outcome":
            continue
        node_state = state.get("nodes", {}).get(node["id"], {})
        outcomes.append(
            {
                "id": node["id"],
                "title": node.get("title"),
                "summary": node.get("summary"),
                "verification": node_state.get("verification"),
                "last_audit": copy.deepcopy(node_state.get("last_audit")),
            }
        )
    turning_types = {
        "plan.replanned",
        "task.amended",
        "task.expanded",
        "task.reopened",
        "task.blocked",
        "task.at-risk",
        "audit.fail",
    }
    turning_points = [event for event in events if event.get("type") in turning_types]
    return {
        "decisions": copy.deepcopy(plan.get("decisions", [])),
        "demonstrable_outcomes": outcomes,
        "event_refs": events,
        "turning_points": turning_points,
    }


def _effective_chronicle(record: dict[str, Any], bindings: list[dict[str, Any]], current_id: str | None) -> dict[str, Any]:
    item = copy.deepcopy(record)
    item["code_bindings"] = copy.deepcopy(bindings)
    item["current_applicability"] = "current" if item.get("chronicle_id") == current_id else "historical"
    if bindings:
        item["effective_replay_fidelity"] = bindings[-1].get("replay_fidelity", "artifact-identical")
        item["bound_commit"] = bindings[-1].get("commit")
    else:
        item["effective_replay_fidelity"] = item.get("replay", {}).get("fidelity", "partial")
        item["bound_commit"] = (
            item.get("replay", {}).get("end_commit")
            if item["effective_replay_fidelity"] == "artifact-identical"
            else None
        )
    if item["effective_replay_fidelity"] == "artifact-identical":
        item["binding_status"] = "established"
        item["binding_next_action"] = None
    elif not item.get("replay", {}).get("start_commit"):
        item["binding_status"] = "unavailable"
        item["binding_next_action"] = (
            "No Git commit was captured at intent start; retain the partial replay record."
        )
    elif item.get("outcome") == "completed":
        item["binding_status"] = "pending"
        item["binding_next_action"] = (
            "Commit the implementation, ensure the worktree is clean, then bind this chronicle."
        )
    else:
        item["binding_status"] = "optional"
        item["binding_next_action"] = (
            "Bind a clean descendant commit only if this incomplete intent must be reproduced exactly."
        )
    return item


def chronicles_from_records(
    records: list[dict[str, Any]], current_plan_id: str | None = None
) -> list[dict[str, Any]]:
    chronicles = [item for item in records if item.get("record_type") == "intent-chronicle"]
    bindings = [item for item in records if item.get("record_type") == "code-binding"]
    current_id = next(
        (
            item.get("chronicle_id")
            for item in reversed(chronicles)
            if current_plan_id is not None and item.get("plan_id") == current_plan_id
        ),
        None,
    )
    if current_plan_id is None and chronicles:
        current_id = chronicles[-1].get("chronicle_id")
    return [
        _effective_chronicle(
            chronicle,
            [item for item in bindings if item.get("chronicle_id") == chronicle.get("chronicle_id")],
            current_id,
        )
        for chronicle in chronicles
    ]


def summary_from_chronicles(
    chronicles: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema": "pyramid-history-summary-v1",
        "chronicles": [
            {
                "chronicle_id": item["chronicle_id"],
                "plan_id": item["plan_id"],
                "title": item["title"],
                "recorded_at": item["recorded_at"],
                "outcome": item["outcome"],
                "intent": item.get("intent", {}).get("statement"),
                "path": item.get("human_story", {}).get("path", []),
                "progress": item.get("human_story", {}).get("progress", []),
                "turning_points": item.get("human_story", {}).get("turning_points", []),
                "ending": item.get("human_story", {}).get("ending"),
                "why_this_result": item.get("human_story", {}).get("why_this_result"),
                "changed_files": len(item.get("provenance_coverage", {}).get("declared_files", [])),
                "provenance_status": item.get("provenance_coverage", {}).get("status"),
                "replay_fidelity": item.get("effective_replay_fidelity"),
                "bound_commit": item.get("bound_commit"),
                "binding_status": item.get("binding_status"),
                "binding_next_action": item.get("binding_next_action"),
                "current_applicability": item.get("current_applicability"),
            }
            for item in chronicles
        ],
    }


def index_from_records(
    records: list[dict[str, Any]], generated_at: str
) -> dict[str, Any]:
    index = {
        "schema": "pyramid-history-index-v1",
        "generated_at": generated_at,
        "chronicles": [
            {
                "chronicle_id": item["chronicle_id"],
                "plan_id": item["plan_id"],
                "title": item["title"],
                "outcome": item["outcome"],
                "recorded_at": item["recorded_at"],
            }
            for item in records
            if item.get("record_type") == "intent-chronicle"
        ],
        "files": {},
        "commits": {},
    }
    for item in records:
        if item.get("record_type") == "intent-chronicle":
            for path in item.get("provenance_coverage", {}).get("declared_files", []):
                index["files"].setdefault(path, []).append(item["chronicle_id"])
            for commit in (
                item.get("replay", {}).get("start_commit"),
                item.get("replay", {}).get("end_commit"),
            ):
                if commit:
                    index["commits"].setdefault(commit, []).append(item["chronicle_id"])
        elif item.get("record_type") == "code-binding" and item.get("commit"):
            index["commits"].setdefault(item["commit"], []).append(item["chronicle_id"])
    index["files"] = dict(sorted(index["files"].items()))
    index["commits"] = dict(sorted(index["commits"].items()))
    return index


def query_from_chronicles(
    chronicles: list[dict[str, Any]],
    starting_records: list[dict[str, Any]],
    summary: dict[str, Any] | None,
    *,
    intent: str | None = None,
    path: str | None = None,
    commit: str | None = None,
    replay: str | None = None,
) -> dict[str, Any]:
    if replay:
        matches = [item for item in chronicles if item["chronicle_id"] == replay or item["plan_id"] == replay]
        if not matches:
            raise HistoryError(f"Unknown intent chronicle: {replay}")
        item = matches[-1]
        return {
            "schema": "pyramid-replay-context-v1",
            "chronicle_id": item["chronicle_id"],
            "plan_id": item["plan_id"],
            "fidelity": item["effective_replay_fidelity"],
            "bound_commit": item.get("bound_commit"),
            "binding_status": item.get("binding_status"),
            "binding_next_action": item.get("binding_next_action"),
            "starting_plan": next(
                (
                    record.get("starting_plan")
                    for record in starting_records
                    if record.get("record_id") == item.get("start_record", {}).get("record_id")
                ),
                None,
            ),
            "ending_plan": item.get("ending_plan"),
            "change_bindings": item.get("change_bindings", []),
            "commands": item.get("replay", {}).get("commands", []),
            "limitations": item.get("replay", {}).get("limitations", []),
            "execution_policy": "preview-only; execute commands only with normal task authorization in an isolated worktree",
        }
    matches = chronicles
    query = "list"
    if intent:
        query = "intent"
        matches = [item for item in matches if item["plan_id"] == intent or item["chronicle_id"] == intent]
    elif path:
        query = "path"
        normalized = path.removeprefix("./")
        matches = [
            item for item in matches
            if normalized in item.get("provenance_coverage", {}).get("declared_files", [])
            or normalized in item.get("provenance_coverage", {}).get("material_files", [])
        ]
    elif commit:
        query = "commit"
        matches = [
            item for item in matches
            if commit in {
                item.get("replay", {}).get("start_commit"),
                item.get("replay", {}).get("end_commit"),
                item.get("bound_commit"),
            }
        ]
    return {
        "schema": "pyramid-history-query-v1",
        "query": query,
        "value": intent or path or commit,
        "count": len(matches),
        "chronicles": matches if query == "intent" else [
            item for item in summary["chronicles"]
            if item["chronicle_id"] in {match["chronicle_id"] for match in matches}
        ],
    }
