from __future__ import annotations

import copy
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HistoryError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_sha256(value: Any) -> str:
    material = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=False)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HistoryError(f"Missing history file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HistoryError(f"Invalid JSON in history file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HistoryError(f"Expected a JSON object in history file {path}")
    return value


def history_paths(meta: Path) -> dict[str, Path]:
    root = meta / "history"
    return {
        "root": root,
        "records": root / "records",
        "head": root / "head.json",
        "index": root / "index.json",
    }


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "intent"


def _record_id(kind: str, plan_id: str, ordinal: int = 1) -> str:
    identity = hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:10].upper()
    suffix = f"-C{ordinal}" if kind == "CHRONICLE" else ""
    return f"{kind}-{_slug(plan_id).upper()}-{identity}{suffix}"


def _head(paths: dict[str, Path]) -> dict[str, Any]:
    if not paths["head"].exists():
        return {
            "schema": "pyramid-history-head-v1",
            "updated_at": None,
            "entries": [],
            "chain_sha256": None,
        }
    return _load_json(paths["head"])


def _append_record(meta: Path, record: dict[str, Any]) -> dict[str, Any]:
    paths = history_paths(meta)
    head = _head(paths)
    errors = history_validation_errors(meta)
    if errors:
        raise HistoryError("History validation failed:\n- " + "\n- ".join(errors))
    filename = f"{record['record_id']}.json"
    destination = paths["records"] / filename
    if destination.exists():
        existing = _load_json(destination)
        if existing == record:
            return existing
        raise HistoryError(f"Immutable history record already exists: {record['record_id']}")
    _write_json(destination, record)
    record_sha256 = _file_sha256(destination)
    previous = head.get("chain_sha256")
    entry = {
        "record_id": record["record_id"],
        "record_type": record["record_type"],
        "plan_id": record["plan_id"],
        "recorded_at": record["recorded_at"],
        "path": f"records/{filename}",
        "sha256": record_sha256,
        "previous_chain_sha256": previous,
    }
    chain_sha256 = _canonical_sha256({"previous": previous, "entry": entry})
    head["updated_at"] = record["recorded_at"]
    head.setdefault("entries", []).append(entry)
    head["chain_sha256"] = chain_sha256
    _write_json(paths["head"], head)
    rebuild_history_index(meta)
    return record


def _git(root: Path, *arguments: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    return result.returncode == 0, result.stdout.strip()


def source_snapshot(root: Path) -> dict[str, Any]:
    available, repository_root = _git(root, "rev-parse", "--show-toplevel")
    if not available:
        return {
            "captured_at": _now(),
            "git": {"available": False, "reason": "Project root is not in a readable Git worktree."},
            "runtime": _runtime_snapshot(),
        }
    _, commit = _git(root, "rev-parse", "HEAD")
    _, tree = _git(root, "rev-parse", "HEAD^{tree}")
    _, tracked = _git(root, "diff", "--name-only", "HEAD", "--")
    _, staged = _git(root, "diff", "--cached", "--name-only", "HEAD", "--")
    _, untracked = _git(root, "ls-files", "--others", "--exclude-standard")
    changed_files = sorted(
        {
            path
            for path in [*tracked.splitlines(), *staged.splitlines(), *untracked.splitlines()]
            if path and not path.startswith(".pyramid/")
        }
    )
    changed_file_sha256 = {
        path: _file_sha256(root / path) if (root / path).is_file() else None
        for path in changed_files
    }
    return {
        "captured_at": _now(),
        "git": {
            "available": True,
            "repository_root": repository_root,
            "commit": commit or None,
            "tree": tree or None,
            "clean": not changed_files,
            "changed_files": changed_files,
            "changed_file_sha256": changed_file_sha256,
        },
        "runtime": _runtime_snapshot(),
    }


def _runtime_snapshot() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
    }


def _records(meta: Path) -> list[dict[str, Any]]:
    paths = history_paths(meta)
    head = _head(paths)
    records: list[dict[str, Any]] = []
    for entry in head.get("entries", []):
        path = paths["root"] / entry.get("path", "")
        if path.exists():
            records.append(_load_json(path))
    return records


def history_contains_plan(meta: Path, plan_id: str) -> bool:
    return any(
        item.get("record_type") == "intent-start" and item.get("plan_id") == plan_id
        for item in _records(meta)
    )


def _record_file_sha256(meta: Path, record_id: str) -> str:
    for entry in _head(history_paths(meta)).get("entries", []):
        if entry.get("record_id") == record_id:
            return str(entry.get("sha256"))
    raise HistoryError(f"History head does not reference record {record_id}")


def history_validation_errors(meta: Path) -> list[str]:
    paths = history_paths(meta)
    if not paths["root"].exists():
        return []
    if not paths["head"].exists():
        return [".pyramid/history exists without history/head.json"]
    try:
        head = _load_json(paths["head"])
    except HistoryError as exc:
        return [str(exc)]
    errors: list[str] = []
    if head.get("schema") != "pyramid-history-head-v1":
        return ["history head schema must be pyramid-history-head-v1"]
    previous: str | None = None
    seen: set[str] = set()
    for entry in head.get("entries", []):
        if not isinstance(entry, dict):
            errors.append("history head entry must be an object")
            continue
        record_id = entry.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            errors.append("history head entry is missing record_id")
            continue
        if record_id in seen:
            errors.append(f"history head repeats record {record_id}")
        seen.add(record_id)
        relative = entry.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            errors.append(f"history record {record_id} has an unsafe path")
            continue
        record_path = paths["root"] / relative
        if not record_path.exists():
            errors.append(f"history record is missing: {record_id}")
            continue
        if _file_sha256(record_path) != entry.get("sha256"):
            errors.append(f"history record hash mismatch: {record_id}")
        if entry.get("previous_chain_sha256") != previous:
            errors.append(f"history chain predecessor mismatch: {record_id}")
        previous = _canonical_sha256({"previous": previous, "entry": entry})
    if head.get("chain_sha256") != previous:
        errors.append("history head chain_sha256 does not match its entries")
    referenced = {
        str((paths["root"] / entry["path"]).resolve())
        for entry in head.get("entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    for record_path in paths["records"].glob("*.json") if paths["records"].exists() else []:
        if str(record_path.resolve()) not in referenced:
            errors.append(f"unreferenced immutable history record: {record_path.name}")
    return errors


def ensure_intent_start(
    meta: Path,
    root: Path,
    plan: dict[str, Any],
    state: dict[str, Any],
    actor: str,
    *,
    transition: dict[str, Any] | None = None,
    legacy_capture: bool = False,
) -> dict[str, Any]:
    starts = [
        item
        for item in _records(meta)
        if item.get("record_type") == "intent-start" and item.get("plan_id") == plan["plan_id"]
    ]
    if starts:
        recorded_created_at = starts[-1].get("starting_state", {}).get("created_at")
        if recorded_created_at != state.get("created_at"):
            raise HistoryError(
                f"Plan ID {plan['plan_id']} already belongs to another recorded intent; "
                "use a new plan_id or restore its archive"
            )
        return starts[-1]
    recent_chronicle = next(
        (item for item in reversed(_records(meta)) if item.get("record_type") == "intent-chronicle"),
        None,
    )
    snapshot = source_snapshot(root)
    record = {
        "schema": "pyramid-intent-start-v1",
        "record_id": _record_id("START", plan["plan_id"]),
        "record_type": "intent-start",
        "plan_id": plan["plan_id"],
        "plan_revision": plan["revision"],
        "title": plan["title"],
        "recorded_at": _now(),
        "recorded_by": actor,
        "capture_quality": "late-partial" if legacy_capture else "at-intent-start",
        "parents": (
            [{"chronicle_id": recent_chronicle["chronicle_id"], "relationship": "extends"}]
            if recent_chronicle
            else []
        ),
        "transition": copy.deepcopy(transition),
        "intent": copy.deepcopy(plan["intent"]),
        "starting_plan": copy.deepcopy(plan),
        "starting_state": {
            "graph_version": state.get("graph_version"),
            "created_at": state.get("created_at"),
            "lifecycle": copy.deepcopy(state.get("lifecycle")),
        },
        "source_snapshot": snapshot,
        "limitations": (
            ["The intent start was reconstructed after work began; its source snapshot is not the original starting state."]
            if legacy_capture
            else []
        ),
    }
    return _append_record(meta, record)


def _event_records(events_dir: Path) -> list[dict[str, Any]]:
    events = []
    if events_dir.exists():
        for path in events_dir.glob("*.json"):
            try:
                event = _load_json(path)
            except HistoryError:
                continue
            events.append((int(event.get("graph_version", 0)), str(event.get("at", "")), path, event))
    events.sort(key=lambda item: (item[0], item[1], item[2].name))
    return [
        {
            "id": event.get("id"),
            "type": event.get("type"),
            "node": event.get("node"),
            "actor": event.get("actor"),
            "at": event.get("at"),
            "graph_version": event.get("graph_version"),
            "sha256": _file_sha256(path),
        }
        for _, _, path, event in events
    ]


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


def _material_git_changes(start: dict[str, Any], end: dict[str, Any], root: Path) -> tuple[list[str], list[str]]:
    start_git = start.get("source_snapshot", {}).get("git", {})
    end_git = end.get("git", {})
    if not start_git.get("available") or not end_git.get("available") or not start_git.get("commit"):
        return [], ["A Git start/end comparison is unavailable."]
    ok, changed = _git(root, "diff", "--name-only", str(start_git["commit"]), "--")
    files = set(changed.splitlines()) if ok and changed else set()
    files.update(end_git.get("changed_files", []))
    material = sorted(
        path for path in files
        if path and not path.startswith(".pyramid/") and not path.startswith("docs/tasks/")
    )
    start_hashes = start_git.get("changed_file_sha256", {})
    end_hashes = end_git.get("changed_file_sha256", {})
    material = [
        path
        for path in material
        if path not in start_hashes or start_hashes.get(path) != end_hashes.get(path)
    ]
    return material, [] if ok else ["Git could not compare the recorded start commit with the ending worktree."]


def record_intent_chronicle(
    meta: Path,
    root: Path,
    plan: dict[str, Any],
    state: dict[str, Any],
    actor: str,
    *,
    outcome: str,
    reason: str | None,
    report_path: Path | None,
    dossier_path: Path | None,
    closing_event: dict[str, Any],
) -> dict[str, Any]:
    start = ensure_intent_start(meta, root, plan, state, actor, legacy_capture=True)
    prior = [
        item for item in _records(meta)
        if item.get("record_type") == "intent-chronicle" and item.get("plan_id") == plan["plan_id"]
    ]
    ordinal = len(prior) + 1
    events = _event_records(meta / "events")
    bindings = _change_bindings(plan, state, events)
    end_snapshot = source_snapshot(root)
    material_files, comparison_limits = _material_git_changes(start, end_snapshot, root)
    declared_files = sorted({path for binding in bindings for path in binding["changed_files"]})
    gaps = sorted(set(material_files) - set(declared_files))
    unobserved_declared = sorted(set(declared_files) - set(material_files))
    if not end_snapshot.get("git", {}).get("available"):
        coverage_status = "unavailable"
    elif gaps or unobserved_declared:
        coverage_status = "partial"
    else:
        coverage_status = "complete"
    clean_committed_range = bool(
        start.get("source_snapshot", {}).get("git", {}).get("commit")
        and end_snapshot.get("git", {}).get("commit")
        and end_snapshot.get("git", {}).get("clean")
        and start.get("source_snapshot", {}).get("git", {}).get("commit")
        != end_snapshot.get("git", {}).get("commit")
    )
    if clean_committed_range and coverage_status == "complete":
        fidelity = "artifact-identical"
    elif coverage_status == "complete" and bindings:
        fidelity = "behaviorally-equivalent"
    else:
        fidelity = "partial"
    limitations = list(start.get("limitations", [])) + comparison_limits
    dirty_at_start = start.get("source_snapshot", {}).get("git", {}).get("changed_files", [])
    if dirty_at_start:
        limitations.append(
            f"The intent began with {len(dirty_at_start)} pre-existing dirty files; unchanged content was excluded and changed content still requires an explicit task binding."
        )
    if not clean_committed_range:
        limitations.append(
            "The ending implementation is not bound to a distinct clean Git commit; use a later code-binding record for artifact-identical replay."
        )
    if gaps:
        limitations.append("Material Git changes without task bindings: " + ", ".join(gaps))
    if unobserved_declared:
        limitations.append(
            "Task-declared files not observed in the Git start/end delta: "
            + ", ".join(unobserved_declared)
        )
    commands = []
    for binding in bindings:
        for check in binding["checks"]:
            if isinstance(check, dict) and check.get("command"):
                commands.append(
                    {"task": binding["task"], "command": check["command"], "recorded_result": check.get("result")}
                )
    report = (
        {"path": str(report_path.relative_to(root)), "sha256": _file_sha256(report_path)}
        if report_path and report_path.exists()
        else None
    )
    dossier = (
        {"path": str(dossier_path.relative_to(root)), "sha256": _file_sha256(dossier_path)}
        if dossier_path and dossier_path.exists()
        else None
    )
    record_id = _record_id("CHRONICLE", plan["plan_id"], ordinal)
    journey = _journey(plan, state, events)
    title_by_id = {node["id"]: node.get("title", node["id"]) for node in plan.get("nodes", [])}
    progress = []
    for item in events:
        event_type = item.get("type")
        if event_type == "task.implemented":
            progress.append(f"Implemented {title_by_id.get(item.get('node'), item.get('node'))}.")
        elif event_type == "audit.pass" and item.get("node") in title_by_id:
            progress.append(f"Accepted evidence for {title_by_id[item['node']]}.")
        elif event_type == "audit.fail" and item.get("node") in title_by_id:
            progress.append(f"Evidence failed for {title_by_id[item['node']]} and required repair.")
    decision_reasons = [
        f"{str(item.get('choice')).rstrip('.')} — {str(item.get('rationale')).rstrip('.')}"
        for item in plan.get("decisions", [])
        if item.get("choice") and item.get("rationale")
    ]
    turning_points = [
        f"Decision: {item}" for item in decision_reasons
    ] + [
        f"{item.get('type')} at graph version {item.get('graph_version')}"
        for item in journey["turning_points"]
    ]
    record = {
        "schema": "pyramid-intent-chronicle-v1",
        "record_id": record_id,
        "record_type": "intent-chronicle",
        "chronicle_id": record_id,
        "plan_id": plan["plan_id"],
        "plan_revision": plan["revision"],
        "graph_version": state.get("graph_version"),
        "title": plan["title"],
        "recorded_at": _now(),
        "recorded_by": actor,
        "outcome": outcome,
        "reason": reason,
        "parents": copy.deepcopy(start.get("parents", [])),
        "previous_chronicle": prior[-1]["chronicle_id"] if prior else None,
        "start_record": {
            "record_id": start["record_id"],
            "sha256": _record_file_sha256(meta, start["record_id"]),
        },
        "start_snapshot": copy.deepcopy(start["source_snapshot"]),
        "end_snapshot": end_snapshot,
        "intent": copy.deepcopy(plan["intent"]),
        "ending_plan": copy.deepcopy(plan),
        "journey": journey,
        "change_bindings": bindings,
        "provenance_coverage": {
            "status": coverage_status,
            "material_files": material_files,
            "declared_files": declared_files,
            "unbound_files": gaps,
            "unobserved_declared_files": unobserved_declared,
        },
        "replay": {
            "fidelity": fidelity,
            "start_commit": start.get("source_snapshot", {}).get("git", {}).get("commit"),
            "end_commit": end_snapshot.get("git", {}).get("commit"),
            "commands": commands,
            "limitations": sorted(set(limitations)),
        },
        "report": report,
        "change_dossier": dossier,
        "closing_event": {
            "id": closing_event.get("id"),
            "type": closing_event.get("type"),
            "at": closing_event.get("at"),
        },
        "human_story": {
            "starting_point": (
                f"Started from Git commit {start.get('source_snapshot', {}).get('git', {}).get('commit')}."
                if start.get("source_snapshot", {}).get("git", {}).get("commit")
                else "Started without a reproducible Git commit binding."
            ),
            "intent": plan["intent"].get("statement"),
            "path": [item["title"] for item in journey["demonstrable_outcomes"]],
            "progress": progress,
            "turning_points": turning_points,
            "ending": (
                "The intent ended with all required primary evidence verified."
                if outcome == "completed"
                else "The intent was archived before formal completion."
            ),
            "why_this_result": (
                "The selected decisions were " + "; ".join(decision_reasons) + "."
                if decision_reasons
                else (
                    f"{len(journey['demonstrable_outcomes'])} demonstrable outcomes and "
                    f"{len(bindings)} implementation result bindings explain the delivered shape."
                )
            ),
        },
    }
    return _append_record(meta, record)


def record_code_binding(
    meta: Path,
    root: Path,
    chronicle_reference: str,
    actor: str,
) -> dict[str, Any]:
    chronicles = [item for item in _records(meta) if item.get("record_type") == "intent-chronicle"]
    matches = [
        item for item in chronicles
        if item.get("chronicle_id") == chronicle_reference or item.get("plan_id") == chronicle_reference
    ]
    if not matches:
        raise HistoryError(f"Unknown intent chronicle: {chronicle_reference}")
    chronicle = matches[-1]
    snapshot = source_snapshot(root)
    git = snapshot.get("git", {})
    if not git.get("available") or not git.get("commit") or not git.get("clean"):
        raise HistoryError("Code binding requires a clean Git worktree with a readable HEAD commit")
    start_commit = chronicle.get("replay", {}).get("start_commit")
    if not start_commit:
        raise HistoryError(
            "Code binding requires a Git commit captured at intent start; this late history can remain partial"
        )
    ancestor, _ = _git(root, "merge-base", "--is-ancestor", str(start_commit), str(git["commit"]))
    if not ancestor:
        raise HistoryError("The binding commit does not descend from the recorded intent start")
    compared, changed = _git(
        root, "diff", "--name-only", f"{start_commit}..{git['commit']}", "--"
    )
    if not compared:
        raise HistoryError("Git could not compare the intent start and binding commits")
    material_files = sorted(
        path
        for path in changed.splitlines()
        if path and not path.startswith(".pyramid/") and not path.startswith("docs/tasks/")
    )
    declared_files = chronicle.get("provenance_coverage", {}).get("declared_files", [])
    unbound_files = sorted(set(material_files) - set(declared_files))
    uncommitted_claims = sorted(set(declared_files) - set(material_files))
    if unbound_files or uncommitted_claims:
        details = []
        if unbound_files:
            details.append("unbound committed files: " + ", ".join(unbound_files))
        if uncommitted_claims:
            details.append("declared files absent from the commit range: " + ", ".join(uncommitted_claims))
        raise HistoryError(
            "Code binding cannot claim artifact-identical provenance; " + "; ".join(details)
        )
    existing = [
        item for item in _records(meta)
        if item.get("record_type") == "code-binding"
        and item.get("chronicle_id") == chronicle["chronicle_id"]
        and item.get("commit") == git["commit"]
    ]
    if existing:
        return existing[-1]
    ordinal = len([item for item in _records(meta) if item.get("record_type") == "code-binding"]) + 1
    record = {
        "schema": "pyramid-code-binding-v1",
        "record_id": f"BINDING-{ordinal:04d}-{str(git['commit'])[:12].upper()}",
        "record_type": "code-binding",
        "plan_id": chronicle["plan_id"],
        "chronicle_id": chronicle["chronicle_id"],
        "recorded_at": _now(),
        "recorded_by": actor,
        "commit": git["commit"],
        "tree": git.get("tree"),
        "clean": True,
        "start_commit": start_commit,
        "material_files": material_files,
        "provenance_status": "complete",
        "replay_fidelity": "artifact-identical",
    }
    return _append_record(meta, record)


def _effective_chronicle(record: dict[str, Any], bindings: list[dict[str, Any]], current_id: str | None) -> dict[str, Any]:
    item = copy.deepcopy(record)
    item["code_bindings"] = copy.deepcopy(bindings)
    item["current_applicability"] = "current" if item.get("chronicle_id") == current_id else "historical"
    if bindings:
        item["effective_replay_fidelity"] = bindings[-1].get("replay_fidelity", "artifact-identical")
        item["bound_commit"] = bindings[-1].get("commit")
    else:
        item["effective_replay_fidelity"] = item.get("replay", {}).get("fidelity", "partial")
        item["bound_commit"] = None
    return item


def history_chronicles(
    meta: Path, current_plan_id: str | None = None
) -> list[dict[str, Any]]:
    records = _records(meta)
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


def history_summary(
    meta: Path, current_plan_id: str | None = None
) -> dict[str, Any]:
    chronicles = history_chronicles(meta, current_plan_id)
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
                "current_applicability": item.get("current_applicability"),
            }
            for item in chronicles
        ],
    }


def rebuild_history_index(meta: Path) -> dict[str, Any]:
    paths = history_paths(meta)
    if not paths["head"].exists():
        return {
            "schema": "pyramid-history-index-v1",
            "generated_at": _now(),
            "chronicles": [],
            "files": {},
            "commits": {},
        }
    records = _records(meta)
    index = {
        "schema": "pyramid-history-index-v1",
        "generated_at": _now(),
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
    _write_json(paths["index"], index)
    return index


def query_history(
    meta: Path,
    *,
    current_plan_id: str | None = None,
    intent: str | None = None,
    path: str | None = None,
    commit: str | None = None,
    replay: str | None = None,
) -> dict[str, Any]:
    errors = history_validation_errors(meta)
    if errors:
        raise HistoryError("History validation failed:\n- " + "\n- ".join(errors))
    chronicles = history_chronicles(meta, current_plan_id)
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
            "starting_plan": next(
                (
                    record.get("starting_plan")
                    for record in _records(meta)
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
            item for item in history_summary(meta, current_plan_id)["chronicles"]
            if item["chronicle_id"] in {match["chronicle_id"] for match in matches}
        ],
    }
