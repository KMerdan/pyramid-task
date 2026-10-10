"""Explicit assurance read/effect/write coordination under caller-owned lock.

Value rules live in changes; clocks and existing stale-marker effects stay here.
No commands/facade imports or additional transaction/rollback protocol.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from pyramid_files import utc_now, write_json
from pyramid_storage import load_assurance_bundle, implementation_frontier
from pyramid_state import invalidate_dependent_claims
from pyramid_assurance import mark_assurance_stale
from pyramid_changes import (scope_drift_records, invalidate_drift_inspections,
    invalidate_actual_changes, invalidate_changed_tasks, assurance_audit_errors)


def _record_scope_drift(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
    nid: str,
    result: dict[str, Any],
    actor: str,
    *,
    clock=utc_now,
) -> tuple[list[str], list[str]]:
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or baseline is None or assurance is None:
        return [], []
    records, affected_assets = scope_drift_records(plan, state, nid, result, baseline, assurance)
    drift_ids = []
    for record in records:
        record["detected_at"] = clock()
        assurance.setdefault("scope_drift", []).append(record)
        drift_ids.append(record["id"])
    if not drift_ids:
        return [], []
    invalidate_drift_inspections(assurance, affected_assets, nid)
    mark_assurance_stale(
        assurance,
        f"Unexpected implementation scope was recorded for {nid}: {', '.join(drift_ids)}",
        actor,
    )
    assurance["updated_at"] = clock()
    assurance["updated_by"] = actor
    write_json(paths["assurance"], assurance)
    invalidated = invalidate_dependent_claims(
        plan,
        state,
        nid,
        f"Scope drift for {nid} made dependent assurance stale.",
        timestamp=clock(),
    )
    return drift_ids, invalidated

def _invalidate_inspections_for_actual_change(
    paths: dict[str, Path],
    plan: dict[str, Any],
    nid: str,
    result: dict[str, Any],
    actor: str,
) -> list[str]:
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or baseline is None or assurance is None:
        return []
    stale, invalidated_assets, touched = invalidate_actual_changes(plan, nid, result, baseline, assurance)
    if not touched:
        return []
    mark_assurance_stale(
        assurance,
        f"Implementation for {nid} changed assets {', '.join(sorted(invalidated_assets))}; post-change inspection is required.",
        actor,
    )
    write_json(paths["assurance"], assurance)
    return stale

def _invalidate_assurance_for_change(
    paths: dict[str, Path],
    plan: dict[str, Any],
    task_ids: set[str],
    actor: str,
    reason: str,
) -> list[str]:
    manifest, _, assurance = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or assurance is None:
        return []
    invalidated = invalidate_changed_tasks(assurance, task_ids, reason)
    mark_assurance_stale(assurance, reason, actor)
    write_json(paths["assurance"], assurance)
    return sorted(invalidated)

def _assurance_audit_errors(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
    node: dict[str, Any],
    evidence: dict[str, Any],
) -> list[str]:
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if not manifest or manifest.get("mode") != "brownfield" or baseline is None or assurance is None:
        return []
    if state["graph_version"] < assurance.get("enforce_from_graph_version", 1):
        return []
    assertion = evidence.get("assurance")
    if not isinstance(assertion, dict):
        return ["Brownfield audit pass requires an assurance coverage assertion"]
    return assurance_audit_errors(plan, state, node, evidence, baseline, assurance,
                                 implementation_frontier(paths))
