"""Query composition; optional scans occur only on explicit request."""
from __future__ import annotations
from pathlib import Path
from pyramid_assurance_io import artifact_footprint
from pyramid_assurance_rules import assurance_for_tasks
from pyramid_assurance_rules import assurance_summary
from pyramid_errors import PyramidError
from pyramid_files import load_json
from pyramid_files import project_lock
from pyramid_files import project_paths
from pyramid_graph import availability
from pyramid_graph import node_map
from pyramid_history import HistoryError
from pyramid_history import history_health
from pyramid_history import query_history
from pyramid_parallel import build_parallel_frontier
from pyramid_projection import task_packet
from pyramid_projection import task_summary
from pyramid_results import _audit_prerequisite_errors
from pyramid_state import _covered_assurance_tasks
from pyramid_state import audit_mutation_guard
from pyramid_state import completion_errors
from pyramid_state import context_identity
from pyramid_state import lifecycle_state
from pyramid_state import lifecycle_status
from pyramid_state import task_mutation_guard
from pyramid_storage import implementation_frontier
from pyramid_storage import load_assurance_bundle
from pyramid_verification import VerificationError
from pyramid_verification import query_harness
from typing import Any
import copy

from dataclasses import dataclass
from typing import Callable
from pyramid_storage import load_project
from pyramid_publication import compile_project
from pyramid_project_queries import validate_project
from pyramid_proof_io import _proof_errors, _audit_proof_dependencies
from pyramid_projection import graph_snapshot as project_snapshot, prepare_graph_nodes
from pyramid_files import utc_now

@dataclass(frozen=True)
class QueryPorts:
    read_project: Callable
    compile_project: Callable
    validate_project: Callable
    snapshot: Callable
    proof_errors: Callable
    audit_dependencies: Callable

def runtime_snapshot(plan, state, baseline=None, assurance=None, manifest=None, frontier=None, *, clock=utc_now):
    prepared = prepare_graph_nodes(plan, state, baseline, assurance, frontier)
    return project_snapshot(plan, state, baseline, assurance, manifest, frontier,
                            generated_at=clock(), prepared=prepared)

def default_ports():
    return QueryPorts(load_project,compile_project,validate_project,runtime_snapshot,
                      _proof_errors,_audit_proof_dependencies)


def inspect_history(
    project: str | Path,
    *,
    intent: str | None = None,
    path: str | None = None,
    commit: str | None = None,
    replay: str | None = None,
) -> dict[str, Any]:
    paths = project_paths(project)
    with project_lock(paths):
        current_plan_id = (
            load_json(paths["plan"]).get("plan_id") if paths["plan"].exists() else None
        )
        try:
            return query_history(
                paths["meta"],
                current_plan_id=current_plan_id,
                intent=intent,
                path=path,
                commit=commit,
                replay=replay,
            )
        except HistoryError as exc:
            raise PyramidError(str(exc)) from exc


def inspect_history_health(project: str | Path) -> dict[str, Any]:
    paths = project_paths(project)
    with project_lock(paths):
        return history_health(paths["meta"])


def inspect_changes(
    project: str | Path,
    from_version: int,
    to_version: int | None = None,
    *,
    detail: bool = False,
    ports: QueryPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    if from_version < 0:
        raise PyramidError("from-version must be zero or greater")
    paths, plan, state = ports.read_project(project)
    upper = state["graph_version"] if to_version is None else to_version
    if upper < from_version:
        raise PyramidError("to-version must be greater than or equal to from-version")
    if upper > state["graph_version"]:
        raise PyramidError(
            f"to-version {upper} exceeds current graph version {state['graph_version']}"
        )
    changes = []
    for event_path in paths["events"].glob("*.json"):
        event = load_json(event_path)
        version = event.get("graph_version")
        if not isinstance(version, int) or not from_version < version <= upper:
            continue
        before = event.get("before")
        after = event.get("after")
        changed_fields = []
        if isinstance(before, dict) and isinstance(after, dict):
            changed_fields = sorted(
                key for key in set(before) | set(after) if before.get(key) != after.get(key)
            )
        elif before != after:
            changed_fields = ["value"]
        item = {
            "graph_version": version,
            "context_id": event.get("context_id"),
            "event": event.get("id"),
            "at": event.get("at"),
            "actor": event.get("actor"),
            "type": event.get("type"),
            "node": event.get("node"),
            "changed_fields": changed_fields,
            "payload_fields": sorted(event.get("payload", {})),
        }
        if detail:
            item.update(
                {
                    "before": copy.deepcopy(before),
                    "after": copy.deepcopy(after),
                    "payload": copy.deepcopy(event.get("payload", {})),
                }
            )
        changes.append(item)
    changes.sort(key=lambda item: (item["graph_version"], item["at"] or "", item["event"] or ""))
    return {
        "schema": "pyramid-changes-v1",
        "plan_id": plan["plan_id"],
        "from_version": from_version,
        "to_version": upper,
        "context": context_identity(plan, state),
        "changes": changes,
    }


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
    ports: QueryPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    if not footprint and (footprint_detail or footprint_limit != 10000):
        raise PyramidError('footprint detail/limit require --footprint')
    paths, plan, state = ports.read_project(project)
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if footprint:
        try:
            return {**artifact_footprint(paths['root'], plan, state, baseline,
                                        detail=footprint_detail, limit=footprint_limit),
                    'context': context_identity(plan, state)}
        except (ValueError, OSError) as exc:
            raise PyramidError(str(exc)) from exc
    frontier = implementation_frontier(paths)
    snapshot = ports.snapshot(
        plan, state, baseline, assurance, manifest, frontier
    )
    context = context_identity(plan, state)
    if harness:
        try:
            return {**query_harness(paths["root"], plan, state, harness), "context": context}
        except (VerificationError, OSError) as exc:
            raise PyramidError(str(exc)) from exc
    if assurance_view or assurance_summary_view or assurance_detail:
        if baseline is None or assurance is None:
            return {
                "schema": "pyramid-assurance-query-v1",
                "mode": manifest.get("mode") if manifest else "legacy",
                "context": context,
                "assurance": None,
                "message": "This project has no brownfield assurance bundle.",
            }
        result = {
            "schema": "pyramid-assurance-query-v1",
            "mode": manifest.get("mode") if manifest else "brownfield",
            "graph_version": state["graph_version"],
            "context": context,
            "summary": assurance_summary(
                baseline,
                assurance,
                implementation_frontier=frontier,
            ),
        }
        if assurance_view or assurance_detail:
            result["baseline"] = copy.deepcopy(baseline)
            result["assurance"] = copy.deepcopy(assurance)
        return result
    if parallel_ready:
        if max_agents < 1:
            raise PyramidError("max-agents must be positive")
        candidates = [
            node["id"]
            for node in plan["nodes"]
            if availability(plan, state, node) in {"ready", "needs-rework"}
        ]
        task_guards = {
            task: task_mutation_guard(plan, state, task, baseline, assurance)
            for task in candidates
        }
        return build_parallel_frontier(
            plan,
            candidates,
            task_guards=task_guards,
            context=context,
            graph_version=state["graph_version"],
            max_agents=max_agents,
            assurance=assurance,
        )
    if audit_readiness:
        nodes = node_map(plan)
        if audit_readiness not in nodes:
            raise PyramidError(f"Unknown node: {audit_readiness}")
        node = nodes[audit_readiness]
        covered_tasks = _covered_assurance_tasks(plan, node)
        blockers = _audit_prerequisite_errors(plan, state, node)
        blockers.extend(ports.audit_dependencies(paths, plan, state, node))
        blockers.extend(ports.proof_errors(paths, plan, state, {audit_readiness}))
        coverage = None
        if baseline is not None and assurance is not None:
            coverage = assurance_for_tasks(
                baseline,
                assurance,
                covered_tasks,
                implementation_frontier=frontier,
            )
            blockers.extend(coverage["blockers"])
        return {
            "schema": "pyramid-audit-readiness-v1",
            "target": audit_readiness,
            "graph_version": state["graph_version"],
            "context": context,
            "audit_guard": audit_mutation_guard(
                plan,
                state,
                audit_readiness,
                baseline,
                assurance,
                frontier,
            ),
            "covered_task_ids": sorted(covered_tasks),
            "ready": not blockers,
            "blockers": sorted(set(blockers)),
            "assurance": coverage,
            "harness_query": f"inspect --harness {audit_readiness}" if plan.get("schema_version") == 2 else None,
            "refresh_inspection_ids": sorted(
                inspection.get("id")
                for inspection in (assurance or {}).get("inspections", [])
                if inspection.get("id")
                and any(
                    f"Inspection {inspection.get('id')} " in blocker
                    or f"inspection {inspection.get('id')} " in blocker
                    for blocker in blockers
                )
            ),
        }
    if nid:
        return task_packet(plan, state, nid, baseline, assurance, frontier)
    if ready:
        tasks = [
            task_summary(plan, state, node["id"], baseline, assurance, frontier)
            for node in plan["nodes"]
            if availability(plan, state, node) in {"ready", "needs-rework"}
        ]
        tasks.sort(key=lambda item: (item["wave"], item["level"], item["task"]))
        return {
            "schema": "pyramid-query-v1",
            "query": "ready",
            "graph_version": state["graph_version"],
            "context": context,
            "tasks": tasks,
        }
    if paused:
        nodes = [
            task_summary(plan, state, node["id"], baseline, assurance, frontier)
            for node in plan["nodes"]
            if state["nodes"][node["id"]].get("execution") == "paused"
        ]
        return {
            "schema": "pyramid-query-v1",
            "query": "paused",
            "graph_version": state["graph_version"],
            "context": context,
            "nodes": nodes,
        }
    if blocked:
        nodes = [
            task_summary(plan, state, node["id"], baseline, assurance, frontier)
            for node in plan["nodes"]
            if availability(plan, state, node) in {"blocked", "locked"}
        ]
        return {
            "schema": "pyramid-query-v1",
            "query": "blocked",
            "graph_version": state["graph_version"],
            "context": context,
            "nodes": nodes,
        }
    if pending_audits:
        nodes = [
            task_summary(plan, state, node["id"], baseline, assurance, frontier)
            for node in plan["nodes"]
            if node["kind"] == "audit"
            and state["nodes"][node["id"]]["verification"] != "passed"
            and node["selection"] == "primary"
        ]
        return {
            "schema": "pyramid-query-v1",
            "query": "pending-audits",
            "graph_version": state["graph_version"],
            "context": context,
            "nodes": nodes,
        }
    return {
        "schema": "pyramid-summary-v1",
        "plan_id": plan["plan_id"],
        "title": plan["title"],
        "revision": plan["revision"],
        "graph_version": state["graph_version"],
        "context": context,
        "lifecycle": copy.deepcopy(lifecycle_state(state)),
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
        "closure_ready": lifecycle_status(state) == "active"
        and not completion_errors(plan, state, baseline, assurance, frontier)
        and not ports.proof_errors(paths, plan, state),
        "verification_mode": "candidate-bound" if plan.get("schema_version") == 2 else "legacy-unbound",
        "intent": plan["intent"],
        "summary": snapshot["summary"],
        "ready": [node["id"] for node in snapshot["nodes"] if node["availability"] in {"ready", "needs-rework"}],
        "working": [node["id"] for node in snapshot["nodes"] if node["availability"] == "working"],
        "paused": [node["id"] for node in snapshot["nodes"] if node["availability"] == "paused"],
        "blocked": [node["id"] for node in snapshot["nodes"] if node["availability"] in {"blocked", "locked"}],
        "pending_audits": [node["id"] for node in snapshot["nodes"] if node["kind"] == "audit" and node["state"]["verification"] != "passed" and node["selection"] == "primary"],
    }
