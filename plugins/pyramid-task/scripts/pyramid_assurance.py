"""Legacy assurance exports and clock adapters; concrete boundaries below."""
from __future__ import annotations

import fnmatch
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from pyramid_assurance_contracts import PROJECT_FORMAT_VERSION, RUNTIME_VERSION, ID_PATTERN, ASSET_KINDS, CRITICALITIES, CONFIDENCE, BASELINE_STATUSES, RELATION_TYPES, IMPACT_TYPES, IMPACT_STATUSES, INSPECTION_STATUSES, INSPECTION_RESULTS, SUFFICIENCY, FINDING_STATUSES, ASSURANCE_STATUSES, CONTROL_STATUSES, HISTORY_KINDS, CHANGE_CLASSES, DEFAULT_INVALIDATION_CLASSES, REFRESH_POLICIES, _strings, _stable_id, validate_project_manifest, validate_baseline, validate_assurance
from pyramid_assurance_rules import _parse_time, _relevant_records, assurance_blockers, asset_ids_for_file, inspection_freshness_blockers, assurance_warnings, assurance_for_tasks, assurance_summary
from pyramid_assurance_io import artifact_footprint, detect_repository_mode
import pyramid_assurance_defaults as _defaults

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_project_manifest(
    *,
    plan_id: str,
    mode: str,
    actor: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    return _defaults.default_project_manifest(plan_id=plan_id, mode=mode, actor=actor, timestamp=created_at or utc_now())


def default_baseline(*, actor: str, root_locator: str = ".") -> dict[str, Any]:
    return _defaults.default_baseline(actor=actor, root_locator=root_locator, timestamp=utc_now())


def default_assurance(
    *,
    plan_id: str,
    baseline: dict[str, Any],
    actor: str,
    policy: str = "brownfield",
) -> dict[str, Any]:
    baseline_id = baseline["baseline_id"]
    baseline_revision = baseline["revision"]
    return _defaults.default_assurance(plan_id=plan_id, baseline_id=baseline_id,
        baseline_revision=baseline_revision, actor=actor, policy=policy, timestamp=utc_now())




import pyramid_assurance_rules as _rules

def mark_assurance_stale(assurance: dict[str, Any], reason: str, actor: str) -> None:
    _rules.prepare_assurance_stale(assurance, reason)
    timestamp = utc_now()
    _rules.apply_assurance_stale_timestamp(assurance, timestamp, actor)
