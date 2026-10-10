"""P3B project_queries boundary; no facade imports.

Existing control flow and canonical/history publication protocol are retained.
"""
from __future__ import annotations
from pathlib import Path
from pyramid_assurance_contracts import RUNTIME_VERSION
from pyramid_assurance_rules import assurance_summary
from pyramid_errors import PyramidError
from pyramid_files import load_json
from pyramid_files import project_paths
from pyramid_handoff_io import handoff_validation_errors
from pyramid_history import history_summary
from pyramid_history import history_validation_errors
from pyramid_proof_io import _proof_errors
from pyramid_state import active_claims
from pyramid_state import completion_errors
from pyramid_state import context_identity
from pyramid_state import lifecycle_state
from pyramid_state import lifecycle_status
from pyramid_state import validate_state
from pyramid_storage import assurance_validation_errors
from pyramid_storage import event_chain_validation_errors
from pyramid_storage import head_validation_errors
from pyramid_storage import implementation_frontier
from pyramid_storage import load_assurance_bundle
from pyramid_storage import load_project
from pyramid_validation import validate_plan
from typing import Any
import copy
import os


def detect_legacy_planner_conflicts() -> list[dict[str, str]]:
    """Return stale standalone planner skills that can conflict with the V3 plugin."""
    configured_home = os.environ.get("CODEX_HOME")
    codex_home = (
        Path(configured_home).expanduser()
        if configured_home
        else Path.home() / ".codex"
    )
    skill_file = codex_home / "skills" / "pyramid-task-planner" / "SKILL.md"
    if not skill_file.exists():
        return []
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError:
        return []
    stale_markers = (
        "The output should be a directory of markdown task files",
        "docs/tasks/README.md",
        "## Default Output Shape",
    )
    if "name: pyramid-task-planner" not in text or not any(
        marker in text for marker in stale_markers
    ):
        return []
    return [
        {
            "path": str(skill_file),
            "kind": "standalone-v2-planner",
            "resolution": (
                "Replace this skill with the published V3 compatibility shim or remove it "
                "from Codex skill discovery; Pyramid Task V3 owns .pyramid state and generated tasks."
            ),
        }
    ]


def intent_transition_route(project: str | Path, *, read_project=load_project) -> dict[str, Any]:
    """Describe the safe lifecycle route for starting another intent."""
    paths = project_paths(project)
    conflicts = detect_legacy_planner_conflicts()
    if not paths["plan"].exists():
        return {
            "runtime_version": RUNTIME_VERSION,
            "project_format_version": None,
            "lifecycle": None,
            "closure_ready": False,
            "active_claims": [],
            "can_start_new_intent": True,
            "recommended_action": "create",
            "transition": ["create"],
            "blockers": [],
            "warnings": [],
            "legacy_skill_conflicts": conflicts,
        }

    paths, plan, state = read_project(project)
    manifest = load_json(paths["project"]) if paths["project"].exists() else None
    _, baseline, assurance = load_assurance_bundle(paths, plan)
    frontier = implementation_frontier(paths)
    project_format = manifest["format_version"]
    status = lifecycle_status(state)
    claims = active_claims(state)
    closure_ready = (
        status == "active"
        and not claims
        and not completion_errors(plan, state, baseline, assurance, frontier)
    )
    blockers: list[str] = []
    warnings: list[str] = []
    transition: list[str] = []
    recommended_action = "continue-current-intent"
    can_start = False

    if claims:
        blockers.append("Resolve active claims (working or paused) before changing intents: " + ", ".join(claims))
    elif status == "completed":
        can_start = True
        recommended_action = "preview-new-intent"
        transition = ["archive", "reset"]
    elif status == "archived":
        can_start = True
        recommended_action = "preview-new-intent"
        transition = ["reset"]
    elif closure_ready:
        recommended_action = "close-then-preview-new-intent"
        blockers.append(
            "The current graph is verified but not formally closed. Run close to produce its final "
            "report and change dossier, then preview the new intent again."
        )
    else:
        blockers.append(
            "The current intent is active. Complete it, or explicitly archive/reset it after user approval."
        )

    summaries = history_summary(paths["meta"], plan["plan_id"])["chronicles"]
    latest = next(
        (item for item in reversed(summaries) if item.get("plan_id") == plan["plan_id"]),
        None,
    )
    if latest and latest.get("binding_status") in {"pending", "unavailable"}:
        warnings.append(
            f"Intent history binding is {latest['binding_status']}: "
            f"{latest.get('binding_next_action') or 'review the chronicle before transition.'}"
        )

    return {
        "runtime_version": RUNTIME_VERSION,
        "project_format_version": project_format,
        "plan_id": plan["plan_id"],
        "lifecycle": status,
        "closure_ready": closure_ready,
        "active_claims": claims,
        "can_start_new_intent": can_start,
        "recommended_action": recommended_action,
        "transition": transition,
        "blockers": blockers,
        "warnings": warnings,
        "legacy_skill_conflicts": conflicts,
    }


def list_archives(project: str | Path) -> list[dict[str, Any]]:
    paths = project_paths(project)
    archives: list[dict[str, Any]] = []
    if not paths["archives"].exists():
        return archives
    for child in sorted(paths["archives"].iterdir(), reverse=True):
        manifest_path = child / "manifest.json"
        if not child.is_dir() or not manifest_path.exists():
            continue
        try:
            manifest = load_json(manifest_path)
        except PyramidError:
            continue
        manifest["path"] = str(child)
        archives.append(manifest)
    return archives


def inspect_lifecycle(project: str | Path, *, read_project=load_project) -> dict[str, Any]:
    paths = project_paths(project)
    archives = list_archives(project)
    if not paths["plan"].exists():
        return {"schema": "pyramid-lifecycle-v1", "current": None, "archives": archives}
    paths, plan, state = read_project(project)
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    frontier = implementation_frontier(paths)
    errors = (
        completion_errors(plan, state, baseline, assurance, frontier) + _proof_errors(paths, plan, state)
        if lifecycle_status(state) == "active"
        else []
    )
    return {
        "schema": "pyramid-lifecycle-v1",
        "plan_id": plan["plan_id"],
        "graph_version": state["graph_version"],
        "context": context_identity(plan, state),
        "lifecycle": copy.deepcopy(lifecycle_state(state)),
        "closure_ready": lifecycle_status(state) == "active" and not errors,
        "closure_blockers": errors,
        "active_claims": active_claims(state),
        "paused": [
            {
                "task": nid,
                "handoff_id": item.get("active_handoff_id"),
                "mode": item.get("pause_mode"),
                "paused_by": item.get("paused_by"),
                "paused_at": item.get("paused_at"),
                "resume_deadline": item.get("resume_deadline"),
            }
            for nid, item in sorted(state["nodes"].items())
            if item.get("execution") == "paused"
        ],
        "project": copy.deepcopy(manifest) if manifest else {
            "format_version": "legacy-v2",
            "mode": "legacy",
        },
        "assurance": assurance_summary(
            baseline,
            assurance,
            implementation_frontier=frontier,
        )
        if baseline is not None and assurance is not None
        else None,
        "archives": archives,
    }


def validate_project(project: str | Path) -> dict[str, Any]:
    paths = project_paths(project)
    plan = load_json(paths["plan"])
    state = load_json(paths["state"])
    errors = (
        validate_plan(plan)
        + validate_state(plan, state)
        + assurance_validation_errors(paths, plan)
        + handoff_validation_errors(paths, plan, state)
        + head_validation_errors(paths, plan, state)
        + event_chain_validation_errors(paths)
        + history_validation_errors(paths["meta"])
    )
    manifest = load_json(paths["project"]) if paths["project"].exists() else None
    return {
        "valid": not errors,
        "errors": errors,
        "plan_id": plan.get("plan_id"),
        "revision": plan.get("revision"),
        "graph_version": state.get("graph_version"),
        "context": context_identity(plan, state),
        "project_format_version": manifest.get("format_version") if manifest else "legacy-v2",
        "mode": manifest.get("mode") if manifest else "legacy",
    }
