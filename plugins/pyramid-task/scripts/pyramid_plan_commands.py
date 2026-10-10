"""P3B plan_commands boundary; no facade imports.

Existing control flow and canonical/history publication protocol are retained.
"""
from __future__ import annotations
from pathlib import Path
from pyramid_assurance_contracts import PROJECT_FORMAT_VERSION
from pyramid_change_io import _invalidate_assurance_for_change
from pyramid_errors import PyramidError
from pyramid_files import load_json
from pyramid_files import project_lock
from pyramid_files import project_paths
from pyramid_files import write_json
from pyramid_graph import claim_relations
from pyramid_graph import node_map
from pyramid_history import HistoryError
from pyramid_history import ensure_intent_start
from pyramid_history import history_chronicles
from pyramid_history import history_contains_plan
from pyramid_history import history_validation_errors
from pyramid_history import record_intent_chronicle
from pyramid_plan_bundle import PlanPorts, default_ports
from pyramid_plan_bundle import _prepare_new_project_bundle
from pyramid_projection import _build_change_dossier
from pyramid_projection import _completion_report
from pyramid_projection import _dossier_markdown
from pyramid_projection import _report_markdown
from pyramid_projection import slugify
from pyramid_projection import task_packet
from pyramid_proof_io import _proof_errors
from pyramid_state import SCHEMA_VERSION
from pyramid_state import canonical_sha256
from pyramid_state import check_expected_version
from pyramid_state import clear_active_pause
from pyramid_state import completion_errors
from pyramid_state import context_identity
from pyramid_state import default_lifecycle
from pyramid_state import dependent_claims
from pyramid_state import lifecycle_state
from pyramid_state import lifecycle_status
from pyramid_state import require_active
from pyramid_storage import _persist_event
from pyramid_storage import implementation_frontier
from pyramid_storage import load_assurance_bundle
from pyramid_topology import _semantic_node
from pyramid_topology import prepare_expansion
from pyramid_topology import prepare_replan
from pyramid_validation import validate_plan
from pyramid_verification import contracts as verification_contracts
from pyramid_verification import replan_proof_bindings
from typing import Any
import copy


def create_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    force: bool = False,
    *,
    mode: str = "auto",
    baseline_path: str | Path | None = None,
    assurance_path: str | Path | None = None,
    ports: PlanPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    paths = project_paths(project)
    plan = load_json(Path(plan_path).expanduser().resolve())
    errors = validate_plan(plan)
    if errors:
        raise PyramidError("Candidate plan is invalid:\n- " + "\n- ".join(errors))
    manifest, baseline, assurance = _prepare_new_project_bundle(
        paths, plan, actor, mode, baseline_path, assurance_path
    )
    with project_lock(paths):
        if paths["plan"].exists():
            if force:
                raise PyramidError("Unsafe replacement is disabled; use reset so the current plan is archived first")
            raise PyramidError(f"A Pyramid Task project already exists at {paths['meta']}; use replan or reset instead")
        history_errors = history_validation_errors(paths["meta"])
        if history_errors:
            raise PyramidError("History validation failed:\n- " + "\n- ".join(history_errors))
        try:
            recorded_plan = history_contains_plan(paths["meta"], plan["plan_id"])
        except HistoryError as exc:
            raise PyramidError(str(exc)) from exc
        if recorded_plan:
            raise PyramidError(
                f"Plan ID {plan['plan_id']} already exists in immutable intent history; "
                "use a new plan_id or restore its archive"
            )
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
        write_json(paths["project"], manifest)
        if baseline is not None and assurance is not None:
            write_json(paths["baseline"], baseline)
            write_json(paths["assurance"], assurance)
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
            "payload": {"mode": manifest["mode"], "project_format_version": PROJECT_FORMAT_VERSION},
        }
        _persist_event(paths, plan, state, event)
        try:
            ensure_intent_start(paths["meta"], paths["root"], plan, state, actor)
        except HistoryError as exc:
            raise PyramidError(str(exc)) from exc
    compiled = ports.compile_project(project)
    return {
        "status": "created",
        "project": str(paths["root"]),
        "mode": manifest["mode"],
        "project_format_version": PROJECT_FORMAT_VERSION,
        "event": event,
        **compiled,
    }


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
    ports: PlanPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    proposal = load_json(Path(proposal_path).expanduser().resolve())
    proposal_hash = canonical_sha256(proposal)
    paths, plan, state = ports.read_project(project)
    check_expected_version(plan, state, expected_version)
    require_active(state, "expand a task")
    candidate, diff = prepare_expansion(plan, state, proposal)
    if not apply:
        return {
            "status": "preview",
            "graph_version": state["graph_version"],
            "context": context_identity(plan, state),
            "proposal_sha256": proposal_hash,
            "approval_required": True,
            "diff": diff,
        }
    if not approved_by or not approved_by.strip():
        raise PyramidError("Applying expansion requires --approved-by")
    if not approval_reference or not approval_reference.strip():
        raise PyramidError("Applying expansion requires --approval-reference")
    if not approved_proposal_sha256 or not approved_proposal_sha256.strip():
        raise PyramidError("Applying expansion requires --approved-proposal-sha256 from preview")
    if approved_proposal_sha256 != proposal_hash:
        raise PyramidError("Approved proposal hash does not match the current proposal; preview and approve again")
    with project_lock(paths):
        paths, current, state = ports.read_project(project)
        check_expected_version(current, state, expected_version)
        require_active(state, "expand a task")
        candidate, diff = prepare_expansion(current, state, proposal)
        target = proposal["target"]
        before = {
            "revision": current["revision"],
            "graph_version": state["graph_version"],
            "node": copy.deepcopy(node_map(current)[target]),
            "state": copy.deepcopy(state["nodes"][target]),
        }
        timestamp = ports.clock()
        parent_state = state["nodes"][target]
        parent_state.update(
            {
                "execution": "planned",
                "verification": "unverified",
                "health": "clear",
                "owner": None,
                "lease_expires_at": None,
                "work_origin": None,
                "blocker": None,
                "updated_at": timestamp,
            }
        )
        candidate_by_id = node_map(candidate)
        for nid in diff["added_nodes"]:
            state["nodes"][nid] = ports.initial_state(candidate_by_id[nid], timestamp)
        invalidated = ports.invalidate_claims(
            candidate,
            state,
            target,
            f"{target} was expanded; dependent verification must follow the approved subtree.",
        )
        stale_inspections = _invalidate_assurance_for_change(
            paths,
            candidate,
            {target, *diff["added_nodes"]},
            actor,
            f"Approved expansion of {target} changed assurance coverage and requires renewed impact review.",
        )
        write_json(paths["plan"], candidate)
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type="task.expanded",
            node=target,
            before=before,
            after={
                "revision": candidate["revision"],
                "node": copy.deepcopy(candidate_by_id[target]),
                "state": copy.deepcopy(parent_state),
                "added_nodes": diff["added_nodes"],
            },
            payload={
                "proposal": proposal,
                "proposal_sha256": proposal_hash,
                "approval": {
                    "approved_by": approved_by,
                    "reference": approval_reference,
                    "proposal_sha256": approved_proposal_sha256,
                },
                "diff": diff,
                "invalidated": invalidated,
                "stale_inspections": stale_inspections,
            },
        )
    compiled = ports.compile_project(project)
    paths, applied_plan, applied_state = ports.read_project(project)
    _, baseline, assurance = load_assurance_bundle(paths, applied_plan)
    return {
        "status": "applied",
        "event": event,
        "proposal_sha256": proposal_hash,
        "diff": diff,
        "invalidated": invalidated,
        "stale_inspections": stale_inspections,
        "parent": task_packet(
            applied_plan,
            applied_state,
            proposal["target"],
            baseline,
            assurance,
        ),
        **compiled,
    }


def replan_project(
    project: str | Path,
    plan_path: str | Path,
    actor: str,
    reason: str,
    apply: bool,
    allow_intent_change: bool = False,
    expected_version: int | dict[str, Any] | None = None,
    *,
    ports: PlanPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    candidate = load_json(Path(plan_path).expanduser().resolve())
    paths, old, state = ports.read_project(project)
    check_expected_version(old, state, expected_version)
    require_active(state, "replan")
    merged, diff = prepare_replan(old, candidate, allow_intent_change)
    if not apply:
        return {
            "status": "preview",
            "graph_version": state["graph_version"],
            "context": context_identity(old, state),
            "diff": diff,
        }
    with project_lock(paths):
        paths, current, state = ports.read_project(project)
        check_expected_version(current, state, expected_version)
        require_active(state, "replan")
        merged, diff = prepare_replan(current, candidate, allow_intent_change)
        before = {"revision": current["revision"], "graph_version": state["graph_version"]}
        current_nodes = node_map(current)
        merged_nodes = node_map(merged)
        proof_bindings = replan_proof_bindings(paths["root"], current, merged, state)
        timestamp = ports.clock()
        next_states: dict[str, Any] = {}
        changed_contracts = {
            nid for nid in merged_nodes if nid not in current_nodes
            or _semantic_node(current_nodes[nid]) != _semantic_node(merged_nodes[nid])
            or claim_relations(current, nid) != claim_relations(merged, nid)
        }
        if merged.get("schema_version") == 2:
            for nid, node in merged_nodes.items():
                if node["selection"] != "primary":
                    continue
                old_contracts = (verification_contracts(current, nid)
                                 if nid in current_nodes and current_nodes[nid]["selection"] == "primary" else [])
                if old_contracts != verification_contracts(merged, nid):
                    changed_contracts.add(nid)
        stale_claims = set(changed_contracts)
        for nid in changed_contracts:
            stale_claims.update(dependent_claims(current, nid))
            stale_claims.update(dependent_claims(merged, nid))
        for nid, node in merged_nodes.items():
            if nid not in state["nodes"]:
                next_states[nid] = ports.initial_state(node, timestamp)
                continue
            item = copy.deepcopy(state["nodes"][nid])
            if node["selection"] == "superseded":
                item["execution"] = "superseded"
                item["owner"] = None
                item["lease_expires_at"] = None
                item["work_origin"] = None
                clear_active_pause(item)
                item["health"] = "clear"
            elif nid in stale_claims:
                if item["execution"] == "working" and nid in changed_contracts:
                    item["execution"] = "planned"
                    item["owner"] = None
                    item["lease_expires_at"] = None
                item["verification"] = "pending" if item["execution"] == "implemented" else "unverified"
                item["health"] = "at-risk"
                item["blocker"] = "Replan changed this claim, its proof contract, or a prerequisite; re-audit required."
            item["updated_at"] = timestamp
            next_states[nid] = item
        state["nodes"] = next_states
        if proof_bindings:
            state["proof_contract_bindings"] = proof_bindings
        write_json(paths["plan"], merged)
        affected_tasks = set(diff["added_nodes"]) | set(diff["changed_nodes"]) | set(diff["superseded_nodes"])
        stale_inspections = _invalidate_assurance_for_change(
            paths,
            merged,
            affected_tasks,
            actor,
            "Replan changed task contracts or graph relations; impact and inspection evidence require review.",
        )
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type="plan.replanned",
            node=merged["intent"]["id"],
            before=before,
            after={"revision": merged["revision"]},
            payload={
                "reason": reason,
                "diff": diff,
                "invalidated_claims": sorted(stale_claims),
                "stale_inspections": stale_inspections,
                "proof_contract_bindings": {
                    rid: binding for rid, binding in proof_bindings.items()
                    if binding.get("to_revision") == merged["revision"]
                },
            },
        )
    compiled = ports.compile_project(project)
    return {
        "status": "applied",
        "event": event,
        "diff": diff,
        "stale_inspections": stale_inspections,
        **compiled,
    }


def close_project(
    project: str | Path,
    actor: str,
    expected_version: int | dict[str, Any] | None = None,
    *,
    ports: PlanPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    paths = project_paths(project)
    with project_lock(paths):
        paths, plan, state = ports.read_project(project)
        check_expected_version(plan, state, expected_version)
        status = lifecycle_status(state)
        if status == "archived":
            raise PyramidError("Cannot close an archived plan; restore it first")
        if status == "completed":
            existing = [
                item
                for item in history_chronicles(paths["meta"])
                if item.get("plan_id") == plan["plan_id"]
                and item.get("outcome") == "completed"
            ]
            if existing:
                chronicle = existing[-1]
            else:
                lifecycle = lifecycle_state(state)
                report_reference = lifecycle.get("completion_report")
                dossier_reference = lifecycle.get("change_dossier")
                try:
                    chronicle = record_intent_chronicle(
                        paths["meta"],
                        paths["root"],
                        plan,
                        state,
                        actor,
                        outcome="completed",
                        reason="Backfilled from an existing completed lifecycle.",
                        report_path=(paths["root"] / report_reference) if report_reference else None,
                        dossier_path=(paths["root"] / dossier_reference) if dossier_reference else None,
                        closing_event={
                            "id": "HISTORY-BACKFILL",
                            "type": "history.backfilled",
                            "at": lifecycle.get("completed_at"),
                        },
                    )
                except HistoryError as exc:
                    raise PyramidError(str(exc)) from exc
            compiled = ports.compile_locked(project)
            return {
                "status": "completed",
                "graph_version": state["graph_version"],
                "report": lifecycle_state(state).get("completion_report"),
                "chronicle": chronicle["chronicle_id"],
                "already_completed": True,
                **compiled,
            }
        manifest, baseline, assurance = load_assurance_bundle(paths, plan)
        errors = completion_errors(
            plan,
            state,
            baseline,
            assurance,
            implementation_frontier(paths),
        )
        errors.extend(_proof_errors(paths, plan, state))
        if errors:
            raise PyramidError("Plan cannot close:\n- " + "\n- ".join(errors))
        completed_at = ports.clock()
        report = _completion_report(plan, state, actor, completed_at)
        report_id = f"FINAL-{slugify(plan['plan_id']).upper()}-R{plan['revision']}-G{state['graph_version'] + 1}"
        report_json = paths["reports"] / f"{report_id}.json"
        report_markdown = paths["reports"] / f"{report_id}.md"
        dossier: dict[str, Any] | None = None
        baseline_after: dict[str, Any] | None = None
        dossier_json: Path | None = None
        dossier_markdown: Path | None = None
        if manifest and manifest.get("mode") == "brownfield" and baseline is not None and assurance is not None:
            dossier_id = f"DOSSIER-{slugify(plan['plan_id']).upper()}-R{plan['revision']}-G{state['graph_version'] + 1}"
            dossier_json = paths["dossiers"] / f"{dossier_id}.json"
            dossier_markdown = paths["dossiers"] / f"{dossier_id}.md"
            dossier, baseline_after = _build_change_dossier(
                plan, state, baseline, assurance, actor, completed_at, dossier_id
            )
            report["change_dossier"] = str(dossier_json.relative_to(paths["root"]))
        lifecycle = lifecycle_state(state)
        before = copy.deepcopy(lifecycle)
        lifecycle.update(
            {
                "status": "completed",
                "completed_at": completed_at,
                "completed_by": actor,
                "completion_report": str(report_json.relative_to(paths["root"])),
                "change_dossier": str(dossier_json.relative_to(paths["root"])) if dossier_json else None,
            }
        )
        write_json(report_json, report)
        report_markdown.parent.mkdir(parents=True, exist_ok=True)
        report_markdown.write_text(_report_markdown(report), encoding="utf-8")
        if dossier is not None and dossier_json is not None and dossier_markdown is not None and baseline_after is not None and assurance is not None:
            write_json(dossier_json, dossier)
            dossier_markdown.parent.mkdir(parents=True, exist_ok=True)
            dossier_markdown.write_text(_dossier_markdown(dossier), encoding="utf-8")
            next_assurance = copy.deepcopy(assurance)
            next_assurance["baseline_id"] = baseline_after["baseline_id"]
            next_assurance["baseline_revision"] = baseline_after["revision"]
            next_assurance["status"] = "passed"
            next_assurance["updated_at"] = completed_at
            next_assurance["updated_by"] = actor
            next_assurance["stale_reasons"] = []
            write_json(paths["baseline"], baseline_after)
            write_json(paths["assurance"], next_assurance)
        event = ports.commit(
            paths,
            state,
            actor=actor,
            event_type="plan.completed",
            node=plan["intent"]["id"],
            before=before,
            after=copy.deepcopy(lifecycle),
            payload={
                "report_json": str(report_json.relative_to(paths["root"])),
                "report_markdown": str(report_markdown.relative_to(paths["root"])),
                "change_dossier_json": str(dossier_json.relative_to(paths["root"])) if dossier_json else None,
                "change_dossier_markdown": str(dossier_markdown.relative_to(paths["root"])) if dossier_markdown else None,
            },
        )
        try:
            chronicle = record_intent_chronicle(
                paths["meta"],
                paths["root"],
                plan,
                state,
                actor,
                outcome="completed",
                reason=None,
                report_path=report_json,
                dossier_path=dossier_json,
                closing_event=event,
            )
        except HistoryError as exc:
            raise PyramidError(str(exc)) from exc
    compiled = ports.compile_project(project)
    return {
        "status": "completed",
        "event": event,
        "report": str(report_json),
        "report_markdown": str(report_markdown),
        "change_dossier": str(dossier_json) if dossier_json else None,
        "change_dossier_markdown": str(dossier_markdown) if dossier_markdown else None,
        "chronicle": chronicle["chronicle_id"],
        **compiled,
    }
