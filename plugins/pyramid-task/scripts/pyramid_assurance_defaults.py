"""Pure placeholder values with explicit timestamps and baseline identity."""
from __future__ import annotations
from typing import Any
from pyramid_assurance_contracts import PROJECT_FORMAT_VERSION, RUNTIME_VERSION

def default_project_manifest(
    *,
    plan_id: str,
    mode: str,
    actor: str,
    timestamp: str,
) -> dict[str, Any]:
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


def default_baseline(*, actor: str, root_locator: str = ".", timestamp: str) -> dict[str, Any]:
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
    baseline_id: str,
    baseline_revision: int,
    timestamp: str,
    actor: str,
    policy: str = "brownfield",
) -> dict[str, Any]:
    return {
        "schema": "pyramid-assurance-v1",
        "plan_id": plan_id,
        "baseline_id": baseline_id,
        "baseline_revision": baseline_revision,
        "policy": policy,
        "status": "incomplete",
        "updated_at": timestamp,
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
