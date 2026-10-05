from __future__ import annotations

import copy
import fnmatch
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_FORMAT_VERSION = 3
RUNTIME_VERSION = "4.2.0"
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]*$")
ASSET_KINDS = {
    "repository",
    "service",
    "module",
    "api",
    "data-store",
    "job",
    "deployment",
    "interface",
    "runbook",
    "external-system",
    "repository-area",
    "unknown",
}
CRITICALITIES = {"unknown", "low", "medium", "high", "critical"}
CONFIDENCE = {"low", "medium", "high"}
BASELINE_STATUSES = {"incomplete", "current", "stale"}
RELATION_TYPES = {
    "depends-on",
    "calls",
    "reads",
    "writes",
    "publishes",
    "subscribes",
    "deployed-with",
    "guarded-by",
    "observed-by",
    "owned-by",
}
IMPACT_TYPES = {"direct", "transitive", "data", "operational", "security", "compliance"}
IMPACT_STATUSES = {"hypothesis", "confirmed", "dismissed"}
INSPECTION_STATUSES = {"planned", "performed", "blocked", "skipped", "stale"}
INSPECTION_RESULTS = {"pass", "fail", "inconclusive", "not-run"}
SUFFICIENCY = {"sufficient", "partial", "insufficient", "unknown"}
FINDING_STATUSES = {"open", "resolved", "accepted", "dismissed"}
ASSURANCE_STATUSES = {"incomplete", "ready", "stale", "passed"}
CONTROL_STATUSES = {"ready", "missing", "not-applicable"}
HISTORY_KINDS = {"incident", "defect", "migration", "decision", "workaround", "change"}
CHANGE_CLASSES = {"source", "generated", "runtime", "configuration", "evidence", "unknown"}
DEFAULT_INVALIDATION_CLASSES = CHANGE_CLASSES - {"evidence"}
REFRESH_POLICIES = {"per-change", "per-wave", "pre-audit", "release"}


def artifact_footprint(root: Path, plan: dict, state: dict, baseline: dict | None,
                       *, detail: bool = False, limit: int = 10000) -> dict:
    """Bounded metadata-only preview. References are current, not retention authority."""
    if type(limit) is not int or not 1 <= limit <= 100000:
        raise ValueError('footprint limit must be between 1 and 100000')
    root = root.resolve()
    evidence, generated, inputs, references = [], [], [], set()
    for node in plan['nodes']:
        agent = node.get('agent', {})
        evidence.extend(agent.get('evidence_outputs', []))
        generated.extend(g.get('pattern', '') for g in agent.get('generated_outputs', []))
        inputs.extend(p for e in node.get('required_evidence', [])
                      for p in e.get('verification', {}).get('inputs', []))

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == 'path' and isinstance(item, str):
                    references.add(item)
                elif key == 'evidence' and isinstance(item, list):
                    references.update(x for x in item if isinstance(x, str))
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    for item in state['nodes'].values():
        collect(item.get('last_result', {}))
        collect(item.get('last_audit', {}))
    matches = lambda rel, patterns: any(fnmatch.fnmatchcase(rel, p) for p in patterns)
    counts, files, excluded, errors = {}, [], set(), []
    entries = total_files = total_bytes = 0
    ignored = {'.git', '.venv', 'node_modules', '__pycache__'}
    stack = [os.scandir(root)]
    complete = True
    try:
        while stack:
            if entries >= limit:
                complete = False
                break
            try:
                entry = next(stack[-1])
            except StopIteration:
                stack.pop().close()
                continue
            except OSError as exc:
                errors.append(type(exc).__name__)
                complete = False
                stack.pop().close()
                continue
            entries += 1
            rel = Path(entry.path).relative_to(root).as_posix()
            try:
                if entry.is_symlink():
                    kind, size = 'symlink-not-followed', 0
                elif entry.is_dir(follow_symlinks=False):
                    if entry.name in ignored:
                        excluded.add(rel)
                    else:
                        stack.append(os.scandir(entry.path))
                    continue
                elif not entry.is_file(follow_symlinks=False):
                    kind, size = 'unknown-special', 0
                else:
                    size = entry.stat(follow_symlinks=False).st_size
                    is_input, is_evidence = matches(rel, inputs), matches(rel, evidence)
                    if is_input and is_evidence:
                        kind = 'input-evidence-conflict'
                    elif is_input:
                        kind = 'proof-input'
                    elif rel.startswith('.pyramid/reports/'):
                        kind = 'retained-evidence'
                    elif rel.startswith('.pyramid/') or rel.startswith('docs/tasks/'):
                        kind = 'canonical-or-projection'
                    elif is_evidence:
                        kind = 'declared-evidence'
                    elif matches(rel, generated):
                        kind = 'declared-generated'
                    else:
                        kind = 'unknown'
                total_files += 1
                total_bytes += size
                record = counts.setdefault(kind, {'files': 0, 'bytes': 0, 'currently_referenced': 0})
                record['files'] += 1
                record['bytes'] += size
                record['currently_referenced'] += int(rel in references)
                if detail and len(files) < 100:
                    files.append({'path': rel, 'class': kind, 'bytes': size,
                                  'currently_referenced': rel in references})
            except OSError as exc:
                errors.append(type(exc).__name__)
                complete = False
    finally:
        for iterator in stack:
            iterator.close()
    result = {'schema': 'pyramid-artifact-footprint-v1', 'deletion_authorized': False,
              'scan': {'entries': entries, 'limit': limit, 'complete': complete,
                       'excluded_directories': sorted(excluded)[:100], 'errors': errors[:20]},
              'totals': {'files': total_files, 'bytes': total_bytes},
              'classes': dict(sorted(counts.items())),
              'current_reference_count': len(references),
              'limitations': ['Logical file bytes, not allocated disk or Git size.',
                              'Current result/audit references only; archive, handoff and historical reference ownership is unknown.',
                              'Declared classes are not executed proof or deletion eligibility. Symlinks are not followed.',
                              'Scan excludes Git metadata, .venv, node_modules and Python caches; incomplete scans are partial totals.']}
    if detail:
        result.update(files=sorted(files, key=lambda f: f['path']), detail_limit=100,
                      detail_truncated=total_files > len(files))
    return result


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _strings(value: Any, *, nonempty: bool = False) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and (not nonempty or bool(item.strip())) for item in value
    )


def _stable_id(value: Any) -> bool:
    return isinstance(value, str) and bool(ID_PATTERN.match(value))


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def detect_repository_mode(root: Path) -> str:
    if not root.exists():
        return "greenfield"
    ignored = {".git", ".pyramid", ".DS_Store"}
    for child in root.iterdir():
        if child.name in ignored:
            continue
        if child.name == "docs" and (child / "tasks").exists() and len(list(child.iterdir())) == 1:
            continue
        return "brownfield"
    return "greenfield"


def default_project_manifest(
    *,
    plan_id: str,
    mode: str,
    actor: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = created_at or utc_now()
    return {
        "schema": "pyramid-project-v1",
        "format_version": PROJECT_FORMAT_VERSION,
        "runtime_version": RUNTIME_VERSION,
        "plan_id": plan_id,
        "mode": mode,
        "created_at": timestamp,
        "created_by": actor,
        "last_upgraded_at": None,
        "last_upgraded_by": None,
        "upgraded_from": None,
        "migrations": [],
    }


def default_baseline(*, actor: str, root_locator: str = ".") -> dict[str, Any]:
    timestamp = utc_now()
    return {
        "schema": "pyramid-baseline-v1",
        "baseline_id": "BASELINE-001",
        "revision": 1,
        "status": "incomplete",
        "captured_at": timestamp,
        "captured_by": actor,
        "capture_method": "initial-placeholder",
        "assets": [
            {
                "id": "ASSET-ROOT",
                "kind": "repository",
                "name": "Repository root",
                "locators": [root_locator],
                "owner": "unknown",
                "criticality": "unknown",
                "confidence": "low",
                "evidence": [],
            }
        ],
        "relations": [],
        "history": [],
        "unknowns": ["The existing system has not yet received a sufficient baseline assessment."],
    }


def default_assurance(
    *,
    plan_id: str,
    baseline: dict[str, Any],
    actor: str,
    policy: str = "brownfield",
) -> dict[str, Any]:
    return {
        "schema": "pyramid-assurance-v1",
        "plan_id": plan_id,
        "baseline_id": baseline["baseline_id"],
        "baseline_revision": baseline["revision"],
        "policy": policy,
        "status": "incomplete",
        "updated_at": utc_now(),
        "updated_by": actor,
        "enforce_from_graph_version": 1,
        "impacts": [],
        "inspections": [],
        "findings": [],
        "scope_drift": [],
        "controls": {
            "rollback": {"status": "missing", "evidence": [], "rationale": ""},
            "monitoring": {"status": "missing", "evidence": [], "rationale": ""},
        },
        "legacy_bridge": {
            "required": False,
            "status": "not-required",
            "gap_asset_ids": [],
            "evidence": [],
            "upgraded_from": None,
        },
        "stale_reasons": [],
    }


def validate_project_manifest(manifest: dict[str, Any], plan_id: str | None = None) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema") != "pyramid-project-v1":
        errors.append("project.schema must be pyramid-project-v1")
    if manifest.get("format_version") != PROJECT_FORMAT_VERSION:
        errors.append(f"project.format_version must be {PROJECT_FORMAT_VERSION}")
    if plan_id is not None and manifest.get("plan_id") != plan_id:
        errors.append(f"project.plan_id must be {plan_id}")
    if manifest.get("mode") not in {"greenfield", "brownfield"}:
        errors.append("project.mode must be greenfield or brownfield")
    if not isinstance(manifest.get("runtime_version"), str) or not manifest["runtime_version"]:
        errors.append("project.runtime_version must be non-empty")
    for field in ("created_at", "created_by"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            errors.append(f"project.{field} must be non-empty")
    for field in ("last_upgraded_at", "last_upgraded_by", "upgraded_from"):
        if manifest.get(field) is not None and not isinstance(manifest.get(field), str):
            errors.append(f"project.{field} must be a string or null")
    migrations = manifest.get("migrations")
    if not isinstance(migrations, list):
        errors.append("project.migrations must be an array")
        migrations = []
    for index, migration in enumerate(migrations):
        path = f"project.migrations[{index}]"
        if not isinstance(migration, dict):
            errors.append(f"{path} must be an object")
            continue
        for field in ("id", "from", "at", "actor", "preview_sha256", "archive_id"):
            if not isinstance(migration.get(field), str) or not migration[field].strip():
                errors.append(f"{path}.{field} must be non-empty")
        if migration.get("to") != PROJECT_FORMAT_VERSION:
            errors.append(f"{path}.to must be {PROJECT_FORMAT_VERSION}")
        if isinstance(migration.get("preview_sha256"), str) and not re.fullmatch(
            r"[a-f0-9]{64}", migration["preview_sha256"]
        ):
            errors.append(f"{path}.preview_sha256 must be a lowercase SHA-256")
    return errors


def validate_baseline(baseline: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if baseline.get("schema") != "pyramid-baseline-v1":
        errors.append("baseline.schema must be pyramid-baseline-v1")
    if not _stable_id(baseline.get("baseline_id")):
        errors.append("baseline.baseline_id must be a stable uppercase ID")
    if not isinstance(baseline.get("revision"), int) or baseline["revision"] < 1:
        errors.append("baseline.revision must be a positive integer")
    if baseline.get("status") not in BASELINE_STATUSES:
        errors.append("baseline.status must be incomplete, current, or stale")
    for field in ("captured_at", "captured_by", "capture_method"):
        if not isinstance(baseline.get(field), str) or not baseline[field].strip():
            errors.append(f"baseline.{field} must be non-empty")
    assets = baseline.get("assets")
    asset_ids: set[str] = set()
    if not isinstance(assets, list) or not assets:
        errors.append("baseline.assets must contain at least one asset")
        assets = []
    for index, asset in enumerate(assets):
        path = f"baseline.assets[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{path} must be an object")
            continue
        aid = asset.get("id")
        if not _stable_id(aid):
            errors.append(f"{path}.id must be a stable uppercase ID")
        elif aid in asset_ids:
            errors.append(f"duplicate asset ID: {aid}")
        else:
            asset_ids.add(aid)
        if asset.get("kind") not in ASSET_KINDS:
            errors.append(f"{aid or path}: invalid asset kind")
        if not isinstance(asset.get("name"), str) or not asset["name"].strip():
            errors.append(f"{aid or path}: name must be non-empty")
        if not _strings(asset.get("locators"), nonempty=True):
            errors.append(f"{aid or path}: locators must be non-empty strings")
        if "exclude_locators" in asset and not _strings(
            asset.get("exclude_locators"), nonempty=True
        ):
            errors.append(f"{aid or path}: exclude_locators must be a string array when provided")
        if not isinstance(asset.get("owner"), str):
            errors.append(f"{aid or path}: owner must be a string")
        if asset.get("criticality") not in CRITICALITIES:
            errors.append(f"{aid or path}: invalid criticality")
        if asset.get("confidence") not in CONFIDENCE:
            errors.append(f"{aid or path}: invalid confidence")
        if not _strings(asset.get("evidence")):
            errors.append(f"{aid or path}: evidence must be a string array")

    relations = baseline.get("relations")
    if not isinstance(relations, list):
        errors.append("baseline.relations must be an array")
        relations = []
    seen_relations: set[tuple[str, str, str]] = set()
    for index, relation in enumerate(relations):
        path = f"baseline.relations[{index}]"
        if not isinstance(relation, dict):
            errors.append(f"{path} must be an object")
            continue
        source, target, kind = relation.get("from"), relation.get("to"), relation.get("type")
        if source not in asset_ids or target not in asset_ids:
            errors.append(f"{path} references an unknown asset")
        if kind not in RELATION_TYPES:
            errors.append(f"{path} has an invalid relation type")
        key = (str(source), str(target), str(kind))
        if key in seen_relations:
            errors.append(f"duplicate baseline relation: {source} --{kind}--> {target}")
        seen_relations.add(key)
        if not _strings(relation.get("evidence")):
            errors.append(f"{path}.evidence must be a string array")

    history = baseline.get("history")
    history_ids: set[str] = set()
    if not isinstance(history, list):
        errors.append("baseline.history must be an array")
        history = []
    for index, item in enumerate(history):
        path = f"baseline.history[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        hid = item.get("id")
        if not _stable_id(hid) or hid in history_ids:
            errors.append(f"{path}.id must be a unique stable ID")
        elif isinstance(hid, str):
            history_ids.add(hid)
        if not isinstance(item.get("summary"), str) or not item["summary"].strip():
            errors.append(f"{hid or path}: summary must be non-empty")
        if item.get("kind") not in HISTORY_KINDS:
            errors.append(f"{hid or path}: invalid history kind")
        if not _strings(item.get("asset_ids")) or any(
            aid not in asset_ids for aid in item.get("asset_ids", [])
        ):
            errors.append(f"{hid or path}: asset_ids must reference known assets")
        if not _strings(item.get("evidence")):
            errors.append(f"{hid or path}: evidence must be a string array")
        if not isinstance(item.get("date"), str) or not item["date"].strip():
            errors.append(f"{hid or path}: date must be non-empty")
        if not _strings(item.get("controls")):
            errors.append(f"{hid or path}: controls must be a string array")
    if not _strings(baseline.get("unknowns")):
        errors.append("baseline.unknowns must be a string array")
    return errors


def validate_assurance(
    assurance: dict[str, Any],
    *,
    plan: dict[str, Any],
    baseline: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if assurance.get("schema") != "pyramid-assurance-v1":
        errors.append("assurance.schema must be pyramid-assurance-v1")
    if assurance.get("plan_id") != plan.get("plan_id"):
        errors.append(f"assurance.plan_id must be {plan.get('plan_id')}")
    if assurance.get("baseline_id") != baseline.get("baseline_id"):
        errors.append("assurance.baseline_id must match the current baseline")
    if assurance.get("baseline_revision") != baseline.get("revision"):
        errors.append("assurance.baseline_revision must match the current baseline revision")
    if assurance.get("policy") not in {"brownfield", "legacy-bridge"}:
        errors.append("assurance.policy must be brownfield or legacy-bridge")
    if assurance.get("status") not in ASSURANCE_STATUSES:
        errors.append("assurance.status is invalid")
    if not isinstance(assurance.get("updated_at"), str) or not assurance["updated_at"].strip():
        errors.append("assurance.updated_at must be non-empty")
    if not isinstance(assurance.get("updated_by"), str) or not assurance["updated_by"].strip():
        errors.append("assurance.updated_by must be non-empty")
    if (
        not isinstance(assurance.get("enforce_from_graph_version"), int)
        or assurance["enforce_from_graph_version"] < 1
    ):
        errors.append("assurance.enforce_from_graph_version must be a positive integer")
    asset_ids = {item["id"] for item in baseline.get("assets", []) if isinstance(item, dict) and "id" in item}
    task_ids = {item["id"] for item in plan.get("nodes", []) if isinstance(item, dict) and "id" in item}
    for node in plan.get("nodes", []):
        if not isinstance(node, dict):
            continue
        for index, output in enumerate(
            node.get("agent", {}).get("generated_outputs", [])
        ):
            if not isinstance(output, dict):
                continue
            unknown_assets = sorted(set(output.get("asset_ids", [])) - asset_ids)
            if unknown_assets:
                errors.append(
                    f"{node.get('id')}: agent.generated_outputs[{index}] references "
                    "unknown baseline assets: " + ", ".join(unknown_assets)
                )

    impact_ids: set[str] = set()
    impacts = assurance.get("impacts")
    if not isinstance(impacts, list):
        errors.append("assurance.impacts must be an array")
        impacts = []
    for index, impact in enumerate(impacts):
        path = f"assurance.impacts[{index}]"
        if not isinstance(impact, dict):
            errors.append(f"{path} must be an object")
            continue
        iid = impact.get("id")
        if not _stable_id(iid) or iid in impact_ids:
            errors.append(f"{path}.id must be a unique stable ID")
        elif isinstance(iid, str):
            impact_ids.add(iid)
        if impact.get("asset_id") not in asset_ids:
            errors.append(f"{iid or path}: asset_id is unknown")
        if not _strings(impact.get("task_ids"), nonempty=True) or any(
            task not in task_ids for task in impact.get("task_ids", [])
        ):
            errors.append(f"{iid or path}: task_ids must reference plan nodes")
        if impact.get("type") not in IMPACT_TYPES:
            errors.append(f"{iid or path}: invalid impact type")
        if impact.get("status") not in IMPACT_STATUSES:
            errors.append(f"{iid or path}: invalid impact status")
        if impact.get("confidence") not in CONFIDENCE:
            errors.append(f"{iid or path}: invalid confidence")
        if not _strings(impact.get("evidence")):
            errors.append(f"{iid or path}: evidence must be a string array")
        if not _strings(impact.get("path")):
            errors.append(f"{iid or path}: path must be a string array")

    inspection_ids: set[str] = set()
    inspections = assurance.get("inspections")
    if not isinstance(inspections, list):
        errors.append("assurance.inspections must be an array")
        inspections = []
    for index, inspection in enumerate(inspections):
        path = f"assurance.inspections[{index}]"
        if not isinstance(inspection, dict):
            errors.append(f"{path} must be an object")
            continue
        iid = inspection.get("id")
        if not _stable_id(iid) or iid in inspection_ids:
            errors.append(f"{path}.id must be a unique stable ID")
        elif isinstance(iid, str):
            inspection_ids.add(iid)
        if not _strings(inspection.get("asset_ids"), nonempty=True) or any(
            aid not in asset_ids for aid in inspection.get("asset_ids", [])
        ):
            errors.append(f"{iid or path}: asset_ids must reference known assets")
        if not _strings(inspection.get("task_ids")) or any(
            task not in task_ids for task in inspection.get("task_ids", [])
        ):
            errors.append(f"{iid or path}: task_ids must reference plan nodes")
        if not isinstance(inspection.get("method"), str) or not inspection["method"].strip():
            errors.append(f"{iid or path}: method must be non-empty")
        if not isinstance(inspection.get("required"), bool):
            errors.append(f"{iid or path}: required must be boolean")
        if inspection.get("status") not in INSPECTION_STATUSES:
            errors.append(f"{iid or path}: invalid status")
        if inspection.get("result") not in INSPECTION_RESULTS:
            errors.append(f"{iid or path}: invalid result")
        if inspection.get("sufficiency") not in SUFFICIENCY:
            errors.append(f"{iid or path}: invalid sufficiency")
        if not _strings(inspection.get("evidence")):
            errors.append(f"{iid or path}: evidence must be a string array")
        if not _strings(inspection.get("limitations")):
            errors.append(f"{iid or path}: limitations must be a string array")
        invalidated_by = inspection.get("invalidated_by")
        if invalidated_by is not None and (
            not _strings(invalidated_by, nonempty=True)
            or any(item not in CHANGE_CLASSES for item in invalidated_by)
        ):
            errors.append(
                f"{iid or path}: invalidated_by must contain supported change classes"
            )
        refresh_policy = inspection.get("refresh_policy")
        if refresh_policy is not None and refresh_policy not in REFRESH_POLICIES:
            errors.append(f"{iid or path}: refresh_policy is invalid")
        validated_through = inspection.get("validated_through")
        if validated_through is not None and (
            not isinstance(validated_through, dict)
            or any(
                task not in task_ids
                or not isinstance(event_id, str)
                or not event_id.startswith("EVENT-")
                for task, event_id in validated_through.items()
            )
        ):
            errors.append(
                f"{iid or path}: validated_through must map plan task IDs to event IDs"
            )
        for field in ("performed_at", "performed_by"):
            if inspection.get(field) is not None and not isinstance(inspection.get(field), str):
                errors.append(f"{iid or path}: {field} must be a string or null")
        if (
            inspection.get("status") == "performed"
            and inspection.get("result") == "pass"
            and inspection.get("sufficiency") == "sufficient"
            and not inspection.get("evidence")
        ):
            errors.append(f"{iid or path}: a sufficient passing inspection needs evidence")
        if inspection.get("status") == "performed" and not all(
            isinstance(inspection.get(field), str) and inspection[field].strip()
            for field in ("performed_at", "performed_by")
        ):
            errors.append(f"{iid or path}: a performed inspection needs actor and timestamp")

    finding_ids: set[str] = set()
    findings = assurance.get("findings")
    if not isinstance(findings, list):
        errors.append("assurance.findings must be an array")
        findings = []
    for index, finding in enumerate(findings):
        path = f"assurance.findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{path} must be an object")
            continue
        fid = finding.get("id")
        if not _stable_id(fid) or fid in finding_ids:
            errors.append(f"{path}.id must be a unique stable ID")
        elif isinstance(fid, str):
            finding_ids.add(fid)
        if not _strings(finding.get("asset_ids"), nonempty=True) or any(
            aid not in asset_ids for aid in finding.get("asset_ids", [])
        ):
            errors.append(f"{fid or path}: asset_ids must reference known assets")
        inspection_id = finding.get("inspection_id")
        if inspection_id is not None and inspection_id not in inspection_ids:
            errors.append(f"{fid or path}: inspection_id is unknown")
        if finding.get("severity") not in CRITICALITIES - {"unknown"}:
            errors.append(f"{fid or path}: invalid severity")
        if finding.get("status") not in FINDING_STATUSES:
            errors.append(f"{fid or path}: invalid status")
        if not isinstance(finding.get("title"), str) or not finding["title"].strip():
            errors.append(f"{fid or path}: title must be non-empty")
        if not _strings(finding.get("evidence")):
            errors.append(f"{fid or path}: evidence must be a string array")
        if finding.get("status") == "accepted" and not all(
            isinstance(finding.get(field), str) and finding[field].strip()
            for field in ("accepted_by", "acceptance_reason")
        ):
            errors.append(f"{fid or path}: accepted findings need accepted_by and acceptance_reason")
        for field in ("accepted_by", "acceptance_reason"):
            if finding.get(field) is not None and not isinstance(finding.get(field), str):
                errors.append(f"{fid or path}: {field} must be a string or null")

    drift_ids: set[str] = set()
    drift = assurance.get("scope_drift")
    if not isinstance(drift, list):
        errors.append("assurance.scope_drift must be an array")
        drift = []
    for index, item in enumerate(drift):
        path = f"assurance.scope_drift[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        did = item.get("id")
        if not _stable_id(did) or did in drift_ids:
            errors.append(f"{path}.id must be a unique stable ID")
        elif isinstance(did, str):
            drift_ids.add(did)
        if item.get("task") not in task_ids:
            errors.append(f"{did or path}: task is unknown")
        if not isinstance(item.get("changed_file"), str) or not item["changed_file"].strip():
            errors.append(f"{did or path}: changed_file must be non-empty")
        if item.get("status") not in {"open", "resolved"}:
            errors.append(f"{did or path}: status must be open or resolved")
        if not _strings(item.get("matched_asset_ids")) or any(
            aid not in asset_ids for aid in item.get("matched_asset_ids", [])
        ):
            errors.append(f"{did or path}: matched_asset_ids must reference known assets")
        if not isinstance(item.get("detected_at"), str) or not item["detected_at"].strip():
            errors.append(f"{did or path}: detected_at must be non-empty")
        resolved_impact = item.get("resolved_impact_id")
        if resolved_impact is not None and resolved_impact not in impact_ids:
            errors.append(f"{did or path}: resolved_impact_id is unknown")
        if item.get("status") == "resolved":
            resolved_record = next(
                (
                    impact
                    for impact in impacts
                    if impact.get("id") == resolved_impact
                ),
                None,
            )
            if resolved_record is None:
                errors.append(f"{did or path}: resolved drift needs a mapped impact record")
            elif (
                item.get("task") not in resolved_record.get("task_ids", [])
                or resolved_record.get("status") != "confirmed"
                or not resolved_record.get("evidence")
            ):
                errors.append(
                    f"{did or path}: resolved impact must confirm this task with evidence"
                )

    controls = assurance.get("controls")
    if not isinstance(controls, dict):
        errors.append("assurance.controls must be an object")
    else:
        for name in ("rollback", "monitoring"):
            control = controls.get(name)
            if not isinstance(control, dict):
                errors.append(f"assurance.controls.{name} must be an object")
                continue
            if control.get("status") not in CONTROL_STATUSES:
                errors.append(f"assurance.controls.{name}.status is invalid")
            if not _strings(control.get("evidence")):
                errors.append(f"assurance.controls.{name}.evidence must be a string array")
            if control.get("status") == "ready" and not control.get("evidence"):
                errors.append(f"assurance.controls.{name} needs evidence when ready")
            if control.get("status") == "not-applicable" and not str(control.get("rationale", "")).strip():
                errors.append(f"assurance.controls.{name} needs rationale when not applicable")
            if not isinstance(control.get("rationale"), str):
                errors.append(f"assurance.controls.{name}.rationale must be a string")

    bridge = assurance.get("legacy_bridge")
    if not isinstance(bridge, dict):
        errors.append("assurance.legacy_bridge must be an object")
    else:
        if not isinstance(bridge.get("required"), bool):
            errors.append("assurance.legacy_bridge.required must be boolean")
        if bridge.get("status") not in {"not-required", "pending", "sufficient", "documented"}:
            errors.append("assurance.legacy_bridge.status is invalid")
        if not _strings(bridge.get("gap_asset_ids")) or any(
            aid not in asset_ids for aid in bridge.get("gap_asset_ids", [])
        ):
            errors.append("assurance.legacy_bridge.gap_asset_ids must reference known assets")
        if not _strings(bridge.get("evidence")):
            errors.append("assurance.legacy_bridge.evidence must be a string array")
        if bridge.get("upgraded_from") is not None and not isinstance(
            bridge.get("upgraded_from"), str
        ):
            errors.append("assurance.legacy_bridge.upgraded_from must be a string or null")
    if not _strings(assurance.get("stale_reasons")):
        errors.append("assurance.stale_reasons must be a string array")
    return errors


def _relevant_records(
    assurance: dict[str, Any], task_ids: set[str] | None
) -> tuple[list[dict[str, Any]], set[str]]:
    impacts = [
        impact
        for impact in assurance.get("impacts", [])
        if impact.get("status") != "dismissed"
        and (task_ids is None or task_ids.intersection(impact.get("task_ids", [])))
    ]
    asset_ids = {impact["asset_id"] for impact in impacts if impact.get("asset_id")}
    return impacts, asset_ids


def assurance_blockers(
    baseline: dict[str, Any],
    assurance: dict[str, Any],
    *,
    task_ids: set[str] | None = None,
    full: bool = False,
    implementation_frontier: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    blockers: list[str] = []
    if baseline.get("status") != "current":
        blockers.append(f"Baseline is {baseline.get('status', 'missing')}, not current")
    if assurance.get("status") == "stale":
        blockers.append("Assurance is stale: " + "; ".join(assurance.get("stale_reasons", [])))
    impacts, impacted_assets = _relevant_records(assurance, None if full else task_ids)
    if not impacts:
        blockers.append("No impact records cover the audited change scope")
    for impact in impacts:
        if impact.get("status") != "confirmed":
            blockers.append(f"Impact {impact.get('id')} remains {impact.get('status')}")
        if not impact.get("evidence"):
            blockers.append(f"Impact {impact.get('id')} has no evidence")

    inspections = [
        item
        for item in assurance.get("inspections", [])
        if impacted_assets.intersection(item.get("asset_ids", []))
        and (task_ids is None or not item.get("task_ids") or task_ids.intersection(item.get("task_ids", [])))
    ]
    for asset_id in sorted(impacted_assets):
        sufficient = [
            item
            for item in inspections
            if asset_id in item.get("asset_ids", [])
            and item.get("status") == "performed"
            and item.get("result") == "pass"
            and item.get("sufficiency") == "sufficient"
            and item.get("evidence")
        ]
        if not sufficient:
            blockers.append(f"Impacted asset {asset_id} lacks a sufficient passing inspection")
    for inspection in inspections:
        if not inspection.get("required"):
            continue
        if inspection.get("status") != "performed":
            blockers.append(f"Required inspection {inspection.get('id')} is {inspection.get('status')}")
        elif inspection.get("result") != "pass":
            blockers.append(f"Required inspection {inspection.get('id')} did not pass")
        elif inspection.get("sufficiency") != "sufficient":
            blockers.append(f"Required inspection {inspection.get('id')} is not sufficient")
        elif not inspection.get("evidence"):
            blockers.append(f"Required inspection {inspection.get('id')} has no evidence")

    blockers.extend(
        inspection_freshness_blockers(
            assurance,
            impacted_assets=impacted_assets,
            task_ids=task_ids,
            implementation_frontier=implementation_frontier,
        )
    )

    for finding in assurance.get("findings", []):
        if not impacted_assets.intersection(finding.get("asset_ids", [])):
            continue
        if finding.get("severity") in {"high", "critical"} and finding.get("status") == "open":
            blockers.append(f"Material finding {finding.get('id')} remains open")
        if finding.get("status") == "accepted" and not all(
            str(finding.get(field, "")).strip() for field in ("accepted_by", "acceptance_reason")
        ):
            blockers.append(f"Accepted finding {finding.get('id')} lacks accountable acceptance")

    open_drift = [
        item
        for item in assurance.get("scope_drift", [])
        if item.get("status") == "open" and (task_ids is None or item.get("task") in task_ids)
    ]
    blockers.extend(f"Scope drift {item.get('id')} is unresolved" for item in open_drift)

    if full:
        for name in ("rollback", "monitoring"):
            control = assurance.get("controls", {}).get(name, {})
            if control.get("status") == "missing":
                blockers.append(f"{name.capitalize()} control is missing")
            elif control.get("status") == "ready" and not control.get("evidence"):
                blockers.append(f"{name.capitalize()} control has no evidence")
            elif control.get("status") == "not-applicable" and not str(control.get("rationale", "")).strip():
                blockers.append(f"{name.capitalize()} non-applicability has no rationale")
        bridge = assurance.get("legacy_bridge", {})
        if bridge.get("required") and bridge.get("status") != "sufficient":
            blockers.append(
                "Legacy assurance bridge is incomplete"
                + (": " + ", ".join(bridge.get("gap_asset_ids", [])) if bridge.get("gap_asset_ids") else "")
            )
        if bridge.get("required") and bridge.get("status") == "sufficient":
            for asset_id in bridge.get("gap_asset_ids", []):
                covered = any(
                    asset_id in item.get("asset_ids", [])
                    and item.get("status") == "performed"
                    and item.get("result") == "pass"
                    and item.get("sufficiency") == "sufficient"
                    and item.get("evidence")
                    for item in assurance.get("inspections", [])
                )
                if not covered:
                    blockers.append(f"Legacy bridge asset {asset_id} lacks sufficient inspection evidence")
    return sorted(set(blockers))


def asset_ids_for_file(baseline: dict[str, Any], changed_file: str) -> set[str]:
    normalized = changed_file.strip().lstrip("./")
    matched: set[str] = set()
    for asset in baseline.get("assets", []):
        excluded = False
        for raw in asset.get("exclude_locators", []):
            locator = raw.strip().lstrip("./")
            prefix = locator.removesuffix("/**").removesuffix("/*").rstrip("/")
            if (
                fnmatch.fnmatch(normalized, locator)
                or normalized == prefix
                or normalized.startswith(prefix + "/")
            ):
                excluded = True
                break
        if excluded:
            continue
        for raw in asset.get("locators", []):
            locator = raw.strip().lstrip("./")
            if raw.strip() == "." or not locator:
                matched.add(asset["id"])
                break
            prefix = locator.removesuffix("/**").removesuffix("/*").rstrip("/")
            if fnmatch.fnmatch(normalized, locator) or normalized == prefix or normalized.startswith(prefix + "/"):
                matched.add(asset["id"])
                break
    return matched


def inspection_freshness_blockers(
    assurance: dict[str, Any],
    *,
    impacted_assets: set[str],
    task_ids: set[str] | None,
    implementation_frontier: dict[str, dict[str, Any]] | None,
) -> list[str]:
    if not implementation_frontier:
        return []
    blockers: list[str] = []
    inspections = [
        item
        for item in assurance.get("inspections", [])
        if impacted_assets.intersection(item.get("asset_ids", []))
        and (
            task_ids is None
            or not item.get("task_ids")
            or task_ids.intersection(item.get("task_ids", []))
        )
    ]
    for inspection in inspections:
        invalidated_by = set(
            inspection.get("invalidated_by", DEFAULT_INVALIDATION_CLASSES)
        )

        def requires_refresh(task: str) -> bool:
            implementation = implementation_frontier.get(task)
            if implementation is None:
                return False
            return not (
                implementation.get("change_effect") == "evidence-only"
                and "evidence" not in invalidated_by
            )

        inspected_tasks = set(inspection.get("task_ids", []))
        if task_ids is not None:
            inspected_tasks.intersection_update(task_ids)
        validated_through = inspection.get("validated_through")
        if isinstance(validated_through, dict):
            stale_for = sorted(
                task
                for task in inspected_tasks
                if requires_refresh(task)
                and validated_through.get(task)
                != implementation_frontier[task].get("event_id")
            )
        else:
            performed_at = _parse_time(inspection.get("performed_at"))
            stale_for = []
            for task in sorted(inspected_tasks):
                if not requires_refresh(task):
                    continue
                implementation_at = _parse_time(
                    implementation_frontier[task].get("at")
                )
                if (
                    performed_at is None
                    or implementation_at is None
                    or performed_at < implementation_at
                ):
                    stale_for.append(task)
        if stale_for:
            blockers.append(
                f"Inspection {inspection.get('id')} predates implementation for: "
                + ", ".join(stale_for)
            )
    return blockers


def assurance_warnings(
    baseline: dict[str, Any], assurance: dict[str, Any]
) -> list[str]:
    warnings: list[str] = []
    for inspection in assurance.get("inspections", []):
        task_count = len(inspection.get("task_ids", []))
        asset_count = len(inspection.get("asset_ids", []))
        if task_count > 8 and inspection.get("refresh_policy") not in {
            "pre-audit",
            "release",
        }:
            warnings.append(
                f"Inspection {inspection.get('id')} covers {task_count} tasks; split it or declare a boundary refresh policy"
            )
        if asset_count > 4:
            warnings.append(
                f"Inspection {inspection.get('id')} covers {asset_count} assets; review its invalidation blast radius"
            )
    for asset in baseline.get("assets", []):
        if any(raw.strip() in {".", "./"} for raw in asset.get("locators", [])):
            warnings.append(
                f"Asset {asset.get('id')} maps the repository root; prefer narrower locators"
            )
    return sorted(set(warnings))


def assurance_for_tasks(
    baseline: dict[str, Any],
    assurance: dict[str, Any],
    task_ids: set[str],
    *,
    implementation_frontier: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    impacts, asset_ids = _relevant_records(assurance, task_ids)
    inspections = [
        item
        for item in assurance.get("inspections", [])
        if asset_ids.intersection(item.get("asset_ids", []))
        and (
            not item.get("task_ids")
            or task_ids.intersection(item.get("task_ids", []))
        )
    ]
    findings = [
        item for item in assurance.get("findings", []) if asset_ids.intersection(item.get("asset_ids", []))
    ]
    drift = [
        item
        for item in assurance.get("scope_drift", [])
        if item.get("task") in task_ids
    ]
    blockers = assurance_blockers(
        baseline,
        assurance,
        task_ids=task_ids,
        implementation_frontier=implementation_frontier,
    )
    return {
        "status": "blocked" if blockers else "covered",
        "task_ids": sorted(task_ids),
        "impact_ids": [item["id"] for item in impacts],
        "asset_ids": sorted(asset_ids),
        "inspection_ids": [item["id"] for item in inspections],
        "finding_ids": [item["id"] for item in findings],
        "scope_drift_ids": [item["id"] for item in drift],
        "blockers": blockers,
    }


def scoped_assurance_detail(
    baseline: dict, assurance: dict, *, task_ids: set[str] | None = None,
    asset_id: str | None = None, inspection_id: str | None = None,
    implementation_frontier: dict | None = None,
) -> dict:
    """Select records, but retain the real related-task coverage and blockers."""
    if sum(value is not None for value in (task_ids, asset_id, inspection_id)) != 1:
        raise ValueError('Exactly one assurance scope is required')
    assets = {item['id']: item for item in baseline['assets']}
    inspections = {item['id']: item for item in assurance['inspections']}
    if asset_id is not None:
        if not _stable_id(asset_id) or asset_id not in assets:
            raise ValueError(f'Unknown asset: {asset_id}')
        selected_assets = {asset_id}
    elif inspection_id is not None:
        if not _stable_id(inspection_id) or inspection_id not in inspections:
            raise ValueError(f'Unknown inspection: {inspection_id}')
        selected_assets = set(inspections[inspection_id]['asset_ids'])
    else:
        selected_assets = _relevant_records(assurance, task_ids)[1]
    if task_ids is None:
        # A record can look green while another asset of its consuming task blocks.
        # Coverage is not narrowed to the displayed asset or inspection.
        task_ids = {task for item in assurance['impacts']
                    if item['asset_id'] in selected_assets
                    and item.get('status') != 'dismissed'
                    for task in item['task_ids']}
        task_ids.update(task for item in assurance['inspections']
                        if selected_assets.intersection(item['asset_ids'])
                        for task in item['task_ids'])
    coverage = assurance_for_tasks(
        baseline, assurance, task_ids, implementation_frontier=implementation_frontier)
    selected_baseline = {key: copy.deepcopy(value) for key, value in baseline.items()
                         if key not in {'assets', 'relations'}}
    selected_baseline['assets'] = [copy.deepcopy(assets[aid]) for aid in sorted(selected_assets)]
    selected_baseline['relations'] = [
        copy.deepcopy(item) for item in baseline.get('relations', [])
        if item.get('from') in selected_assets or item.get('to') in selected_assets]
    selected_assurance = {key: copy.deepcopy(value) for key, value in assurance.items()
                          if key not in {'impacts', 'inspections', 'findings', 'scope_drift'}}
    selected_assurance['impacts'] = [
        copy.deepcopy(item) for item in assurance['impacts']
        if item['asset_id'] in selected_assets
        and (not task_ids or task_ids.intersection(item['task_ids']))]
    selected_assurance['inspections'] = [
        copy.deepcopy(item) for item in assurance['inspections']
        if (item['id'] == inspection_id if inspection_id else
            selected_assets.intersection(item['asset_ids'])
            and (not item['task_ids'] or task_ids.intersection(item['task_ids'])))]
    # Findings/drift affecting related task coverage remain load-bearing even
    # when their asset is not displayed. Coverage carries exact recovery IDs.
    selected_assurance['findings'] = [
        copy.deepcopy(item) for item in assurance['findings']
        if item['id'] in coverage['finding_ids']
        or selected_assets.intersection(item['asset_ids'])]
    selected_assurance['scope_drift'] = [
        copy.deepcopy(item) for item in assurance['scope_drift']
        if item['task'] in task_ids]
    omitted = {
        'baseline.' + key: len(baseline.get(key, [])) - len(selected_baseline.get(key, []))
        for key in ('assets', 'relations')}
    omitted.update({
        'assurance.' + key: len(assurance.get(key, [])) - len(selected_assurance.get(key, []))
        for key in ('impacts', 'inspections', 'findings', 'scope_drift')})
    return {
        'selection': {'task_ids': sorted(task_ids), 'asset_id': asset_id,
                      'inspection_id': inspection_id},
        'coverage': coverage, 'baseline': selected_baseline, 'assurance': selected_assurance,
        'omitted_record_counts': omitted,
        'recovery': 'inspect --assurance-detail; inspect --audit-readiness <related-node>',
        'scope_note': 'Selected records are not audit acceptance. Coverage includes blockers from all assets of related tasks; omitted records remain canonical.',
    }


def assurance_summary(
    baseline: dict[str, Any],
    assurance: dict[str, Any],
    *,
    implementation_frontier: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    impacted = {item["asset_id"] for item in assurance.get("impacts", []) if item.get("status") != "dismissed"}
    inspected = {
        aid
        for item in assurance.get("inspections", [])
        if item.get("status") == "performed"
        and item.get("result") == "pass"
        and item.get("sufficiency") == "sufficient"
        and item.get("evidence")
        for aid in item.get("asset_ids", [])
    }
    blockers = assurance_blockers(
        baseline,
        assurance,
        full=True,
        implementation_frontier=implementation_frontier,
    )
    return {
        "policy": assurance.get("policy"),
        "status": "blocked" if blockers else "ready",
        "baseline_status": baseline.get("status"),
        "baseline_revision": baseline.get("revision"),
        "assets": len(baseline.get("assets", [])),
        "impacted_assets": len(impacted),
        "sufficiently_inspected_assets": len(impacted.intersection(inspected)),
        "open_scope_drift": sum(item.get("status") == "open" for item in assurance.get("scope_drift", [])),
        "open_material_findings": sum(
            item.get("status") == "open" and item.get("severity") in {"high", "critical"}
            for item in assurance.get("findings", [])
        ),
        "blockers": blockers,
        "refresh_inspection_ids": sorted(
            inspection.get("id")
            for inspection in assurance.get("inspections", [])
            if inspection.get("id")
            and (
                inspection.get("status") == "stale"
                or any(
                    f"Inspection {inspection.get('id')} " in blocker
                    for blocker in blockers
                )
            )
        ),
        "warnings": assurance_warnings(baseline, assurance),
    }


def mark_assurance_stale(assurance: dict[str, Any], reason: str, actor: str) -> None:
    assurance["status"] = "stale"
    reasons = assurance.setdefault("stale_reasons", [])
    if reason not in reasons:
        reasons.append(reason)
    assurance["updated_at"] = utc_now()
    assurance["updated_by"] = actor
