from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from pyramid_assurance_contracts import CHANGE_CLASSES, DEFAULT_INVALIDATION_CLASSES, PROJECT_FORMAT_VERSION, RUNTIME_VERSION, validate_assurance, validate_baseline, validate_project_manifest
from pyramid_assurance import mark_assurance_stale
from pyramid_assurance_rules import asset_ids_for_file, assurance_blockers, assurance_for_tasks, assurance_summary
from pyramid_assurance_io import artifact_footprint, detect_repository_mode
from pyramid_assurance import default_assurance, default_baseline, default_project_manifest
from pyramid_graph import (
    AUDIT_BLOCKING,
    EDGE_TYPES,
    EXECUTABLE_KINDS,
    EXECUTION_STATES,
    HEALTH_STATES,
    ID_PATTERN,
    NODE_KINDS,
    PLAN_LIFECYCLE_STATES,
    SELECTIONS,
    START_BLOCKING,
    VERIFICATION_STATES,
    availability,
    claim_relations,
    edges_from,
    edges_to,
    node_map,
    start_blockers,
)
from pyramid_parallel import build_parallel_frontier, _patterns_overlap, _task_scopes
from pyramid_amendment import prepare_amendment
from pyramid_verification import (
    VerificationError, contracts as verification_contracts, normalize_proofs,
    proof_readiness, publish_artifacts, query_harness, render_guide,
    validate_contracts, validate_amendment_inputs,
    replan_proof_bindings, validate_proof_bindings,
)
from pyramid_history import (
    HistoryError,
    ensure_intent_start,
    history_chronicles,
    history_contains_plan,
    history_health,
    history_summary,
    history_validation_errors,
    query_history,
    rebuild_history_index,
    record_code_binding,
    record_intent_chronicle,
    repair_history_transaction,
)

# Compatibility exports for the isolated pure validation boundary.
from pyramid_validation import _cycle, _is_string_list, validate_plan

from pyramid_errors import PyramidError

import pyramid_files as _files
import pyramid_storage as _storage
import pyramid_publication as _publication
import pyramid_change_io as _change_io
from pyramid_files import (
    load_json,
    write_json,
    project_paths,
    require_supported_project,
    project_lock,
    write_projection_text,
    _file_sha256,
    UNSUPPORTED_LEGACY_PROJECT,
)
from pyramid_storage import (
    load_assurance_bundle,
    assurance_validation_errors,
    implementation_frontier,
    _collection_sha256,
    _canonical_file_hashes,
    _previous_event,
    _publish_head,
    _persist_event,
    head_validation_errors,
    event_chain_validation_errors,
    load_project,
)
from pyramid_handoff import (
    _validate_handoff_draft,
    _handoff_path,
    _handoff_markdown,
    _handoff_record_errors,
    HANDOFF_DRAFT_FIELDS,
)
from pyramid_handoff_io import (
    _git_output,
    worktree_fingerprint,
    handoff_validation_errors,
    _handoff_fingerprint,
    _handoff_drift,
)
from pyramid_changes import (
    _path_matches,
    _generated_assets_for_path,
    _classified_changes,
)
from pyramid_change_io import (
    _invalidate_inspections_for_actual_change,
    _invalidate_assurance_for_change,
    _assurance_audit_errors,
)
from pyramid_state import (
    SCHEMA_VERSION,
    default_lifecycle,
    lifecycle_state,
    lifecycle_status,
    require_active,
    active_claims,
    canonical_sha256,
    canonical_context_id,
    context_identity,
    _guard_token,
    task_mutation_guard,
    audit_mutation_guard,
    check_expected_guard,
    clear_active_pause,
    validate_state,
    completion_errors,
    check_expected_version,
    _covered_assurance_tasks,
    dependent_claims,
    initial_node_state as _initial_node_state,
    invalidate_dependent_claims as _invalidate_dependent_claims,
)
from pyramid_topology import (
    EXPANSION_PARENT_FIELDS,
    _edge_key,
    prepare_replan,
    _semantic_node,
    expansion_parent_snapshot,
    _expansion_errors,
    prepare_expansion,
)
from pyramid_projection import (
    goal_trace,
    task_packet,
    task_summary,
    slugify,
    node_doc_path,
    _markdown_list,
    render_node_markdown,
    _report_markdown,
    _dossier_markdown,
    _build_change_dossier,
    _completion_report,
    graph_snapshot as _graph_snapshot,
    prepare_graph_nodes as _prepare_graph_nodes,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


import pyramid_project_queries as _pyramid_project_queries
import pyramid_plan_bundle as _pyramid_plan_bundle
import pyramid_plan_commands as _pyramid_plan_commands
import pyramid_plan_lifecycle as _pyramid_plan_lifecycle
import pyramid_assurance_commands as _pyramid_assurance_commands
from pyramid_assurance_commands import _assurance_semantic_sha256
from pyramid_plan_bundle import _copy_current_snapshot
from pyramid_plan_bundle import _prepare_new_project_bundle
from pyramid_plan_bundle import _purge_current
from pyramid_plan_bundle import _resolve_archive
from pyramid_project_queries import detect_legacy_planner_conflicts
from pyramid_project_queries import list_archives
from pyramid_project_queries import validate_project

def _plan_ports():
    return _pyramid_plan_bundle.PlanPorts(load_project,compile_project,_compile_project_locked,utc_now,
        datetime,commit_event,_event_id,invalidate_dependent_claims,inspect_lifecycle,validate_project,
        initial_node_state,parse_time,intent_transition_route)

import pyramid_queries as _pyramid_queries
import pyramid_history_commands as _pyramid_history_commands

def _query_ports():
    return _pyramid_queries.QueryPorts(load_project, compile_project, validate_project,
        graph_snapshot, _proof_errors, _audit_proof_dependencies)

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    return _files.parse_time(value, clock=datetime)


def intent_transition_route(project: str | Path) -> dict[str, Any]:
    'Describe the safe lifecycle route for starting another intent.'
    return _pyramid_project_queries.intent_transition_route(project, read_project=load_project)


def _handoff_identifier(nid: str) -> str:
    return _files._handoff_identifier(nid, clock=datetime)


def initial_node_state(node: dict[str, Any], now: str | None = None) -> dict[str, Any]:
    return _initial_node_state(node, now or utc_now())


def graph_snapshot(
    plan: dict[str, Any],
    state: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    assurance: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    frontier: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _pyramid_queries.runtime_snapshot(plan, state, baseline, assurance, manifest, frontier, clock=utc_now)


def write_projection_json(path: Path, data: Any) -> bool:
    return _files.write_projection_json(path, data, writer=write_projection_text)


def _compile_project_locked(project: str | Path, *, allow_archived: bool = False) -> dict[str, Any]:
    return _publication._compile_project_locked(project, allow_archived=allow_archived,
        read_project=load_project, clock=utc_now, text_writer=write_projection_text)


def compile_project(project: str | Path, *, allow_archived: bool = False) -> dict[str, Any]:
    return _publication.compile_project(project, allow_archived=allow_archived,
        read_project=load_project, clock=utc_now, text_writer=write_projection_text)


def compile_and_load_graph(project: str | Path, *, allow_archived: bool = False) -> dict[str, Any]:
    return _publication.compile_and_load_graph(project, allow_archived=allow_archived,
        read_project=load_project, clock=utc_now, text_writer=write_projection_text)


def _event_id() -> str:
    return _files._event_id(clock=datetime)


def commit_event(
    paths: dict[str, Path],
    state: dict[str, Any],
    *,
    actor: str,
    event_type: str,
    node: str | None,
    before: Any,
    after: Any,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _storage.commit_event(paths, state, actor=actor, event_type=event_type,
        node=node, before=before, after=after, payload=payload, clock=utc_now, event_id=_event_id)


def create_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    force: bool = False,
    *,
    mode: str = "auto",
    baseline_path: str | Path | None = None,
    assurance_path: str | Path | None = None,
) -> dict[str, Any]:
    return _pyramid_plan_commands.create_project(project, plan_path, actor, force, mode=mode, baseline_path=baseline_path, assurance_path=assurance_path, ports=_plan_ports())


def assess_project(
    project: str | Path,
    baseline_path: str | Path,
    actor: str,
    *,
    apply: bool = False,
    expected_version: int | dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _pyramid_assurance_commands.assess_project(project, baseline_path, actor, apply=apply, expected_version=expected_version, ports=_plan_ports())


def _normalize_assurance_candidate(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    actor: str,
    frontier: dict[str, dict[str, Any]],
    *,
    stamp: bool,
) -> tuple[dict[str, Any], list[str]]:
    return _pyramid_assurance_commands._normalize_assurance_candidate(candidate, baseline, actor, frontier, stamp=stamp, ports=_plan_ports())


def impact_project(
    project: str | Path,
    assurance_path: str | Path,
    actor: str,
    *,
    apply: bool = False,
    expected_version: int | dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _pyramid_assurance_commands.impact_project(project, assurance_path, actor, apply=apply, expected_version=expected_version, ports=_plan_ports())


import pyramid_task_commands as _tasks
from pyramid_results import _validate_agent_result, _audit_prerequisite_errors, _validate_audit_result
from pyramid_proof_io import _normalize_proofs, _proof_errors, _audit_proof_dependencies


def _task_ports():
    return _tasks.TaskPorts(load_project, compile_project, _compile_project_locked,
                            utc_now, datetime, commit_event, _handoff_identifier,
                            _record_scope_drift, invalidate_dependent_claims, parse_time)


def take_task(
    project: str | Path,
    actor: str,
    nid: str | None = None,
    take_next: bool = False,
    lease_minutes: int = 120,
    expected_version: int | dict[str, Any] | None = None,
    expected_guard: str | None = None,
) -> dict[str, Any]:
    return _tasks.take_task(project, actor, nid, take_next, lease_minutes, expected_version, expected_guard, ports=_task_ports())


def pause_task(
    project: str | Path,
    nid: str,
    actor: str,
    reason: str,
    handoff_path: str | Path,
    *,
    mode: str = "hold",
    resume_minutes: int = 60,
    expected_version: int | dict[str, Any] | None = None,
    expected_guard: str | None = None,
) -> dict[str, Any]:
    'Pause an owned task and persist a complete, immutable continuation record.'
    return _tasks.pause_task(project, nid, actor, reason, handoff_path, mode=mode, resume_minutes=resume_minutes, expected_version=expected_version, expected_guard=expected_guard, ports=_task_ports())


def resume_task(
    project: str | Path,
    nid: str,
    actor: str,
    *,
    handoff_id: str | None = None,
    lease_minutes: int = 120,
    accept_stale: bool = False,
    takeover: bool = False,
    for_recovery: bool = False,
    expected_version: int | dict[str, Any] | None = None,
) -> dict[str, Any]:
    'Resume a paused task only after its recorded continuation context is checked.'
    return _tasks.resume_task(project, nid, actor, handoff_id=handoff_id, lease_minutes=lease_minutes, accept_stale=accept_stale, takeover=takeover, for_recovery=for_recovery, expected_version=expected_version, ports=_task_ports())


def _record_scope_drift(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
    nid: str,
    result: dict[str, Any],
    actor: str,
) -> tuple[list[str], list[str]]:
    return _change_io._record_scope_drift(paths, plan, state, nid, result, actor, clock=utc_now)


def update_task(
    project: str | Path,
    nid: str,
    actor: str,
    status: str,
    reason: str | None = None,
    result_path: str | Path | None = None,
    expected_version: int | dict[str, Any] | None = None,
    expected_guard: str | None = None,
) -> dict[str, Any]:
    return _tasks.update_task(project, nid, actor, status, reason, result_path, expected_version, expected_guard, ports=_task_ports())


def invalidate_dependent_claims(
    plan: dict[str, Any],
    state: dict[str, Any],
    origin: str,
    reason: str,
) -> list[str]:
    return _invalidate_dependent_claims(plan, state, origin, reason, timestamp=utc_now())


def audit_node(
    project: str | Path,
    nid: str,
    actor: str,
    result_value: str,
    evidence_path: str | Path,
    expected_version: int | dict[str, Any] | None = None,
    expected_guard: str | None = None,
) -> dict[str, Any]:
    return _tasks.audit_node(project, nid, actor, result_value, evidence_path, expected_version, expected_guard, ports=_task_ports())


def expand_project(
    project: str | Path,
    proposal_path: str | Path,
    actor: str,
    *,
    apply: bool,
    approved_by: str | None = None,
    approval_reference: str | None = None,
    approved_proposal_sha256: str | None = None,
    expected_version: int | dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _pyramid_plan_commands.expand_project(project, proposal_path, actor, apply=apply, approved_by=approved_by, approval_reference=approval_reference, approved_proposal_sha256=approved_proposal_sha256, expected_version=expected_version, ports=_plan_ports())


def amend_task(
    project: str | Path,
    proposal_path: str | Path,
    actor: str,
    apply: bool = False,
    expected_amendment: str | None = None,
) -> dict[str, Any]:
    "Extend one live owner's implementation context without replacing its contract."
    return _tasks.amend_task(project, proposal_path, actor, apply, expected_amendment, ports=_task_ports())


def replan_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    reason: str,
    apply: bool,
    allow_intent_change: bool = False,
    expected_version: int | dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _pyramid_plan_commands.replan_project(project, plan_path, actor, reason, apply, allow_intent_change, expected_version, ports=_plan_ports())


def reopen_node(
    project: str | Path,
    nid: str,
    actor: str,
    reason: str,
    evidence_path: str | Path | None = None,
    expected_version: int | dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _tasks.reopen_node(project, nid, actor, reason, evidence_path, expected_version, ports=_task_ports())


def close_project(
    project: str | Path,
    actor: str,
    expected_version: int | dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _pyramid_plan_commands.close_project(project, actor, expected_version, ports=_plan_ports())


def _archive_identifier(plan: dict[str, Any], state: dict[str, Any]) -> str:
    return _pyramid_plan_bundle._archive_identifier(plan, state, ports=_plan_ports())


def archive_project(
    project: str | Path,
    actor: str,
    reason: str,
    expected_version: int | dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _pyramid_plan_lifecycle.archive_project(project, actor, reason, expected_version, ports=_plan_ports())


def _initialize_current(
    paths: dict[str, Path],
    plan: dict[str, Any],
    actor: str,
    payload: dict[str, Any],
    *,
    mode: str = "greenfield",
    baseline: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return _pyramid_plan_bundle._initialize_current(paths, plan, actor, payload, mode=mode, baseline=baseline, ports=_plan_ports())


def reset_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    reason: str,
    expected_version: int | dict[str, Any] | None = None,
    transition_approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _pyramid_plan_lifecycle.reset_project(project, plan_path, actor, reason, expected_version, transition_approval, ports=_plan_ports())


def _new_intent_material(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    reason: str,
    *,
    mode: str,
    expected_version: int | dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    return _pyramid_plan_lifecycle._new_intent_material(project, plan_path, actor, reason, mode=mode, expected_version=expected_version, ports=_plan_ports())


def new_intent_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    reason: str,
    *,
    mode: str = "auto",
    apply: bool = False,
    approved_by: str | None = None,
    approval_reference: str | None = None,
    approved_new_intent_sha256: str | None = None,
    expected_version: int | dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _pyramid_plan_lifecycle.new_intent_project(project, plan_path, actor, reason, mode=mode, apply=apply, approved_by=approved_by, approval_reference=approval_reference, approved_new_intent_sha256=approved_new_intent_sha256, expected_version=expected_version, ports=_plan_ports())


def restore_project(
    project: str | Path,
    archive_reference: str,
    actor: str,
    reason: str,
    expected_version: int | dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _pyramid_plan_lifecycle.restore_project(project, archive_reference, actor, reason, expected_version, ports=_plan_ports())


def clean_project(project: str | Path) -> dict[str, Any]:
    return _pyramid_plan_lifecycle.clean_project(project, ports=_plan_ports())


def inspect_history(
    project: str | Path,
    *,
    intent: str | None = None,
    path: str | None = None,
    commit: str | None = None,
    replay: str | None = None,
) -> dict[str, Any]:
    return _pyramid_queries.inspect_history(project, intent=intent, path=path, commit=commit, replay=replay)


def inspect_history_health(project: str | Path) -> dict[str, Any]:
    return _pyramid_queries.inspect_history_health(project)


def repair_history(project: str | Path) -> dict[str, Any]:
    return _pyramid_history_commands.repair_history(project, ports=_query_ports())


def bind_history_commit(
    project: str | Path,
    chronicle: str,
    actor: str,
) -> dict[str, Any]:
    return _pyramid_history_commands.bind_history_commit(project, chronicle, actor, ports=_query_ports())


def inspect_lifecycle(project: str | Path) -> dict[str, Any]:
    return _pyramid_project_queries.inspect_lifecycle(project, read_project=load_project)


def inspect_changes(
    project: str | Path,
    from_version: int,
    to_version: int | None = None,
    *,
    detail: bool = False,
) -> dict[str, Any]:
    return _pyramid_queries.inspect_changes(project, from_version, to_version, detail=detail, ports=_query_ports())


def inspect_project(
    project: str | Path,
    *,
    summary: bool = False,
    ready: bool = False,
    blocked: bool = False,
    pending_audits: bool = False,
    paused: bool = False,
    assurance_view: bool = False,
    assurance_summary_view: bool = False,
    assurance_detail: bool = False,
    parallel_ready: bool = False,
    max_agents: int = 4,
    audit_readiness: str | None = None,
    harness: str | None = None,
    footprint: bool = False,
    footprint_detail: bool = False,
    footprint_limit: int = 10000,
    nid: str | None = None,
) -> dict[str, Any]:
    return _pyramid_queries.inspect_project(project, summary=summary, ready=ready, blocked=blocked, pending_audits=pending_audits, paused=paused, assurance_view=assurance_view, assurance_summary_view=assurance_summary_view, assurance_detail=assurance_detail, parallel_ready=parallel_ready, max_agents=max_agents, audit_readiness=audit_readiness, harness=harness, footprint=footprint, footprint_detail=footprint_detail, footprint_limit=footprint_limit, nid=nid, ports=_query_ports())
