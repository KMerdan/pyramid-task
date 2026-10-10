"""Baseline/assurance contracts and ordered validation stages.

Helpers append to the operation-local error list in the original order.
"""
from __future__ import annotations
import re
from typing import Any

PROJECT_FORMAT_VERSION = 3

RUNTIME_VERSION = "4.2.1"

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

def _strings(value: Any, *, nonempty: bool = False) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and (not nonempty or bool(item.strip())) for item in value
    )

def _stable_id(value: Any) -> bool:
    return isinstance(value, str) and bool(ID_PATTERN.match(value))

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


def _validate_assurance_identity(assurance, plan, baseline, errors):
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


def _validate_assurance_generated_assets(plan, asset_ids, errors):
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


def _validate_assurance_impacts(assurance, asset_ids, task_ids, errors):
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
    return impact_ids, impacts


def _validate_assurance_inspections(assurance, asset_ids, task_ids, errors):
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
    return inspection_ids


def _validate_assurance_findings(assurance, asset_ids, task_ids, inspection_ids, errors):
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


def _validate_assurance_drift(assurance, asset_ids, task_ids, impact_ids, impacts, errors):
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


def _validate_assurance_controls(assurance, asset_ids, errors):
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


def validate_assurance(
    assurance: dict[str, Any],
    *,
    plan: dict[str, Any],
    baseline: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    _validate_assurance_identity(assurance, plan, baseline, errors)
    asset_ids = {item["id"] for item in baseline.get("assets", []) if isinstance(item, dict) and "id" in item}
    task_ids = {item["id"] for item in plan.get("nodes", []) if isinstance(item, dict) and "id" in item}
    _validate_assurance_generated_assets(plan, asset_ids, errors)
    impact_ids, impacts = _validate_assurance_impacts(assurance, asset_ids, task_ids, errors)
    inspection_ids = _validate_assurance_inspections(assurance, asset_ids, task_ids, errors)
    _validate_assurance_findings(assurance, asset_ids, task_ids, inspection_ids, errors)
    _validate_assurance_drift(assurance, asset_ids, task_ids, impact_ids, impacts, errors)
    _validate_assurance_controls(assurance, asset_ids, errors)
    return errors
