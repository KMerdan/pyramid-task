"""P3B plan_bundle boundary; no facade imports.

Existing control flow and canonical/history publication protocol are retained.
"""
from __future__ import annotations
from datetime import timezone
from pathlib import Path
from pyramid_assurance_contracts import PROJECT_FORMAT_VERSION
from pyramid_assurance import default_assurance
from pyramid_assurance import default_baseline
from pyramid_assurance import default_project_manifest
from pyramid_assurance_io import detect_repository_mode
from pyramid_assurance_contracts import validate_assurance
from pyramid_assurance_contracts import validate_baseline
from pyramid_errors import PyramidError
from pyramid_files import load_json
from pyramid_files import write_json
from pyramid_history import HistoryError
from pyramid_history import ensure_intent_start
from pyramid_project_queries import list_archives
from pyramid_projection import slugify
from pyramid_state import SCHEMA_VERSION
from pyramid_state import default_lifecycle
from pyramid_storage import _persist_event
from typing import Any
import copy
import shutil

from dataclasses import dataclass
from typing import Callable
from pyramid_files import utc_now, _event_id, parse_time
from pyramid_storage import load_project, commit_event
from pyramid_publication import compile_project, _compile_project_locked
from pyramid_state import initial_node_state as initial_values, invalidate_dependent_claims as invalidate_values
from pyramid_project_queries import inspect_lifecycle, validate_project, intent_transition_route
from datetime import datetime

@dataclass(frozen=True)
class PlanPorts:
    read_project: Callable
    compile_project: Callable
    compile_locked: Callable
    clock: Callable
    date_type: type
    commit: Callable
    event_id: Callable
    invalidate_claims: Callable
    lifecycle_query: Callable
    validate_query: Callable
    initial_state: Callable
    parse_time: Callable
    transition_route: Callable

def _initial_state(node, timestamp=None):
    return initial_values(node, timestamp=timestamp or utc_now())

def _invalidate_claims(plan, state, origin, reason):
    return invalidate_values(plan, state, origin, reason, timestamp=utc_now())

def default_ports():
    return PlanPorts(load_project,compile_project,_compile_project_locked,utc_now,datetime,
                     commit_event,_event_id,_invalidate_claims,inspect_lifecycle,validate_project,
                     _initial_state,parse_time,intent_transition_route)


def _prepare_new_project_bundle(
    paths: dict[str, Path],
    plan: dict[str, Any],
    actor: str,
    mode: str,
    baseline_path: str | Path | None,
    assurance_path: str | Path | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    selected_mode = detect_repository_mode(paths["root"]) if mode == "auto" else mode
    if selected_mode not in {"greenfield", "brownfield"}:
        raise PyramidError("mode must be auto, greenfield, or brownfield")
    manifest = default_project_manifest(plan_id=plan["plan_id"], mode=selected_mode, actor=actor)
    if selected_mode == "greenfield":
        if baseline_path or assurance_path:
            raise PyramidError("greenfield creation cannot accept baseline or assurance files")
        return manifest, None, None
    baseline = (
        load_json(Path(baseline_path).expanduser().resolve())
        if baseline_path
        else default_baseline(actor=actor)
    )
    baseline_errors = validate_baseline(baseline)
    if baseline_errors:
        raise PyramidError("Candidate baseline is invalid:\n- " + "\n- ".join(baseline_errors))
    assurance = (
        load_json(Path(assurance_path).expanduser().resolve())
        if assurance_path
        else default_assurance(plan_id=plan["plan_id"], baseline=baseline, actor=actor)
    )
    assurance_errors = validate_assurance(assurance, plan=plan, baseline=baseline)
    if assurance_errors:
        raise PyramidError("Candidate assurance is invalid:\n- " + "\n- ".join(assurance_errors))
    return manifest, baseline, assurance


def _archive_identifier(plan: dict[str, Any], state: dict[str, Any], *, ports: PlanPorts | None = None) -> str:
    ports = ports or default_ports()
    stamp = ports.date_type.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{slugify(plan['plan_id']).upper()}-R{plan['revision']}-G{state['graph_version'] + 1}-{stamp}"


def _copy_current_snapshot(paths: dict[str, Path], destination: Path, manifest: dict[str, Any]) -> None:
    if destination.exists():
        raise PyramidError(f"Archive already exists: {destination}")
    archive_meta = destination / ".pyramid"
    archive_docs = destination / "docs" / "tasks"
    archive_meta.mkdir(parents=True, exist_ok=False)
    for key in ("plan", "state", "project", "head", "baseline", "assurance", "graph", "ready"):
        source = paths[key]
        if source.exists():
            shutil.copy2(source, archive_meta / source.name)
    for key in ("events", "handoffs", "reports", "dossiers", "history"):
        source = paths[key]
        if source.exists():
            shutil.copytree(source, archive_meta / source.name)
    if paths["docs"].exists():
        archive_docs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(paths["docs"], archive_docs)
    write_json(destination / "manifest.json", manifest)


def _purge_current(
    paths: dict[str, Path],
    *,
    preserve_baseline: bool = False,
    preserve_dossiers: bool = False,
) -> None:
    directory_keys = ["events", "handoffs", "reports", "docs"]
    if not preserve_dossiers:
        directory_keys.append("dossiers")
    for key in directory_keys:
        target = paths[key]
        if target.exists():
            shutil.rmtree(target)
    file_keys = ["plan", "state", "project", "head", "assurance", "graph", "ready", "html"]
    if not preserve_baseline:
        file_keys.append("baseline")
    for key in file_keys:
        target = paths[key]
        if target.exists():
            target.unlink()


def _initialize_current(
    paths: dict[str, Path],
    plan: dict[str, Any],
    actor: str,
    payload: dict[str, Any],
    *,
    mode: str = "greenfield",
    baseline: dict[str, Any] | None = None,
    ports: PlanPorts | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ports = ports or default_ports()
    timestamp = ports.clock()
    state = {
        "schema_version": SCHEMA_VERSION,
        "graph_version": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
        "lifecycle": default_lifecycle(),
        "nodes": {node["id"]: ports.initial_state(node, timestamp) for node in plan["nodes"]},
    }
    write_json(paths["plan"], plan)
    manifest = default_project_manifest(plan_id=plan["plan_id"], mode=mode, actor=actor, created_at=timestamp)
    write_json(paths["project"], manifest)
    if mode == "brownfield":
        next_baseline = copy.deepcopy(baseline) if baseline is not None else default_baseline(actor=actor)
        next_assurance = default_assurance(
            plan_id=plan["plan_id"], baseline=next_baseline, actor=actor
        )
        write_json(paths["baseline"], next_baseline)
        write_json(paths["assurance"], next_assurance)
    event = {
        "schema": "pyramid-event-v1",
        "id": ports.event_id(),
        "at": timestamp,
        "graph_version": 1,
        "actor": actor,
        "type": "plan.created",
        "node": plan["intent"]["id"],
        "before": None,
        "after": {"plan_id": plan["plan_id"], "revision": plan["revision"]},
        "payload": {**payload, "mode": mode, "project_format_version": PROJECT_FORMAT_VERSION},
    }
    _persist_event(paths, plan, state, event)
    try:
        ensure_intent_start(
            paths["meta"],
            paths["root"],
            plan,
            state,
            actor,
            transition=payload,
        )
    except HistoryError as exc:
        raise PyramidError(str(exc)) from exc
    return state, event


def _resolve_archive(project: str | Path, reference: str) -> tuple[Path, dict[str, Any]]:
    matches = [item for item in list_archives(project) if item.get("archive_id") == reference or item.get("plan_id") == reference]
    if not matches:
        raise PyramidError(f"Unknown archive or archived plan: {reference}")
    matches.sort(key=lambda item: item.get("archived_at") or "", reverse=True)
    selected = matches[0]
    return Path(selected["path"]), selected
