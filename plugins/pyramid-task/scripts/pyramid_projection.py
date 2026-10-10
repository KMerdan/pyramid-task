"""Value projections for callers, graph, Markdown and closing reports.

Inputs are supplied plan/state/assurance values and explicit generated_at.
No project I/O or current clock. Existing state defaulting by guard/lifecycle
rules is preserved; the publication layer remains responsible for file writes.
"""
from __future__ import annotations
import copy
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from pyramid_errors import PyramidError
from pyramid_graph import AUDIT_BLOCKING, EXECUTABLE_KINDS, availability, edges_from, edges_to, node_map, start_blockers
from pyramid_state import (_covered_assurance_tasks, audit_mutation_guard,
    completion_errors, context_identity, lifecycle_state, lifecycle_status, task_mutation_guard)
from pyramid_assurance_rules import asset_ids_for_file, assurance_for_tasks, assurance_summary
from pyramid_verification import contracts as verification_contracts, render_guide


def goal_trace(plan: dict[str, Any], start: str) -> list[str]:
    intent_id = plan["intent"]["id"]
    if start == intent_id:
        return [start]
    parents: dict[str, list[str]] = defaultdict(list)
    for edge in plan["edges"]:
        if edge["type"] == "contributes-to":
            parents[edge["from"]].append(edge["to"])
    queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
    visited = {start}
    while queue:
        current, path = queue.popleft()
        for parent in sorted(parents.get(current, [])):
            if parent == intent_id:
                return path + [parent]
            if parent not in visited:
                visited.add(parent)
                queue.append((parent, path + [parent]))
    return [start]


def task_packet(
    plan: dict[str, Any],
    state: dict[str, Any],
    nid: str,
    baseline: dict[str, Any] | None = None,
    assurance: dict[str, Any] | None = None,
    frontier: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    nodes = node_map(plan)
    if nid not in nodes:
        raise PyramidError(f"Unknown node: {nid}")
    node = nodes[nid]
    dependency_edges = edges_from(plan, nid, AUDIT_BLOCKING)
    dependencies = []
    for edge in dependency_edges:
        target = nodes[edge["to"]]
        target_state = state["nodes"][target["id"]]
        dependencies.append(
            {
                "id": target["id"],
                "title": target["title"],
                "type": edge["type"],
                "execution": target_state["execution"],
                "verification": target_state["verification"],
                "availability": availability(plan, state, target),
            }
        )
    gates = [edge["to"] for edge in edges_from(plan, nid, {"validated-by"})]
    item = state["nodes"][nid]
    packet = {
        "schema": "agent-task-v1",
        "task": nid,
        "graph_version": state["graph_version"],
        "context": context_identity(plan, state),
        "title": node["title"],
        "purpose": node["summary"],
        "kind": node["kind"],
        "level": node["level"],
        "wave": node["wave"],
        "workstream": node["workstream"],
        "selection": node["selection"],
        "availability": availability(plan, state, node),
        "execution": item["execution"],
        "verification": item["verification"],
        "health": item["health"],
        "blocker": item["blocker"],
        "goal_trace": goal_trace(plan, nid),
        "parents": [edge["to"] for edge in edges_from(plan, nid, {"contributes-to"})],
        "children": [edge["from"] for edge in edges_to(plan, nid, {"contributes-to"})],
        "dependencies": dependencies,
        "blocked_by": start_blockers(plan, state, node),
        "required_context": node["agent"]["required_context"],
        "allowed_write_scope": node["agent"]["allowed_write_scope"],
        "commands": node["agent"]["commands"],
        "deliverables": node["agent"]["deliverables"],
        "non_goals": node["agent"]["non_goals"],
        "acceptance_criteria": node["acceptance_criteria"],
        "required_evidence": node["required_evidence"],
        "audit_gates": gates,
        "owner": item["owner"],
        "lease_expires_at": item["lease_expires_at"],
        "pause": {
            "active_handoff_id": item.get("active_handoff_id"),
            "paused_at": item.get("paused_at"),
            "paused_by": item.get("paused_by"),
            "mode": item.get("pause_mode"),
            "resume_deadline": item.get("resume_deadline"),
        },
        "completion_report_schema": "agent-result-v1",
        "mutation_guards": {
            "task": task_mutation_guard(plan, state, nid, baseline, assurance),
            "audit": audit_mutation_guard(
                plan,
                state,
                nid,
                baseline,
                assurance,
                frontier or {},
            ),
        },
    }
    packet["mutation_guard"] = packet["mutation_guards"]["task"]
    if plan.get("schema_version") == 2 and node["selection"] == "primary":
        packet["required_evidence"] = [
            {key: value for key, value in evidence.items() if key != "verification"}
            for evidence in node["required_evidence"]
        ]
        packet["harness"] = {
            "contracts": verification_contracts(plan, nid),
            "capture": f"inspect --harness {nid}",
            "guide": "docs/tasks/DEVELOPMENT_HARNESS.md",
            "instruction": "Reuse existing checks; implement only missing capability. Capture candidate before checks; view required screenshots. Submit proofs or reuse a current run. A mutation guard is not a source fingerprint.",
        }
    if baseline is not None and assurance is not None:
        packet["assurance"] = assurance_for_tasks(
            baseline,
            assurance,
            _covered_assurance_tasks(plan, node),
            implementation_frontier=frontier,
        )
    return packet


def task_summary(
    plan: dict[str, Any],
    state: dict[str, Any],
    nid: str,
    baseline: dict[str, Any] | None = None,
    assurance: dict[str, Any] | None = None,
    frontier: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    node = node_map(plan)[nid]
    item = state["nodes"][nid]
    summary = {
        "id": nid,
        "task": nid,
        "title": node["title"],
        "kind": node["kind"],
        "level": node["level"],
        "wave": node["wave"],
        "workstream": node["workstream"],
        "availability": availability(plan, state, node),
        "execution": item["execution"],
        "verification": item["verification"],
        "health": item["health"],
        "owner": item.get("owner"),
        "blocker": item.get("blocker"),
        "blocked_by": start_blockers(plan, state, node),
        "handoff_id": item.get("active_handoff_id"),
        "mutation_guards": {
            "task": task_mutation_guard(plan, state, nid, baseline, assurance),
            "audit": audit_mutation_guard(
                plan,
                state,
                nid,
                baseline,
                assurance,
                frontier or {},
            ),
        },
    }
    summary["mutation_guard"] = summary["mutation_guards"]["task"]
    if baseline is not None and assurance is not None:
        coverage = assurance_for_tasks(
            baseline,
            assurance,
            _covered_assurance_tasks(plan, node),
            implementation_frontier=frontier,
        )
        summary["assurance"] = {
            "status": coverage["status"],
            "blockers": coverage["blockers"],
        }
    return summary


def prepare_graph_nodes(plan, state, baseline=None, assurance=None, frontier=None):
    """Prepare exactly the graph values evaluated before the legacy clock."""
    nodes = node_map(plan)
    enriched = []
    counts: dict[str, int] = defaultdict(int)
    for node in sorted(plan["nodes"], key=lambda item: (item["level"], item["wave"], item["id"])):
        nid = node["id"]
        item = copy.deepcopy(node)
        item["state"] = copy.deepcopy(state["nodes"][nid])
        item["availability"] = availability(plan, state, node)
        counts[item["availability"]] += 1
        item["blocked_by"] = start_blockers(plan, state, node)
        item["goal_trace"] = goal_trace(plan, nid)
        item["parents"] = [edge["to"] for edge in edges_from(plan, nid, {"contributes-to"})]
        item["children"] = [edge["from"] for edge in edges_to(plan, nid, {"contributes-to"})]
        item["dependencies"] = [
            {"id": edge["to"], "type": edge["type"], "verification": state["nodes"][edge["to"]]["verification"]}
            for edge in edges_from(plan, nid, AUDIT_BLOCKING)
        ]
        item["audit_gates"] = [edge["to"] for edge in edges_from(plan, nid, {"validated-by"})]
        item["evidence"] = [entry["id"] for entry in plan["evidence"] if nid in entry.get("supports", [])]
        if baseline is not None and assurance is not None:
            item["assurance"] = assurance_for_tasks(
                baseline,
                assurance,
                _covered_assurance_tasks(plan, node),
                implementation_frontier=frontier,
            )
        enriched.append(item)
    primary = [node for node in enriched if node["selection"] == "primary"]
    verified = sum(node["state"]["verification"] == "passed" for node in primary)
    return enriched, counts, primary, verified


def graph_snapshot(
    plan: dict[str, Any],
    state: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    assurance: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    frontier: dict[str, dict[str, Any]] | None = None,
    *,
    generated_at: str,
    prepared: tuple | None = None,
) -> dict[str, Any]:
    enriched, counts, primary, verified = (prepared if prepared is not None else
        prepare_graph_nodes(plan, state, baseline, assurance, frontier))
    snapshot = {
        "schema": "pyramid-graph-v1",
        "generated_at": generated_at,
        "graph_version": state["graph_version"],
        "context": context_identity(plan, state),
        "plan_id": plan["plan_id"],
        "title": plan["title"],
        "revision": plan["revision"],
        "intent": plan["intent"],
        "verification_scope": "recorded-candidate" if plan.get("schema_version") == 2 else "legacy-unbound",
        "lifecycle": copy.deepcopy(lifecycle_state(state)),
        "summary": {
            "primary_nodes": len(primary),
            "verified_primary_nodes": verified,
            "closure_ready": not completion_errors(
                plan, state, baseline, assurance, frontier
            ),
            "availability": dict(sorted(counts.items())),
        },
        "nodes": enriched,
        "edges": copy.deepcopy(plan["edges"]),
        "evidence": copy.deepcopy(plan["evidence"]),
        "decisions": copy.deepcopy(plan["decisions"]),
    }
    snapshot["project"] = copy.deepcopy(manifest) if manifest else {
        "format_version": "legacy-v2",
        "mode": "legacy",
    }
    if baseline is not None and assurance is not None:
        snapshot["assurance"] = {
            "summary": assurance_summary(
                baseline,
                assurance,
                implementation_frontier=frontier,
            ),
            "baseline": copy.deepcopy(baseline),
            "impacts": copy.deepcopy(assurance.get("impacts", [])),
            "inspections": copy.deepcopy(assurance.get("inspections", [])),
            "findings": copy.deepcopy(assurance.get("findings", [])),
            "scope_drift": copy.deepcopy(assurance.get("scope_drift", [])),
            "controls": copy.deepcopy(assurance.get("controls", {})),
            "legacy_bridge": copy.deepcopy(assurance.get("legacy_bridge", {})),
        }
    else:
        snapshot["assurance"] = None
    return snapshot



def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def node_doc_path(paths: dict[str, Path], node: dict[str, Any]) -> Path:
    name = f"{node['id']}-{slugify(node['title'])}.md"
    if node["kind"] in EXECUTABLE_KINDS:
        folder = f"{node['wave']:02d}-{slugify(node['workstream'])}"
        return paths["docs"] / folder / name
    return paths["docs"] / "nodes" / name


def _markdown_list(values: list[str], empty: str = "None") -> str:
    return "\n".join(f"- {value}" for value in values) if values else f"- {empty}"


def render_node_markdown(
    paths: dict[str, Path],
    plan: dict[str, Any],
    state: dict[str, Any],
    node: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    assurance: dict[str, Any] | None = None,
    frontier: dict[str, dict[str, Any]] | None = None,
) -> str:
    packet = task_packet(plan, state, node["id"], baseline, assurance, frontier)
    dependencies = [f"`{item['id']}` ({item['type']}, {item['verification']})" for item in packet["dependencies"]]
    criteria = [f"`{item['id']}` — {item['description']}" for item in node["acceptance_criteria"]]
    evidence = [f"`{item['id']}` ({item['type']}) — {item['description']}" for item in node["required_evidence"]]
    status = state["nodes"][node["id"]]
    assurance_section = ""
    if "assurance" in packet:
        coverage = packet["assurance"]
        assurance_section = f"""
## Brownfield Assurance

- Status: `{coverage['status']}`
- Impact records: {', '.join(f'`{item}`' for item in coverage['impact_ids']) or 'None'}
- Affected assets: {', '.join(f'`{item}`' for item in coverage['asset_ids']) or 'None'}
- Inspections: {', '.join(f'`{item}`' for item in coverage['inspection_ids']) or 'None'}

### Assurance Blockers

{_markdown_list(coverage['blockers'])}
"""
    return f"""<!-- Generated by Pyramid Task V3. Change canonical files through Pyramid Task interfaces, not this file. -->
# {node['id']}: {node['title']}

## Metadata

- Kind: `{node['kind']}`
- Level: `{node['level']}`
- Wave: `{node['wave']}`
- Workstream: `{node['workstream']}`
- Selection: `{node['selection']}`
- Execution: `{status['execution']}`
- Verification: `{status['verification']}`
- Health: `{status['health']}`
- Availability: `{packet['availability']}`
- Goal trace: {' → '.join(f'`{item}`' for item in packet['goal_trace'])}

## Goal

{node['summary']}

## Deliverables

{_markdown_list(node['agent']['deliverables'])}

## Allowed Write Scope

{_markdown_list(node['agent']['allowed_write_scope'])}

## Non-Goals

{_markdown_list(node['agent']['non_goals'])}

## Dependencies

{_markdown_list(dependencies)}

## Required Context

{_markdown_list(node['agent']['required_context'])}

## Validation Commands

{_markdown_list(node['agent']['commands'])}

## Acceptance Criteria

{_markdown_list(criteria)}

## Required Evidence

{_markdown_list(evidence)}

## Audit Gates

{_markdown_list([f'`{gate}`' for gate in packet['audit_gates']])}
{assurance_section}
{render_guide(plan, node['id']) if plan.get('schema_version') == 2 and node['selection'] == 'primary' else ''}
"""


def _report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "<!-- Generated by Pyramid Task V3. -->",
        f"# Final Report: {report['title']}",
        "",
        f"- Plan: `{report['plan_id']}`",
        f"- Revision: `{report['revision']}`",
        f"- Graph version: `{report['graph_version']}`",
        f"- Completed at: `{report['completed_at']}`",
        f"- Completed by: `{report['completed_by']}`",
        "",
        "## Intent",
        "",
        report["intent"]["statement"],
        "",
        "## Success Evidence",
        "",
    ]
    for item in report["success_evidence"]:
        lines.append(f"- `{item['id']}` — {item['description']} (covered by: {', '.join(item['covered_by']) or 'none'})")
    lines.extend(["", "## Verified Primary Nodes", ""])
    lines.extend(f"- `{item['id']}` — {item['title']}" for item in report["verified_primary_nodes"])
    lines.extend(["", "## Residual Risks", ""])
    lines.extend(f"- {item}" for item in report["residual_risks"] or ["None recorded"])
    lines.append("")
    return "\n".join(lines)


def _dossier_markdown(dossier: dict[str, Any]) -> str:
    lines = [
        "<!-- Generated by Pyramid Task V3. -->",
        f"# Change Dossier: {dossier['title']}",
        "",
        f"- Dossier: `{dossier['dossier_id']}`",
        f"- Plan: `{dossier['plan_id']}`",
        f"- Completed at: `{dossier['completed_at']}`",
        f"- Completed by: `{dossier['completed_by']}`",
        f"- Baseline: revision `{dossier['baseline_before']['revision']}` → `{dossier['baseline_after']['revision']}`",
        "",
        "## Intent",
        "",
        dossier["intent"]["statement"],
        "",
        "## Predicted Impact",
        "",
    ]
    lines.extend(
        f"- `{item['id']}` → `{item['asset_id']}` ({item['type']}, {item['status']})"
        for item in dossier["predicted_impacts"]
    )
    if not dossier["predicted_impacts"]:
        lines.append("- None recorded")
    lines.extend(["", "## Actual Changes", ""])
    lines.extend(
        f"- `{item['task']}`: `{item['file']}` → "
        + (", ".join(f"`{asset}`" for asset in item["asset_ids"]) or "unmapped")
        for item in dossier["actual_changes"]
    )
    if not dossier["actual_changes"]:
        lines.append("- None recorded")
    lines.extend(["", "## Inspections", ""])
    lines.extend(
        f"- `{item['id']}` — {item['method']} ({item['result']}, {item['sufficiency']})"
        for item in dossier["inspections"]
    )
    if not dossier["inspections"]:
        lines.append("- None recorded")
    lines.extend(["", "## Scope Drift", ""])
    lines.extend(
        f"- `{item['id']}` — `{item['changed_file']}` ({item['status']})"
        for item in dossier["scope_drift"]
    )
    if not dossier["scope_drift"]:
        lines.append("- None recorded")
    lines.extend(["", "## Findings and Residual Risk", ""])
    lines.extend(
        f"- `{item['id']}` — {item['title']} ({item['severity']}, {item['status']})"
        for item in dossier["findings"]
    )
    lines.extend(f"- {item}" for item in dossier["residual_risks"])
    if not dossier["findings"] and not dossier["residual_risks"]:
        lines.append("- None recorded")
    lines.extend(["", "## Recovery and Observation", ""])
    for name in ("rollback", "monitoring"):
        control = dossier["controls"][name]
        lines.append(f"- {name.capitalize()}: `{control['status']}`")
    lines.append("")
    return "\n".join(lines)


def _build_change_dossier(
    plan: dict[str, Any],
    state: dict[str, Any],
    baseline: dict[str, Any],
    assurance: dict[str, Any],
    actor: str,
    completed_at: str,
    dossier_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline_before = copy.deepcopy(baseline)
    baseline_after = copy.deepcopy(baseline)
    baseline_after["revision"] += 1
    baseline_after["status"] = "current"
    baseline_after["captured_at"] = completed_at
    baseline_after["captured_by"] = actor
    baseline_after["capture_method"] = "verified-change-close"
    history_id = f"HISTORY-{slugify(plan['plan_id']).upper()}-R{plan['revision']}"
    existing_history_ids = {item.get("id") for item in baseline_after.get("history", [])}
    if history_id in existing_history_ids:
        history_id = f"{history_id}-G{state['graph_version'] + 1}"
    impacted_assets = sorted(
        {item["asset_id"] for item in assurance.get("impacts", []) if item.get("status") != "dismissed"}
    )
    baseline_after.setdefault("history", []).append(
        {
            "id": history_id,
            "kind": "change",
            "summary": f"Completed {plan['title']} under dossier {dossier_id}.",
            "asset_ids": impacted_assets,
            "evidence": [dossier_id],
            "date": completed_at,
            "controls": [
                name
                for name, control in assurance.get("controls", {}).items()
                if control.get("status") == "ready"
            ],
        }
    )
    actual_changes: list[dict[str, str]] = []
    audits: list[dict[str, Any]] = []
    residual_risks: list[Any] = []
    for node in plan["nodes"]:
        item = state["nodes"][node["id"]]
        result = item.get("last_result")
        if isinstance(result, dict):
            recorded_assets: set[str] = set()
            for changed in result.get("changed_files", []):
                if not isinstance(changed, str):
                    continue
                mapped_assets = sorted(asset_ids_for_file(baseline, changed))
                recorded_assets.update(mapped_assets)
                actual_changes.append(
                    {
                        "task": node["id"],
                        "file": changed,
                        "asset_ids": mapped_assets,
                    }
                )
            for asset_id in result.get("changed_assets", []):
                if isinstance(asset_id, str) and asset_id not in recorded_assets:
                    actual_changes.append(
                        {
                            "task": node["id"],
                            "file": f"asset:{asset_id}",
                            "asset_ids": [asset_id],
                        }
                    )
            residual_risks.extend(result.get("discovered_risks", []))
        if isinstance(item.get("last_audit"), dict):
            audits.append({"node": node["id"], "audit": copy.deepcopy(item["last_audit"])})
    residual_risks.extend(
        {
            "finding": item["id"],
            "severity": item["severity"],
            "status": item["status"],
            "acceptance_reason": item.get("acceptance_reason"),
        }
        for item in assurance.get("findings", [])
        if item.get("status") == "accepted"
    )
    dossier = {
        "schema": "pyramid-change-dossier-v1",
        "dossier_id": dossier_id,
        "plan_id": plan["plan_id"],
        "title": plan["title"],
        "completed_at": completed_at,
        "completed_by": actor,
        "baseline_before": baseline_before,
        "baseline_after": copy.deepcopy(baseline_after),
        "intent": copy.deepcopy(plan["intent"]),
        "predicted_impacts": copy.deepcopy(assurance.get("impacts", [])),
        "actual_changes": actual_changes,
        "inspections": copy.deepcopy(assurance.get("inspections", [])),
        "scope_drift": copy.deepcopy(assurance.get("scope_drift", [])),
        "findings": copy.deepcopy(assurance.get("findings", [])),
        "controls": copy.deepcopy(assurance.get("controls", {})),
        "audits": audits,
        "residual_risks": residual_risks,
        "legacy_bridge": copy.deepcopy(assurance.get("legacy_bridge", {})),
    }
    return dossier, baseline_after


def _completion_report(plan: dict[str, Any], state: dict[str, Any], actor: str, completed_at: str) -> dict[str, Any]:
    primary = [node for node in plan["nodes"] if node["selection"] == "primary"]
    success = []
    for criterion in plan["intent"]["success_evidence"]:
        success.append(
            {
                **copy.deepcopy(criterion),
                "covered_by": sorted(node["id"] for node in primary if criterion["id"] in node["source_requirements"]),
            }
        )
    risks: list[str] = []
    for node in primary:
        result = state["nodes"][node["id"]].get("last_result")
        if isinstance(result, dict):
            for risk in result.get("discovered_risks", []):
                risks.append(f"{node['id']}: {risk}")
    return {
        "schema": "pyramid-final-report-v1",
        "plan_id": plan["plan_id"],
        "title": plan["title"],
        "revision": plan["revision"],
        "graph_version": state["graph_version"] + 1,
        "completed_at": completed_at,
        "completed_by": actor,
        "intent": copy.deepcopy(plan["intent"]),
        "success_evidence": success,
        "verified_primary_nodes": [
            {"id": node["id"], "title": node["title"], "last_audit": state["nodes"][node["id"]].get("last_audit")}
            for node in primary
        ],
        "decisions": copy.deepcopy(plan["decisions"]),
        "evidence": copy.deepcopy(plan["evidence"]),
        "residual_risks": risks,
    }


def render_intent_markdown(plan):
    intent = plan["intent"]
    intent_text = f"""<!-- Generated by Pyramid Task V3. -->
# Intent: {plan['title']}

{intent['statement']}

## Success Evidence

{_markdown_list([f"`{item['id']}` — {item['description']}" for item in intent['success_evidence']])}

## Constraints

{_markdown_list(intent['constraints'])}

## Non-Goals

{_markdown_list(intent['non_goals'])}

## Assumptions

{_markdown_list([f"`{item['id']}` ({item['confidence']}) — {item['statement']}" for item in intent['assumptions']])}
"""
    return intent_text


def batch_documents(paths, plan):
    executable = [node for node in plan["nodes"] if node["kind"] in EXECUTABLE_KINDS]
    batches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in executable:
        batches[f"{node['wave']:02d}-{slugify(node['workstream'])}"].append(node)
    for folder, batch_nodes in batches.items():
        lines = [f"# Batch {folder}\n", "## Tasks\n"]
        for node in sorted(batch_nodes, key=lambda item: item["id"]):
            lines.append(f"- [`{node['id']}`]({node_doc_path(paths, node).name}) — {node['title']}")
        lines.extend(["", "## Parallelism", "", "Use the ready index; tasks in the same batch are parallel only when their typed dependencies are verified.", ""])
        yield paths["docs"] / folder / "README.md", "\n".join(lines)



def render_project_readme(paths, plan, state, snapshot, ready_packets, baseline, assurance, frontier):
    intent = plan["intent"]
    batches = {f"{node['wave']:02d}-{slugify(node['workstream'])}" for node in plan["nodes"] if node["kind"] in EXECUTABLE_KINDS}
    summary = snapshot["summary"]
    readme_lines = [
        "<!-- Generated by Pyramid Task V3. -->",
        f"# {plan['title']}",
        "",
        intent["statement"],
        "",
        "## Current State",
        "",
        f"- Graph version: `{state['graph_version']}`",
        f"- Plan revision: `{plan['revision']}`",
        f"- Lifecycle: `{lifecycle_status(state)}`",
        f"- Verified primary nodes: `{summary['verified_primary_nodes']}/{summary['primary_nodes']}`",
        f"- Ready tasks: `{len(ready_packets)}`",
        "",
        "## Ready Frontier",
        "",
    ]
    readme_lines.extend([f"- `{packet['task']}` — {packet['title']}" for packet in ready_packets] or ["- None"])
    if plan.get("schema_version") == 2:
        readme_lines.extend(["", "## Development Harness", "",
                             "[Generated guide](DEVELOPMENT_HARNESS.md). Use `inspect --harness <node>` for scoped capture/reuse and audit readiness for current input freshness. Recorded verification is historical, not a working-tree watch."])
    if baseline is not None and assurance is not None:
        summary_assurance = assurance_summary(
            baseline,
            assurance,
            implementation_frontier=frontier,
        )
        readme_lines.extend(
            [
                "",
                "## Brownfield Assurance",
                "",
                f"- Status: `{summary_assurance['status']}`",
                f"- Baseline: `{summary_assurance['baseline_status']}` revision `{summary_assurance['baseline_revision']}`",
                f"- Impacted assets inspected sufficiently: `{summary_assurance['sufficiently_inspected_assets']}/{summary_assurance['impacted_assets']}`",
                f"- Open scope drift: `{summary_assurance['open_scope_drift']}`",
                f"- Open material findings: `{summary_assurance['open_material_findings']}`",
            ]
        )
    readme_lines.extend(["", "## Batch Order", ""])
    readme_lines.extend([f"- [`{folder}`]({folder}/README.md)" for folder in sorted(batches)] or ["- No executable batches"])
    readme_lines.extend(
        [
            "",
            "## Dependency Rule",
            "",
            "Start work only from the generated ready frontier. Implementation completion remains unverified until its audit passes.",
            "",
            "## Definition of Done",
            "",
            "The final intent is done only when its success evidence exists, required children are verified, and its final audit passes.",
            "",
        ]
    )
    return "\n".join(readme_lines)
