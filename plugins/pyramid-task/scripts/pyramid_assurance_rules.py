"""Pure freshness, blocker and scoped assurance projections."""
from __future__ import annotations
import fnmatch
from datetime import datetime
from typing import Any
from pyramid_assurance_contracts import PROJECT_FORMAT_VERSION, RUNTIME_VERSION, ID_PATTERN, ASSET_KINDS, CRITICALITIES, CONFIDENCE, BASELINE_STATUSES, RELATION_TYPES, IMPACT_TYPES, IMPACT_STATUSES, INSPECTION_STATUSES, INSPECTION_RESULTS, SUFFICIENCY, FINDING_STATUSES, ASSURANCE_STATUSES, CONTROL_STATUSES, HISTORY_KINDS, CHANGE_CLASSES, DEFAULT_INVALIDATION_CLASSES, REFRESH_POLICIES, _strings

def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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


def prepare_assurance_stale(assurance: dict[str, Any], reason: str) -> None:
    assurance["status"] = "stale"
    reasons = assurance.setdefault("stale_reasons", [])
    if reason not in reasons:
        reasons.append(reason)


def apply_assurance_stale_timestamp(assurance: dict[str, Any], timestamp: str, actor: str) -> None:
    assurance["updated_at"] = timestamp
    assurance["updated_by"] = actor
