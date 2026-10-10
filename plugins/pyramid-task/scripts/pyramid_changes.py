"""Value-only change scope, classification, drift and coverage rules.

Inspection helpers intentionally mutate the supplied assurance value. No clock,
project/files/processes or core import; effect coordination is in change_io.
"""
from __future__ import annotations
import fnmatch
import hashlib
from collections import defaultdict
from typing import Any, Iterable
from pyramid_assurance_contracts import DEFAULT_INVALIDATION_CLASSES
from pyramid_assurance_rules import asset_ids_for_file, assurance_blockers
from pyramid_graph import node_map
from pyramid_state import _covered_assurance_tasks


def _path_matches(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.strip().lstrip("./")
    for raw in patterns:
        pattern = raw.strip().lstrip("./")
        prefix = pattern.removesuffix("/**").removesuffix("/*").rstrip("/")
        if (
            fnmatch.fnmatch(normalized, pattern)
            or normalized == prefix
            or normalized.startswith(prefix + "/")
        ):
            return True
    return False


def _generated_assets_for_path(node: dict[str, Any], path: str) -> set[str]:
    assets: set[str] = set()
    for declaration in node.get("agent", {}).get("generated_outputs", []):
        if isinstance(declaration, dict) and _path_matches(
            path, [declaration.get("pattern", "")]
        ):
            assets.update(declaration.get("asset_ids", []))
    return assets


def _classified_changes(
    result: dict[str, Any], node: dict[str, Any]
) -> list[dict[str, str]]:
    explicit = {
        item.get("path"): item.get("class")
        for item in result.get("changes", [])
        if isinstance(item, dict)
    }
    effect = result.get("change_effect")
    evidence_outputs = node.get("agent", {}).get("evidence_outputs", [])
    records: list[dict[str, str]] = []
    for path in result.get("changed_files", []):
        if not isinstance(path, str) or not path.strip():
            continue
        change_class = explicit.get(path)
        if change_class is None:
            if effect == "evidence-only" or _path_matches(path, evidence_outputs):
                change_class = "evidence"
            elif _generated_assets_for_path(node, path):
                change_class = "generated"
            else:
                change_class = "source"
        records.append({"path": path, "class": change_class})
    return records


def scope_drift_records(plan, state, nid, result, baseline, assurance):
    expected_assets = {
        impact["asset_id"]
        for impact in assurance.get("impacts", [])
        if nid in impact.get("task_ids", []) and impact.get("status") != "dismissed"
    }
    node = node_map(plan)[nid]
    candidates: list[tuple[str, set[str], set[str]]] = []
    for change in _classified_changes(result, node):
        changed_file = change["path"]
        change_class = change["class"]
        if change_class == "evidence":
            continue
        matched = asset_ids_for_file(baseline, changed_file)
        declared = (
            _generated_assets_for_path(node, changed_file)
            if change_class == "generated"
            else set()
        )
        candidates.append((changed_file, matched | declared, expected_assets | declared))
    known_assets = {item["id"] for item in baseline.get("assets", [])}
    if result.get("change_effect") != "evidence-only":
        for changed_asset in result.get("changed_assets", []):
            matched = {changed_asset} if changed_asset in known_assets else set()
            candidates.append((f"asset:{changed_asset}", matched, expected_assets))
    records: list[dict[str, Any]] = []
    drift_ids: list[str] = []
    affected_assets: set[str] = set()
    for changed_file, matched_assets, allowed_assets in candidates:
        if matched_assets and matched_assets.issubset(allowed_assets):
            continue
        token = hashlib.sha256(
            f"{nid}\0{changed_file}\0{state['graph_version']}".encode("utf-8")
        ).hexdigest()[:12].upper()
        drift_id = f"DRIFT-{token}"
        if any(item.get("id") == drift_id for item in assurance.get("scope_drift", []) + records):
            continue
        records.append(
            {
                "id": drift_id,
                "task": nid,
                "changed_file": changed_file,
                "matched_asset_ids": sorted(matched_assets),
                "status": "open",
                "detected_at": None,
                "resolved_impact_id": None,
            }
        )
        drift_ids.append(drift_id)
        affected_assets.update(matched_assets or expected_assets)
    return records, affected_assets


def invalidate_drift_inspections(assurance, affected_assets, nid):
    for inspection in assurance.get("inspections", []):
        if (
            "unknown"
            in set(inspection.get("invalidated_by", DEFAULT_INVALIDATION_CLASSES))
            and affected_assets.intersection(inspection.get("asset_ids", []))
        ):
            inspection["status"] = "stale"
            limitations = inspection.setdefault("limitations", [])
            message = f"Scope drift from {nid} invalidated this inspection."
            if message not in limitations:
                limitations.append(message)


def invalidate_actual_changes(plan, nid, result, baseline, assurance):
    known_assets = {item["id"] for item in baseline.get("assets", [])}
    node = node_map(plan)[nid]
    changed_assets_by_class: dict[str, set[str]] = defaultdict(set)
    asset_class = (
        "evidence" if result.get("change_effect") == "evidence-only" else "source"
    )
    changed_assets_by_class[asset_class].update(
        asset_id
        for asset_id in result.get("changed_assets", [])
        if asset_id in known_assets
    )
    for change in _classified_changes(result, node):
        changed_assets_by_class[change["class"]].update(
            asset_ids_for_file(baseline, change["path"])
        )
        if change["class"] == "generated":
            changed_assets_by_class["generated"].update(
                _generated_assets_for_path(node, change["path"])
            )
    changed_assets = set().union(*changed_assets_by_class.values())
    if not changed_assets:
        return [], set(), False
    stale: list[str] = []
    invalidated_assets: set[str] = set()
    touched = False
    for inspection in assurance.get("inspections", []):
        invalidated_by = set(
            inspection.get("invalidated_by", DEFAULT_INVALIDATION_CLASSES)
        )
        overlapping = set().union(
            *(
                assets.intersection(inspection.get("asset_ids", []))
                for change_class, assets in changed_assets_by_class.items()
                if change_class in invalidated_by
            )
        ) if invalidated_by else set()
        if not overlapping:
            continue
        touched = True
        invalidated_assets.update(overlapping)
        if inspection.get("status") == "performed":
            inspection["status"] = "stale"
            stale.append(inspection["id"])
        limitations = inspection.setdefault("limitations", [])
        message = (
            f"Implementation result for {nid} changed covered assets after this inspection: "
            + ", ".join(sorted(overlapping))
            + "."
        )
        if message not in limitations:
            limitations.append(message)
    if not touched:
        return [], set(), False
    return sorted(stale), invalidated_assets, touched


def invalidate_changed_tasks(assurance, task_ids, reason):
    impacted_assets = {
        impact["asset_id"]
        for impact in assurance.get("impacts", [])
        if task_ids.intersection(impact.get("task_ids", []))
        and impact.get("status") != "dismissed"
    }
    invalidated: list[str] = []
    for inspection in assurance.get("inspections", []):
        if not (
            task_ids.intersection(inspection.get("task_ids", []))
            or impacted_assets.intersection(inspection.get("asset_ids", []))
        ):
            continue
        if inspection.get("status") == "performed":
            inspection["status"] = "stale"
            invalidated.append(inspection["id"])
        limitations = inspection.setdefault("limitations", [])
        if reason not in limitations:
            limitations.append(reason)
    return sorted(invalidated)


def assurance_audit_errors(plan, state, node, evidence, baseline, assurance, frontier):
    if state["graph_version"] < assurance.get("enforce_from_graph_version", 1):
        return []
    assertion = evidence.get("assurance")
    if not isinstance(assertion, dict):
        return ["Brownfield audit pass requires an assurance coverage assertion"]
    errors: list[str] = []
    covered_tasks = _covered_assurance_tasks(plan, node)
    full = node["id"] == plan["intent"]["id"]
    errors.extend(
        assurance_blockers(
            baseline,
            assurance,
            task_ids=None if full else covered_tasks,
            full=full,
            implementation_frontier=frontier,
        )
    )
    relevant_impacts = [
        item
        for item in assurance.get("impacts", [])
        if item.get("status") != "dismissed"
        and (full or covered_tasks.intersection(item.get("task_ids", [])))
    ]
    relevant_assets = {item["asset_id"] for item in relevant_impacts}
    relevant_inspections = [
        item
        for item in assurance.get("inspections", [])
        if relevant_assets.intersection(item.get("asset_ids", []))
        and (
            full
            or not item.get("task_ids")
            or covered_tasks.intersection(item.get("task_ids", []))
        )
    ]
    expected_impacts = {item["id"] for item in relevant_impacts}
    expected_inspections = {
        item["id"]
        for item in relevant_inspections
        if item.get("required")
        or (
            item.get("status") == "performed"
            and item.get("result") == "pass"
            and item.get("sufficiency") == "sufficient"
        )
    }
    expected_findings = {
        item["id"]
        for item in assurance.get("findings", [])
        if relevant_assets.intersection(item.get("asset_ids", []))
    }
    asserted_impacts = set(assertion.get("impact_ids", []))
    asserted_inspections = set(assertion.get("inspection_ids", []))
    asserted_findings = set(assertion.get("finding_ids", []))
    known_impacts = {item["id"] for item in assurance.get("impacts", [])}
    known_inspections = {item["id"] for item in assurance.get("inspections", [])}
    known_findings = {item["id"] for item in assurance.get("findings", [])}
    if not expected_impacts.issubset(asserted_impacts):
        errors.append(
            "Audit assurance omits impact records: "
            + ", ".join(sorted(expected_impacts - asserted_impacts))
        )
    if not expected_inspections.issubset(asserted_inspections):
        errors.append(
            "Audit assurance omits inspection records: "
            + ", ".join(sorted(expected_inspections - asserted_inspections))
        )
    if not expected_findings.issubset(asserted_findings):
        errors.append(
            "Audit assurance omits findings: "
            + ", ".join(sorted(expected_findings - asserted_findings))
        )
    for label, asserted, known in (
        ("impact", asserted_impacts, known_impacts),
        ("inspection", asserted_inspections, known_inspections),
        ("finding", asserted_findings, known_findings),
    ):
        unknown = asserted - known
        if unknown:
            errors.append(
                f"Audit assurance references unknown {label} records: "
                + ", ".join(sorted(unknown))
            )
    if assertion.get("scope_review") != "complete":
        errors.append("Audit assurance scope review is incomplete")
    return sorted(set(errors))
