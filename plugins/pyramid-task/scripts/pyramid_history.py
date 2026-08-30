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


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
GIT_OBJECT_PATTERN = re.compile(r"^[a-f0-9]{40,64}$")
RECORD_ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]*$")

START_FIELDS = {
    "schema",
    "record_id",
    "record_type",
    "plan_id",
    "plan_revision",
    "title",
    "recorded_at",
    "recorded_by",
    "capture_quality",
    "parents",
    "transition",
    "intent",
    "starting_plan",
    "starting_state",
    "source_snapshot",
    "limitations",
}
CHRONICLE_FIELDS = {
    "schema",
    "record_id",
    "record_type",
    "chronicle_id",
    "plan_id",
    "plan_revision",
    "graph_version",
    "title",
    "recorded_at",
    "recorded_by",
    "outcome",
    "reason",
    "parents",
    "previous_chronicle",
    "start_record",
    "start_snapshot",
    "end_snapshot",
    "intent",
    "ending_plan",
    "journey",
    "change_bindings",
    "provenance_coverage",
    "replay",
    "report",
    "change_dossier",
    "closing_event",
    "human_story",
}
BINDING_FIELDS = {
    "schema",
    "record_id",
    "record_type",
    "plan_id",
    "chronicle_id",
    "recorded_at",
    "recorded_by",
    "commit",
    "tree",
    "clean",
    "start_commit",
    "material_files",
    "provenance_status",
    "replay_fidelity",
}
RECORD_FIELDS = {
    "intent-start": START_FIELDS,
    "intent-chronicle": CHRONICLE_FIELDS,
    "code-binding": BINDING_FIELDS,
}
HEAD_FIELDS = {"schema", "updated_at", "entries", "chain_sha256"}
ENTRY_FIELDS = {
    "record_id",
    "record_type",
    "plan_id",
    "recorded_at",
    "path",
    "sha256",
    "previous_chain_sha256",
}


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


def _serialized_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")


def _sync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_serialized_json(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
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
        "transaction": root / "transaction.json",
    }


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _snapshot_errors(snapshot: Any, label: str) -> list[str]:
    if not isinstance(snapshot, dict):
        return [f"{label} must be an object"]
    required = {"captured_at", "git", "runtime"}
    errors = [f"{label} is missing {field}" for field in sorted(required - set(snapshot))]
    if not _nonempty_string(snapshot.get("captured_at")):
        errors.append(f"{label}.captured_at must be a non-empty string")
    if not isinstance(snapshot.get("git"), dict):
        errors.append(f"{label}.git must be an object")
    if not isinstance(snapshot.get("runtime"), dict):
        errors.append(f"{label}.runtime must be an object")
    return errors


def _record_validation_errors(record: Any) -> list[str]:
    if not isinstance(record, dict):
        return ["history record must be an object"]
    record_id = record.get("record_id")
    record_type = record.get("record_type")
    prefix = str(record_id or "history record")
    fields = RECORD_FIELDS.get(record_type)
    if fields is None:
        return [f"{prefix}: invalid record_type"]
    errors = [f"{prefix}: missing {field}" for field in sorted(fields - set(record))]
    errors.extend(
        f"{prefix}: unexpected field {field}" for field in sorted(set(record) - fields)
    )
    if not isinstance(record_id, str) or not RECORD_ID_PATTERN.fullmatch(record_id):
        errors.append(f"{prefix}: invalid record_id")
    for field in ("plan_id", "recorded_at", "recorded_by"):
        if not _nonempty_string(record.get(field)):
            errors.append(f"{prefix}: {field} must be a non-empty string")

    if record_type == "intent-start":
        if record.get("schema") != "pyramid-intent-start-v1":
            errors.append(f"{prefix}: invalid intent-start schema")
        if not isinstance(record.get("plan_revision"), int) or record["plan_revision"] < 1:
            errors.append(f"{prefix}: plan_revision must be a positive integer")
        if not _nonempty_string(record.get("title")):
            errors.append(f"{prefix}: title must be a non-empty string")
        if record.get("capture_quality") not in {"at-intent-start", "late-partial"}:
            errors.append(f"{prefix}: invalid capture_quality")
        if not isinstance(record.get("parents"), list) or not all(
            isinstance(item, dict) and _nonempty_string(item.get("chronicle_id"))
            for item in record.get("parents", [])
        ):
            errors.append(f"{prefix}: parents must contain chronicle references")
        if record.get("transition") is not None and not isinstance(record.get("transition"), dict):
            errors.append(f"{prefix}: transition must be an object or null")
        for field in ("intent", "starting_plan", "starting_state"):
            if not isinstance(record.get(field), dict):
                errors.append(f"{prefix}: {field} must be an object")
        errors.extend(_snapshot_errors(record.get("source_snapshot"), f"{prefix}.source_snapshot"))
        if not _string_list(record.get("limitations")):
            errors.append(f"{prefix}: limitations must be a string array")

    elif record_type == "intent-chronicle":
        if record.get("schema") != "pyramid-intent-chronicle-v1":
            errors.append(f"{prefix}: invalid intent-chronicle schema")
        if record.get("chronicle_id") != record_id:
            errors.append(f"{prefix}: chronicle_id must equal record_id")
        for field in ("plan_revision", "graph_version"):
            if not isinstance(record.get(field), int) or record[field] < 1:
                errors.append(f"{prefix}: {field} must be a positive integer")
        if not _nonempty_string(record.get("title")):
            errors.append(f"{prefix}: title must be a non-empty string")
        if record.get("outcome") not in {"completed", "archived-incomplete"}:
            errors.append(f"{prefix}: invalid outcome")
        if record.get("reason") is not None and not isinstance(record.get("reason"), str):
            errors.append(f"{prefix}: reason must be a string or null")
        if not isinstance(record.get("parents"), list):
            errors.append(f"{prefix}: parents must be an array")
        if record.get("previous_chronicle") is not None and not _nonempty_string(
            record.get("previous_chronicle")
        ):
            errors.append(f"{prefix}: previous_chronicle must be a string or null")
        start_record = record.get("start_record")
        if not isinstance(start_record, dict) or not _nonempty_string(start_record.get("record_id")) or not SHA256_PATTERN.fullmatch(str(start_record.get("sha256", ""))):
            errors.append(f"{prefix}: start_record must contain a record_id and SHA-256")
        errors.extend(_snapshot_errors(record.get("start_snapshot"), f"{prefix}.start_snapshot"))
        errors.extend(_snapshot_errors(record.get("end_snapshot"), f"{prefix}.end_snapshot"))
        for field in ("intent", "ending_plan", "journey", "closing_event", "human_story"):
            if not isinstance(record.get(field), dict):
                errors.append(f"{prefix}: {field} must be an object")
        if not isinstance(record.get("change_bindings"), list) or not all(
            isinstance(item, dict) for item in record.get("change_bindings", [])
        ):
            errors.append(f"{prefix}: change_bindings must contain objects")
        coverage = record.get("provenance_coverage")
        if not isinstance(coverage, dict) or coverage.get("status") not in {
            "complete",
            "partial",
            "unavailable",
        }:
            errors.append(f"{prefix}: invalid provenance_coverage")
        elif any(
            not _string_list(coverage.get(field))
            for field in (
                "material_files",
                "declared_files",
                "unbound_files",
                "unobserved_declared_files",
            )
        ):
            errors.append(f"{prefix}: provenance coverage paths must be string arrays")
        replay = record.get("replay")
        if not isinstance(replay, dict) or replay.get("fidelity") not in {
            "artifact-identical",
            "behaviorally-equivalent",
            "partial",
        }:
            errors.append(f"{prefix}: invalid replay contract")
        else:
            commands = replay.get("commands")
            if not isinstance(commands, list):
                errors.append(f"{prefix}: replay commands are invalid")
            elif not all(
                isinstance(item, dict)
                and set(item) == {"task", "command", "recorded_result"}
                and _nonempty_string(item.get("task"))
                and _nonempty_string(item.get("command"))
                and item.get("recorded_result") in {"passed", "failed", "not-run"}
                for item in commands
            ):
                errors.append(f"{prefix}: replay commands are invalid")
            if not _string_list(replay.get("limitations")):
                errors.append(f"{prefix}: replay limitations must be a string array")
            for field in ("start_commit", "end_commit"):
                value = replay.get(field)
                if value is not None and not GIT_OBJECT_PATTERN.fullmatch(str(value)):
                    errors.append(f"{prefix}: replay {field} must be a Git object ID or null")
            if replay.get("fidelity") == "behaviorally-equivalent":
                evidence_gaps = _replay_evidence_gaps(record.get("change_bindings", []))
                if (
                    not isinstance(coverage, dict)
                    or coverage.get("status") != "complete"
                    or not record.get("change_bindings")
                    or evidence_gaps
                ):
                    errors.append(
                        f"{prefix}: behaviorally-equivalent replay requires complete provenance, passed commands, and acceptance evidence"
                    )
            if replay.get("fidelity") == "artifact-identical" and (
                not isinstance(coverage, dict)
                or coverage.get("status") != "complete"
                or not replay.get("start_commit")
                or not replay.get("end_commit")
                or replay.get("start_commit") == replay.get("end_commit")
            ):
                errors.append(
                    f"{prefix}: artifact-identical replay requires a complete distinct Git commit range"
                )
        for field in ("report", "change_dossier"):
            if record.get(field) is not None and not isinstance(record.get(field), dict):
                errors.append(f"{prefix}: {field} must be an object or null")

    elif record_type == "code-binding":
        if record.get("schema") != "pyramid-code-binding-v1":
            errors.append(f"{prefix}: invalid code-binding schema")
        if not _nonempty_string(record.get("chronicle_id")):
            errors.append(f"{prefix}: chronicle_id must be a non-empty string")
        for field in ("commit", "start_commit"):
            if not GIT_OBJECT_PATTERN.fullmatch(str(record.get(field, ""))):
                errors.append(f"{prefix}: {field} must be a Git object ID")
        tree = record.get("tree")
        if tree is not None and not GIT_OBJECT_PATTERN.fullmatch(str(tree)):
            errors.append(f"{prefix}: tree must be a Git object ID or null")
        if record.get("clean") is not True:
            errors.append(f"{prefix}: clean must be true")
        if not _string_list(record.get("material_files")):
            errors.append(f"{prefix}: material_files must be a string array")
        if record.get("provenance_status") != "complete":
            errors.append(f"{prefix}: provenance_status must be complete")
        if record.get("replay_fidelity") != "artifact-identical":
            errors.append(f"{prefix}: replay_fidelity must be artifact-identical")
    return errors


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


def _transaction_validation_errors(transaction: Any) -> list[str]:
    if not isinstance(transaction, dict):
        return ["history transaction must be an object"]
    required = {
        "schema",
        "operation",
        "prepared_at",
        "record",
        "record_sha256",
        "entry",
        "previous_chain_sha256",
        "next_head",
    }
    errors = [
        f"history transaction is missing {field}"
        for field in sorted(required - set(transaction))
    ]
    errors.extend(
        f"history transaction has unexpected field {field}"
        for field in sorted(set(transaction) - required)
    )
    if transaction.get("schema") != "pyramid-history-transaction-v1":
        errors.append("history transaction schema must be pyramid-history-transaction-v1")
    if transaction.get("operation") != "append":
        errors.append("history transaction operation must be append")
    if not _nonempty_string(transaction.get("prepared_at")):
        errors.append("history transaction prepared_at must be a non-empty string")
    record = transaction.get("record")
    errors.extend(_record_validation_errors(record))
    expected_record_sha = hashlib.sha256(_serialized_json(record)).hexdigest()
    if transaction.get("record_sha256") != expected_record_sha:
        errors.append("history transaction record SHA-256 does not match its payload")
    if not SHA256_PATTERN.fullmatch(str(transaction.get("record_sha256", ""))):
        errors.append("history transaction record_sha256 must be a SHA-256")
    predecessor = transaction.get("previous_chain_sha256")
    if predecessor is not None and not SHA256_PATTERN.fullmatch(str(predecessor)):
        errors.append("history transaction previous_chain_sha256 must be a SHA-256 or null")
    entry = transaction.get("entry")
    if not isinstance(entry, dict):
        errors.append("history transaction entry must be an object")
    elif isinstance(record, dict):
        errors.extend(
            f"history transaction entry is missing {field}"
            for field in sorted(ENTRY_FIELDS - set(entry))
        )
        errors.extend(
            f"history transaction entry has unexpected field {field}"
            for field in sorted(set(entry) - ENTRY_FIELDS)
        )
        if entry.get("record_id") != record.get("record_id"):
            errors.append("history transaction entry record_id does not match its record")
        for field in ("record_type", "plan_id", "recorded_at"):
            if entry.get(field) != record.get(field):
                errors.append(
                    f"history transaction entry {field} does not match its record"
                )
        relative = entry.get("path")
        expected_path = f"records/{record.get('record_id')}.json"
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or relative != expected_path
        ):
            errors.append("history transaction entry path is invalid")
        if entry.get("sha256") != expected_record_sha:
            errors.append("history transaction entry SHA-256 does not match its record")
        if entry.get("previous_chain_sha256") != transaction.get(
            "previous_chain_sha256"
        ):
            errors.append("history transaction predecessor does not match its entry")
    next_head = transaction.get("next_head")
    if not isinstance(next_head, dict):
        errors.append("history transaction next_head must be an object")
    elif isinstance(entry, dict):
        errors.extend(
            f"history transaction next_head is missing {field}"
            for field in sorted(HEAD_FIELDS - set(next_head))
        )
        errors.extend(
            f"history transaction next_head has unexpected field {field}"
            for field in sorted(set(next_head) - HEAD_FIELDS)
        )
        if next_head.get("schema") != "pyramid-history-head-v1":
            errors.append("history transaction next_head schema is invalid")
        if isinstance(record, dict) and next_head.get("updated_at") != record.get(
            "recorded_at"
        ):
            errors.append("history transaction next_head updated_at does not match its record")
        entries = next_head.get("entries")
        if not isinstance(entries, list) or not entries or entries[-1] != entry:
            errors.append("history transaction next_head does not end with its entry")
        expected_chain = _canonical_sha256(
            {"previous": transaction.get("previous_chain_sha256"), "entry": entry}
        )
        if next_head.get("chain_sha256") != expected_chain:
            errors.append("history transaction next_head chain identity is invalid")
    return errors


def _clear_transaction(paths: dict[str, Path]) -> None:
    try:
        paths["transaction"].unlink()
    except FileNotFoundError:
        return
    _sync_directory(paths["root"])


def _append_record(meta: Path, record: dict[str, Any]) -> dict[str, Any]:
    paths = history_paths(meta)
    head = _head(paths)
    errors = history_validation_errors(meta)
    if errors:
        raise HistoryError("History validation failed:\n- " + "\n- ".join(errors))
    record_errors = _record_validation_errors(record)
    if record_errors:
        raise HistoryError("History record is invalid:\n- " + "\n- ".join(record_errors))
    filename = f"{record['record_id']}.json"
    destination = paths["records"] / filename
    if destination.exists():
        existing = _load_json(destination)
        if existing == record:
            return existing
        raise HistoryError(f"Immutable history record already exists: {record['record_id']}")
    link_errors = _record_link_errors([*_records(meta), record])
    if link_errors:
        raise HistoryError("History record links are invalid:\n- " + "\n- ".join(link_errors))
    record_sha256 = hashlib.sha256(_serialized_json(record)).hexdigest()
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
    next_head = copy.deepcopy(head)
    next_head["updated_at"] = record["recorded_at"]
    next_head.setdefault("entries", []).append(entry)
    next_head["chain_sha256"] = chain_sha256
    transaction = {
        "schema": "pyramid-history-transaction-v1",
        "operation": "append",
        "prepared_at": _now(),
        "record": copy.deepcopy(record),
        "record_sha256": record_sha256,
        "entry": copy.deepcopy(entry),
        "previous_chain_sha256": previous,
        "next_head": next_head,
    }
    transaction_errors = _transaction_validation_errors(transaction)
    if transaction_errors:
        raise HistoryError(
            "History append transaction is invalid:\n- "
            + "\n- ".join(transaction_errors)
        )
    _write_json(paths["transaction"], transaction)
    try:
        _write_json(destination, record)
        _write_json(paths["head"], next_head)
        rebuild_history_index(meta)
    except Exception as exc:
        raise HistoryError(
            "History append was interrupted; run history --doctor and history --repair"
        ) from exc
    _clear_transaction(paths)
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


def _record_link_errors(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    positions: dict[str, int] = {}
    records_by_id: dict[str, dict[str, Any]] = {}
    starts_by_plan: dict[str, list[str]] = {}
    for position, record in enumerate(records):
        record_id = record.get("record_id")
        if not isinstance(record_id, str):
            continue
        if record_id in positions:
            errors.append(f"history repeats record_id {record_id}")
            continue
        positions[record_id] = position
        records_by_id[record_id] = record
        if record.get("record_type") == "intent-start":
            starts_by_plan.setdefault(str(record.get("plan_id")), []).append(record_id)

    for plan_id, starts in starts_by_plan.items():
        if len(starts) != 1:
            errors.append(
                f"plan {plan_id} has {len(starts)} intent-start records; exactly one is required"
            )

    def earlier_chronicle(reference: Any, owner: str, relationship: str) -> dict[str, Any] | None:
        if not isinstance(reference, str) or not reference:
            errors.append(f"{owner}: {relationship} must reference an earlier chronicle")
            return None
        target = records_by_id.get(reference)
        if target is None or target.get("record_type") != "intent-chronicle":
            errors.append(f"{owner}: {relationship} references unknown chronicle {reference}")
            return None
        if positions[reference] >= positions.get(owner, len(records)):
            errors.append(f"{owner}: {relationship} must reference an earlier chronicle")
            return None
        return target

    for record in records:
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or record_id not in positions:
            continue
        record_type = record.get("record_type")
        plan_id = record.get("plan_id")
        if record_type == "intent-start":
            for parent in record.get("parents", []) if isinstance(record.get("parents"), list) else []:
                if isinstance(parent, dict):
                    earlier_chronicle(parent.get("chronicle_id"), record_id, "parent")
        elif record_type == "intent-chronicle":
            starts = starts_by_plan.get(str(plan_id), [])
            if len(starts) != 1:
                errors.append(f"{record_id}: plan must have exactly one intent-start record")
            start_reference = record.get("start_record", {})
            start_id = (
                start_reference.get("record_id")
                if isinstance(start_reference, dict)
                else None
            )
            start = records_by_id.get(str(start_id))
            if (
                start is None
                or start.get("record_type") != "intent-start"
                or start.get("plan_id") != plan_id
            ):
                errors.append(
                    f"{record_id}: start_record must reference the intent-start for plan {plan_id}"
                )
            elif positions[str(start_id)] >= positions[record_id]:
                errors.append(f"{record_id}: start_record must precede the chronicle")
            previous = record.get("previous_chronicle")
            if previous is not None:
                target = earlier_chronicle(previous, record_id, "previous_chronicle")
                if target is not None and target.get("plan_id") != plan_id:
                    errors.append(
                        f"{record_id}: previous_chronicle must belong to plan {plan_id}"
                    )
            for parent in record.get("parents", []) if isinstance(record.get("parents"), list) else []:
                if isinstance(parent, dict):
                    earlier_chronicle(parent.get("chronicle_id"), record_id, "parent")
        elif record_type == "code-binding":
            chronicle_id = record.get("chronicle_id")
            target = earlier_chronicle(chronicle_id, record_id, "chronicle_id")
            if target is not None:
                if target.get("plan_id") != plan_id:
                    errors.append(
                        f"{record_id}: bound chronicle must belong to plan {plan_id}"
                    )
                if record.get("start_commit") != target.get("replay", {}).get(
                    "start_commit"
                ):
                    errors.append(
                        f"{record_id}: start_commit does not match the bound chronicle"
                    )
    return errors


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


def _committed_history_validation_errors(
    meta: Path, *, ignored_unreferenced: set[str] | None = None
) -> list[str]:
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
    errors.extend(f"history head is missing {field}" for field in sorted(HEAD_FIELDS - set(head)))
    errors.extend(
        f"history head has unexpected field {field}" for field in sorted(set(head) - HEAD_FIELDS)
    )
    if head.get("schema") != "pyramid-history-head-v1":
        errors.append("history head schema must be pyramid-history-head-v1")
    if head.get("updated_at") is not None and not _nonempty_string(head.get("updated_at")):
        errors.append("history head updated_at must be a string or null")
    if not isinstance(head.get("entries"), list):
        errors.append("history head entries must be an array")
        return errors
    if head.get("chain_sha256") is not None and not SHA256_PATTERN.fullmatch(
        str(head.get("chain_sha256"))
    ):
        errors.append("history head chain_sha256 must be a SHA-256 or null")
    previous: str | None = None
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    record_hashes: dict[str, str] = {}
    for entry in head.get("entries", []):
        if not isinstance(entry, dict):
            errors.append("history head entry must be an object")
            continue
        errors.extend(
            f"history head entry is missing {field}"
            for field in sorted(ENTRY_FIELDS - set(entry))
        )
        errors.extend(
            f"history head entry has unexpected field {field}"
            for field in sorted(set(entry) - ENTRY_FIELDS)
        )
        record_id = entry.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            errors.append("history head entry is missing record_id")
            continue
        if record_id in seen:
            errors.append(f"history head repeats record {record_id}")
        seen.add(record_id)
        if entry.get("record_type") not in RECORD_FIELDS:
            errors.append(f"history head entry has invalid record_type: {record_id}")
        for field in ("plan_id", "recorded_at"):
            if not _nonempty_string(entry.get(field)):
                errors.append(f"history head entry {record_id} has invalid {field}")
        if not SHA256_PATTERN.fullmatch(str(entry.get("sha256", ""))):
            errors.append(f"history head entry {record_id} has invalid SHA-256")
        relative = entry.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            errors.append(f"history record {record_id} has an unsafe path")
            continue
        if relative != f"records/{record_id}.json":
            errors.append(f"history record {record_id} has a non-canonical path")
            continue
        record_path = paths["root"] / relative
        if not record_path.exists():
            errors.append(f"history record is missing: {record_id}")
            continue
        actual_sha = _file_sha256(record_path)
        if actual_sha != entry.get("sha256"):
            errors.append(f"history record hash mismatch: {record_id}")
        try:
            record = _load_json(record_path)
        except HistoryError as exc:
            errors.append(str(exc))
            continue
        records.append(record)
        record_hashes[record_id] = actual_sha
        errors.extend(_record_validation_errors(record))
        for field in ("record_id", "record_type", "plan_id", "recorded_at"):
            if entry.get(field) != record.get(field):
                errors.append(
                    f"history head entry {record_id} does not match record field {field}"
                )
        if entry.get("previous_chain_sha256") != previous:
            errors.append(f"history chain predecessor mismatch: {record_id}")
        previous = _canonical_sha256({"previous": previous, "entry": entry})
    if head.get("chain_sha256") != previous:
        errors.append("history head chain_sha256 does not match its entries")
    if head.get("entries"):
        last = head["entries"][-1]
        if isinstance(last, dict) and head.get("updated_at") != last.get("recorded_at"):
            errors.append("history head updated_at does not match its final entry")
    elif head.get("updated_at") is not None:
        errors.append("empty history head must have a null updated_at")
    errors.extend(_record_link_errors(records))
    for record in records:
        if record.get("record_type") != "intent-chronicle":
            continue
        start_reference = record.get("start_record")
        if not isinstance(start_reference, dict):
            continue
        start_id = start_reference.get("record_id")
        if isinstance(start_id, str) and start_id in record_hashes:
            if start_reference.get("sha256") != record_hashes[start_id]:
                errors.append(
                    f"{record.get('record_id')}: start_record SHA-256 does not match {start_id}"
                )
    referenced = {
        str((paths["root"] / entry["path"]).resolve())
        for entry in head.get("entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    ignored = ignored_unreferenced or set()
    for record_path in paths["records"].glob("*.json") if paths["records"].exists() else []:
        relative = str(record_path.relative_to(paths["root"]))
        if str(record_path.resolve()) not in referenced and relative not in ignored:
            errors.append(f"unreferenced immutable history record: {record_path.name}")
    return errors


def history_validation_errors(meta: Path) -> list[str]:
    paths = history_paths(meta)
    if paths["transaction"].exists():
        errors = [
            "history append transaction is pending; run history --doctor and history --repair"
        ]
        try:
            transaction = _load_json(paths["transaction"])
        except HistoryError as exc:
            return [*errors, str(exc)]
        return [*errors, *_transaction_validation_errors(transaction)]
    return _committed_history_validation_errors(meta)


def history_health(meta: Path) -> dict[str, Any]:
    paths = history_paths(meta)
    if not paths["root"].exists():
        return {
            "schema": "pyramid-history-health-v1",
            "status": "empty",
            "record_count": 0,
            "chronicle_count": 0,
            "binding_count": 0,
            "pending_transaction": None,
            "errors": [],
        }
    transaction: dict[str, Any] | None = None
    transaction_errors: list[str] = []
    if paths["transaction"].exists():
        try:
            transaction = _load_json(paths["transaction"])
            transaction_errors = _transaction_validation_errors(transaction)
        except HistoryError as exc:
            transaction_errors = [str(exc)]
    ignored = set()
    if transaction and isinstance(transaction.get("entry"), dict):
        pending_path = transaction["entry"].get("path")
        if isinstance(pending_path, str):
            ignored.add(pending_path)
    first_append = bool(
        transaction
        and not paths["head"].exists()
        and transaction.get("previous_chain_sha256") is None
        and isinstance(transaction.get("next_head", {}).get("entries"), list)
        and len(transaction["next_head"]["entries"]) == 1
    )
    committed_errors = (
        []
        if first_append
        else _committed_history_validation_errors(meta, ignored_unreferenced=ignored)
    )
    try:
        records = _records(meta) if paths["head"].exists() else []
    except HistoryError:
        records = []
    if transaction_errors or committed_errors:
        status = "invalid"
    elif transaction is not None:
        status = "repair-required"
    else:
        status = "valid"
    return {
        "schema": "pyramid-history-health-v1",
        "status": status,
        "record_count": len(records),
        "chronicle_count": sum(
            item.get("record_type") == "intent-chronicle" for item in records
        ),
        "binding_count": sum(
            item.get("record_type") == "code-binding" for item in records
        ),
        "pending_transaction": (
            {
                "operation": transaction.get("operation"),
                "prepared_at": transaction.get("prepared_at"),
                "record_id": transaction.get("record", {}).get("record_id"),
            }
            if transaction
            else None
        ),
        "errors": [*transaction_errors, *committed_errors],
    }


def repair_history_transaction(meta: Path) -> dict[str, Any]:
    paths = history_paths(meta)
    if not paths["transaction"].exists():
        health = history_health(meta)
        return {**health, "repair": "not-required"}
    transaction = _load_json(paths["transaction"])
    errors = _transaction_validation_errors(transaction)
    if errors:
        raise HistoryError("History transaction is invalid:\n- " + "\n- ".join(errors))
    entry = transaction["entry"]
    pending_path = str(entry["path"])
    first_append = bool(
        not paths["head"].exists()
        and transaction.get("previous_chain_sha256") is None
        and len(transaction["next_head"].get("entries", [])) == 1
    )
    committed_errors = (
        []
        if first_append
        else _committed_history_validation_errors(
            meta, ignored_unreferenced={pending_path}
        )
    )
    if committed_errors:
        raise HistoryError(
            "Committed history is invalid and cannot be repaired automatically:\n- "
            + "\n- ".join(committed_errors)
        )
    head = _head(paths)
    next_head = transaction["next_head"]
    current_entries = head.get("entries", [])
    next_entries = next_head.get("entries", [])
    if current_entries == next_entries:
        if head != next_head:
            raise HistoryError("Pending append head differs from its prepared next_head")
    elif current_entries == next_entries[:-1]:
        if head.get("chain_sha256") != transaction.get("previous_chain_sha256"):
            raise HistoryError("Pending append predecessor no longer matches history head")
    else:
        raise HistoryError("Pending append does not extend the current history head")
    current_records = _records(meta) if paths["head"].exists() else []
    if current_entries != next_entries:
        link_errors = _record_link_errors([*current_records, transaction["record"]])
        if link_errors:
            raise HistoryError(
                "Pending history record links are invalid:\n- "
                + "\n- ".join(link_errors)
            )
    record_path = paths["root"] / pending_path
    if record_path.exists():
        if _file_sha256(record_path) != transaction["record_sha256"]:
            raise HistoryError("Pending history record does not match its transaction")
    else:
        _write_json(record_path, transaction["record"])
    _write_json(paths["head"], next_head)
    rebuild_history_index(meta)
    final_errors = _committed_history_validation_errors(meta)
    if final_errors:
        raise HistoryError(
            "Repaired history did not validate:\n- " + "\n- ".join(final_errors)
        )
    _clear_transaction(paths)
    health = history_health(meta)
    return {
        **health,
        "repair": "completed",
        "repaired_record_id": transaction["record"]["record_id"],
    }


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


def _replay_evidence_gaps(bindings: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    for binding in bindings:
        task = str(binding.get("task", "unknown task"))
        checks = binding.get("checks")
        if not isinstance(checks, list) or not checks:
            gaps.append(f"{task}: no validation command was recorded")
        else:
            for position, check in enumerate(checks, start=1):
                if (
                    not isinstance(check, dict)
                    or not _nonempty_string(check.get("command"))
                    or check.get("result") != "passed"
                ):
                    gaps.append(
                        f"{task}: validation check {position} lacks a passed command result"
                    )
        evidence = binding.get("acceptance_evidence")
        if not isinstance(evidence, list) or not evidence:
            gaps.append(f"{task}: no acceptance evidence was recorded")
        else:
            for position, item in enumerate(evidence, start=1):
                if (
                    not isinstance(item, dict)
                    or not _nonempty_string(item.get("criterion"))
                    or not _nonempty_string(item.get("reference"))
                    or item.get("result") != "passed"
                ):
                    gaps.append(
                        f"{task}: acceptance evidence {position} is incomplete or not passed"
                    )
    return gaps


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
    replay_evidence_gaps = _replay_evidence_gaps(bindings)
    commands = []
    for binding in bindings:
        for check in binding["checks"]:
            if isinstance(check, dict) and check.get("command"):
                commands.append(
                    {
                        "task": binding["task"],
                        "command": check["command"],
                        "recorded_result": check.get("result"),
                    }
                )
    if clean_committed_range and coverage_status == "complete":
        fidelity = "artifact-identical"
    elif coverage_status == "complete" and bindings and not replay_evidence_gaps:
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
    if replay_evidence_gaps:
        limitations.append(
            "Replay evidence is incomplete: " + "; ".join(replay_evidence_gaps)
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
                "binding_status": item.get("binding_status"),
                "binding_next_action": item.get("binding_next_action"),
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
            "binding_status": item.get("binding_status"),
            "binding_next_action": item.get("binding_next_action"),
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
