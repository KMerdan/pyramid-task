"""Handoff value contracts and rendering; no files, clock, Git or facade.

Path objects are value locators here; this module does not inspect the filesystem.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any
from pyramid_errors import PyramidError
from pyramid_validation import _is_string_list
HANDOFF_DRAFT_FIELDS = (
    "progress",
    "changed_files",
    "changed_assets",
    "checks",
    "decisions",
    "assumptions",
    "blockers",
    "risks",
    "next_steps",
    "context_references",
    "external_session_refs",
    "running_resources",
)

def _validate_handoff_draft(draft: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed_fields = {"schema", "summary", "recommended_first_action", *HANDOFF_DRAFT_FIELDS}
    unsupported = sorted(set(draft) - allowed_fields)
    if unsupported:
        errors.append("handoff contains unsupported fields: " + ", ".join(unsupported))
    if draft.get("schema") != "pyramid-handoff-draft-v1":
        errors.append("handoff.schema must be pyramid-handoff-draft-v1")
    for field in ("summary", "recommended_first_action"):
        if not isinstance(draft.get(field), str) or not draft[field].strip():
            errors.append(f"handoff.{field} must be a non-empty string")
    for field in HANDOFF_DRAFT_FIELDS:
        if not isinstance(draft.get(field), list):
            errors.append(f"handoff.{field} must be an array")
    if isinstance(draft.get("changed_files"), list) and not _is_string_list(draft["changed_files"]):
        errors.append("handoff.changed_files must contain strings")
    if isinstance(draft.get("changed_assets"), list) and not _is_string_list(draft["changed_assets"]):
        errors.append("handoff.changed_assets must contain strings")
    if isinstance(draft.get("progress"), list) and not _is_string_list(draft["progress"]):
        errors.append("handoff.progress must contain strings")
    if isinstance(draft.get("assumptions"), list) and not _is_string_list(draft["assumptions"]):
        errors.append("handoff.assumptions must contain strings")
    if isinstance(draft.get("blockers"), list) and not _is_string_list(draft["blockers"]):
        errors.append("handoff.blockers must contain strings")
    if isinstance(draft.get("risks"), list) and not _is_string_list(draft["risks"]):
        errors.append("handoff.risks must contain strings")
    if isinstance(draft.get("next_steps"), list) and not _is_string_list(draft["next_steps"]):
        errors.append("handoff.next_steps must contain strings")
    elif isinstance(draft.get("next_steps"), list) and not draft["next_steps"]:
        errors.append("handoff.next_steps must contain at least one next step")
    if isinstance(draft.get("context_references"), list) and not _is_string_list(draft["context_references"]):
        errors.append("handoff.context_references must contain strings")
    if isinstance(draft.get("external_session_refs"), list) and not _is_string_list(draft["external_session_refs"]):
        errors.append("handoff.external_session_refs must contain strings")
    for field in ("checks", "decisions", "running_resources"):
        if isinstance(draft.get(field), list) and not all(isinstance(item, dict) for item in draft[field]):
            errors.append(f"handoff.{field} must contain objects")
    for index, check in enumerate(draft.get("checks", [])):
        if not isinstance(check, dict):
            continue
        if set(check) != {"command", "result", "notes"}:
            errors.append(f"handoff.checks[{index}] has unsupported or missing fields")
        if not all(isinstance(check.get(field), str) for field in ("command", "result", "notes")):
            errors.append(f"handoff.checks[{index}] needs string command, result, and notes")
        elif check["result"] not in {"passed", "failed", "not-run", "partial"}:
            errors.append(f"handoff.checks[{index}].result is invalid")
    for index, decision in enumerate(draft.get("decisions", [])):
        if not isinstance(decision, dict):
            continue
        if set(decision) != {"decision", "rationale", "reference"}:
            errors.append(f"handoff.decisions[{index}] has unsupported or missing fields")
        if not all(isinstance(decision.get(field), str) for field in ("decision", "rationale", "reference")):
            errors.append(f"handoff.decisions[{index}] needs string decision, rationale, and reference")
    for index, resource in enumerate(draft.get("running_resources", [])):
        if not isinstance(resource, dict):
            continue
        if set(resource) != {"description", "status", "resume_command"}:
            errors.append(f"handoff.running_resources[{index}] has unsupported or missing fields")
        if not all(isinstance(resource.get(field), str) for field in ("description", "status", "resume_command")):
            errors.append(f"handoff.running_resources[{index}] needs string description, status, and resume_command")
    return errors


def _handoff_path(paths: dict[str, Path], handoff_id: str) -> Path:
    if not re.fullmatch(r"HANDOFF-[A-Z0-9-]+", handoff_id):
        raise PyramidError(f"Invalid handoff identifier: {handoff_id}")
    return paths["handoffs"] / f"{handoff_id}.json"


def _handoff_markdown(handoff: dict[str, Any]) -> str:
    def lines(values: list[Any]) -> str:
        if not values:
            return "- None"
        rendered = []
        for value in values:
            if isinstance(value, str):
                rendered.append(f"- {value}")
            else:
                rendered.append(f"- `{json.dumps(value, ensure_ascii=False, sort_keys=True)}`")
        return "\n".join(rendered)

    return f"""<!-- Generated by Pyramid Task V3.2. The JSON record is canonical. -->
# Handoff: {handoff['task']}

## Resume Contract

- Handoff: `{handoff['id']}`
- Plan: `{handoff['plan_id']}` at graph version `{handoff['graph_version']}`
- Paused by: `{handoff['actor']}` at `{handoff['created_at']}`
- Mode: `{handoff['pause_mode']}`
- Resume deadline: `{handoff['resume_deadline'] or 'None'}`
- Reason: {handoff['reason']}

## Summary

{handoff['summary']}

## Recommended First Action

{handoff['recommended_first_action']}

## Progress

{lines(handoff['progress'])}

## Changed Files and Assets

### Files

{lines(handoff['changed_files'])}

### Assets

{lines(handoff['changed_assets'])}

## Checks, Decisions, and Risks

### Checks

{lines(handoff['checks'])}

### Decisions

{lines(handoff['decisions'])}

### Assumptions

{lines(handoff['assumptions'])}

### Blockers

{lines(handoff['blockers'])}

### Risks

{lines(handoff['risks'])}

## Next Steps

{lines(handoff['next_steps'])}

## Context References

{lines(handoff['context_references'])}

## External Sessions and Running Resources

### External Sessions

{lines(handoff['external_session_refs'])}

### Running Resources

{lines(handoff['running_resources'])}
"""


def _handoff_record_errors(
    handoff: dict[str, Any],
    *,
    plan_id: str | None = None,
    nid: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if handoff.get("schema") != "pyramid-handoff-v1":
        errors.append("handoff schema must be pyramid-handoff-v1")
    for field in ("id", "plan_id", "task", "actor", "pause_mode", "reason", "created_at", "summary", "recommended_first_action"):
        if not isinstance(handoff.get(field), str) or not handoff[field].strip():
            errors.append(f"handoff.{field} must be a non-empty string")
    if handoff.get("pause_mode") not in {"hold", "handoff"}:
        errors.append("handoff.pause_mode must be hold or handoff")
    if handoff.get("resume_deadline") is not None and not isinstance(handoff.get("resume_deadline"), str):
        errors.append("handoff.resume_deadline must be a string or null")
    if not isinstance(handoff.get("graph_version"), int) or handoff.get("graph_version", 0) < 1:
        errors.append("handoff.graph_version must be a positive integer")
    for field in HANDOFF_DRAFT_FIELDS:
        if not isinstance(handoff.get(field), list):
            errors.append(f"handoff.{field} must be an array")
    if not isinstance(handoff.get("fingerprint"), dict):
        errors.append("handoff.fingerprint must be an object")
    else:
        fingerprint = handoff["fingerprint"]
        if not isinstance(fingerprint.get("plan_sha256"), str):
            errors.append("handoff.fingerprint.plan_sha256 must be a string")
        for field in ("baseline_sha256", "assurance_sha256"):
            if fingerprint.get(field) is not None and not isinstance(fingerprint.get(field), str):
                errors.append(f"handoff.fingerprint.{field} must be a string or null")
        if not isinstance(fingerprint.get("worktree"), dict):
            errors.append("handoff.fingerprint.worktree must be an object")
    draft_view = {"schema": "pyramid-handoff-draft-v1"}
    for field in ("summary", "recommended_first_action", *HANDOFF_DRAFT_FIELDS):
        draft_view[field] = handoff.get(field)
    errors.extend(_validate_handoff_draft(draft_view))
    if handoff.get("pause_mode") == "hold" and not handoff.get("resume_deadline"):
        errors.append("hold handoff requires resume_deadline")
    if handoff.get("pause_mode") == "handoff" and handoff.get("resume_deadline") is not None:
        errors.append("transfer handoff must not retain a resume_deadline")
    if plan_id is not None and handoff.get("plan_id") != plan_id:
        errors.append("handoff plan_id does not match the current plan")
    if nid is not None and handoff.get("task") != nid:
        errors.append("handoff task does not match the paused node")
    return errors


def handoff_version_drift(state: dict[str, Any], handoff: dict[str, Any]) -> list[str]:
    drift: list[str] = []
    if handoff.get("graph_version") != state.get("graph_version"):
        drift.append(
            f"graph version changed from {handoff.get('graph_version')} to {state.get('graph_version')}"
        )
    return drift


def handoff_fingerprint_drift(handoff: dict[str, Any], current: dict[str, Any]) -> list[str]:
    drift: list[str] = []
    expected = handoff.get("fingerprint", {})
    for key in ("plan_sha256", "baseline_sha256", "assurance_sha256", "worktree"):
        if expected.get(key) != current.get(key):
            drift.append(f"{key} changed since the handoff")
    return drift


def _handoff_drift(state: dict[str, Any], handoff: dict[str, Any], current: dict[str, Any]) -> list[str]:
    return handoff_version_drift(state, handoff) + handoff_fingerprint_drift(handoff, current)
