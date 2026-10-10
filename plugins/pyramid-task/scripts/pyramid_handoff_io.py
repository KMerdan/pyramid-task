"""Handoff/event collection and repository fingerprint reads.

Reads depend on atomic files and value contracts, never verified project loading.
"""
from __future__ import annotations
import hashlib
import subprocess
from pathlib import Path
from typing import Any
from pyramid_errors import PyramidError
from pyramid_files import load_json, _file_sha256
from pyramid_state import canonical_sha256
from pyramid_handoff import _handoff_record_errors, handoff_version_drift, handoff_fingerprint_drift


def _git_output(root: Path, *args: str) -> str | None:
    """Return a bounded git query without making the runtime depend on Git."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def worktree_fingerprint(root: Path) -> dict[str, Any]:
    """Hash source-tree state while deliberately excluding Pyramid's own metadata."""
    inside = _git_output(root, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        return {"kind": "not-git"}
    head = _git_output(root, "rev-parse", "HEAD")
    branch = _git_output(root, "branch", "--show-current")
    diff_args = ("diff", "--binary", "--", ".", ":(exclude).pyramid/**")
    staged_args = ("diff", "--cached", "--binary", "--", ".", ":(exclude).pyramid/**")
    untracked = _git_output(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        ".",
        ":(exclude).pyramid/**",
    )
    return {
        "kind": "git",
        "head": head,
        "branch": branch or None,
        "unstaged_sha256": hashlib.sha256((_git_output(root, *diff_args) or "").encode("utf-8")).hexdigest(),
        "staged_sha256": hashlib.sha256((_git_output(root, *staged_args) or "").encode("utf-8")).hexdigest(),
        "untracked_sha256": hashlib.sha256((untracked or "").encode("utf-8")).hexdigest(),
    }


def handoff_validation_errors(
    paths: dict[str, Path], plan: dict[str, Any], state: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    event_hashes: dict[str, tuple[str | None, str | None]] = {}
    if paths["events"].exists():
        for event_path in sorted(paths["events"].glob("*.json")):
            try:
                event = load_json(event_path)
            except PyramidError as exc:
                errors.append(str(exc))
                continue
            if event.get("type") != "task.paused":
                continue
            payload = event.get("payload", {})
            if isinstance(payload, dict) and isinstance(payload.get("handoff_id"), str):
                event_hashes[payload["handoff_id"]] = (
                    payload.get("handoff_sha256"),
                    event.get("node"),
                )
    if paths["handoffs"].exists():
        for path in sorted(paths["handoffs"].glob("*.json")):
            try:
                handoff = load_json(path)
            except PyramidError as exc:
                errors.append(str(exc))
                continue
            handoff_id = handoff.get("id")
            if handoff_id != path.stem:
                errors.append(f"{path.name}: handoff.id must match its filename")
            errors.extend(
                f"{path.name}: {error}"
                for error in _handoff_record_errors(handoff, plan_id=plan["plan_id"])
            )
            if isinstance(handoff_id, str):
                records[handoff_id] = handoff
                event_hash = event_hashes.get(handoff_id)
                if event_hash is None:
                    errors.append(f"{path.name}: canonical handoff has no task.paused event")
                else:
                    expected_hash, event_node = event_hash
                    if expected_hash != canonical_sha256(handoff):
                        errors.append(f"{path.name}: content hash no longer matches task.paused")
                    if event_node != handoff.get("task"):
                        errors.append(f"{path.name}: task.paused node does not match handoff.task")
    for handoff_id in sorted(set(event_hashes) - set(records)):
        errors.append(f"task.paused event references missing handoff {handoff_id}")
    for nid, item in state.get("nodes", {}).items():
        handoff_id = item.get("active_handoff_id")
        if item.get("execution") != "paused":
            continue
        if not isinstance(handoff_id, str):
            continue
        handoff = records.get(handoff_id)
        if handoff is None:
            errors.append(f"{nid}: missing active handoff file for {handoff_id}")
            continue
        errors.extend(f"{nid}: {error}" for error in _handoff_record_errors(handoff, plan_id=plan["plan_id"], nid=nid))
        for state_field, handoff_field in (
            ("paused_at", "created_at"),
            ("paused_by", "actor"),
            ("pause_mode", "pause_mode"),
            ("resume_deadline", "resume_deadline"),
        ):
            if item.get(state_field) != handoff.get(handoff_field):
                errors.append(f"{nid}: state.{state_field} does not match the active handoff")
    return errors


def _handoff_fingerprint(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "plan_sha256": _file_sha256(paths["plan"]),
        "baseline_sha256": _file_sha256(paths["baseline"]) if paths["baseline"].exists() else None,
        "assurance_sha256": _file_sha256(paths["assurance"]) if paths["assurance"].exists() else None,
        "worktree": worktree_fingerprint(paths["root"]),
    }


def _handoff_drift(paths: dict[str, Path], state: dict[str, Any], handoff: dict[str, Any]) -> list[str]:
    drift = handoff_version_drift(state, handoff)
    current = _handoff_fingerprint(paths)
    return drift + handoff_fingerprint_drift(handoff, current)
