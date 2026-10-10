"""Pure record, transaction and link contracts; preserve ordered errors."""
from __future__ import annotations
import copy,hashlib,json,re
from pathlib import Path
from typing import Any

class HistoryError(RuntimeError):
    pass

HistoryError.__module__ = "pyramid_history"

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

def _canonical_sha256(value: Any) -> str:
    material = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()

def _serialized_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")

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

def _git_object_or_none(value: Any) -> str | None:
    """A Git object ID, or None when the value is missing or not one.

    Older captures stored a symbolic ref such as "HEAD" when the repository had
    no commits yet. Recording that as a commit would assert a provenance the
    intent never had, so an unusable value becomes None: the schema permits it
    and replay fidelity degrades to partial on its own.
    """
    return str(value) if value is not None and GIT_OBJECT_PATTERN.fullmatch(str(value)) else None

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
