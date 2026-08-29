from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pyramid_core import (
    compile_and_load_graph,
    graph_snapshot,
    lifecycle_status,
    load_assurance_bundle,
    load_json,
    load_project,
    project_paths,
)


EXECUTABLE_NODE_KINDS = {
    "research",
    "contract",
    "implementation",
    "integration",
    "risk-control",
    "audit",
}


def _check_counts(records: Any) -> dict[str, int]:
    checks = records if isinstance(records, list) else []
    counts = {"passed": 0, "failed": 0, "not_run": 0, "total": 0}
    for check in checks:
        if not isinstance(check, dict):
            continue
        result = check.get("result")
        if result == "passed":
            counts["passed"] += 1
        elif result == "failed":
            counts["failed"] += 1
        else:
            counts["not_run"] += 1
        counts["total"] += 1
    return counts


def _proof_summary(node: dict[str, Any]) -> dict[str, Any]:
    state = node.get("state", {})
    result = state.get("last_result") if isinstance(state.get("last_result"), dict) else {}
    audit = state.get("last_audit") if isinstance(state.get("last_audit"), dict) else {}
    acceptance = result.get("acceptance_evidence") if isinstance(result, dict) else []
    return {
        "verification": state.get("verification", "unverified"),
        "updated_at": state.get("updated_at"),
        "implementation_checks": _check_counts(result.get("checks")),
        "acceptance_checks": _check_counts(acceptance),
        "audit_checks": _check_counts(audit.get("checks")),
        "recommended_action": audit.get("recommended_action"),
    }


def _outcome_status(
    outcome: dict[str, Any],
    gate: dict[str, Any] | None,
    supporting: list[dict[str, Any]],
) -> str:
    related = [outcome, *supporting]
    if gate is not None:
        related.append(gate)
    if outcome.get("state", {}).get("verification") == "passed":
        return "verified"
    if any(
        item.get("state", {}).get("verification") == "failed"
        or item.get("state", {}).get("execution") == "needs-rework"
        or item.get("state", {}).get("health") == "blocked"
        for item in related
    ):
        return "needs-attention"
    if any(item.get("state", {}).get("execution") == "working" for item in related):
        return "in-progress"
    if gate is not None and (
        gate.get("state", {}).get("verification") == "pending"
        or gate.get("state", {}).get("execution") == "implemented"
    ):
        return "proof-pending"
    if gate is not None and gate.get("availability") == "ready":
        return "ready-for-proof"
    if any(item.get("availability") == "ready" for item in related):
        return "work-ready"
    return "planned"


def _target_outcome(node: dict[str, Any], node_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for candidate_id in node.get("goal_trace", []):
        candidate = node_by_id.get(candidate_id)
        if candidate and candidate.get("kind") == "outcome" and candidate.get("selection") == "primary":
            return candidate
    return None


def observer_projection(graph: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a deterministic, human-first read model without adding canonical state."""
    node_by_id = {node["id"]: node for node in nodes}
    intent = node_by_id.get(graph["intent"]["id"], {})
    primary = [node for node in nodes if node.get("selection") == "primary"]
    outcomes = sorted(
        (node for node in primary if node.get("kind") == "outcome"),
        key=lambda node: (-node.get("level", 0), node.get("wave", 0), node["id"]),
    )
    stages: list[dict[str, Any]] = []
    for outcome in outcomes:
        gate = next(
            (node_by_id.get(gate_id) for gate_id in outcome.get("audit_gates", [])),
            None,
        )
        supporting = [
            node
            for node in primary
            if node["id"] != outcome["id"] and outcome["id"] in node.get("goal_trace", [])
        ]
        stages.append(
            {
                "id": outcome["id"],
                "title": outcome["title"],
                "summary": outcome["summary"],
                "status": _outcome_status(outcome, gate, supporting),
                "verification": outcome.get("state", {}).get("verification"),
                "updated_at": outcome.get("state", {}).get("updated_at"),
                "gate": {
                    "id": gate["id"],
                    "title": gate["title"],
                    "summary": gate["summary"],
                    "availability": gate.get("availability"),
                    "verification": gate.get("state", {}).get("verification"),
                    "acceptance_criteria": gate.get("acceptance_criteria", []),
                    "required_evidence": gate.get("required_evidence", []),
                    "proof": gate.get("proof"),
                }
                if gate
                else None,
                "acceptance_criteria": outcome.get("acceptance_criteria", []),
                "required_evidence": outcome.get("required_evidence", []),
                "supporting_work": len(supporting),
                "active_work": sum(
                    node.get("state", {}).get("execution") == "working" for node in supporting
                ),
                "attention_items": sum(
                    node.get("state", {}).get("health") in {"at-risk", "blocked"}
                    or node.get("state", {}).get("verification") == "failed"
                    or node.get("state", {}).get("execution") == "needs-rework"
                    for node in supporting
                ),
            }
        )

    verified_stages = [stage for stage in stages if stage["status"] == "verified"]
    verified_stages.sort(
        key=lambda stage: (stage.get("updated_at") or "", stages.index(stage))
    )
    last_verified = verified_stages[-1] if verified_stages else None
    next_stage = next((stage for stage in stages if stage["status"] != "verified"), None)

    work_items = []
    attention = []
    for node in primary:
        state = node.get("state", {})
        target = _target_outcome(node, node_by_id)
        target_summary = (
            {"id": target["id"], "title": target["title"]} if target else None
        )
        base = {
            "id": node["id"],
            "title": node["title"],
            "summary": node["summary"],
            "kind": node["kind"],
            "owner": state.get("owner"),
            "availability": node.get("availability"),
            "updated_at": state.get("updated_at"),
            "target_outcome": target_summary,
        }
        if state.get("execution") == "working" and state.get("health") != "blocked":
            work_items.append(base)

        issue_type = None
        next_action = None
        if state.get("verification") == "failed" or state.get("execution") == "needs-rework":
            issue_type, next_action = "Failed proof", "Repair the evidence gap, then re-audit."
        elif state.get("health") == "blocked":
            issue_type, next_action = "Blocked", "Resolve the stated blocker before continuing."
        elif state.get("health") == "at-risk":
            issue_type, next_action = "At risk", "Investigate the risk before it affects the next outcome."
        elif state.get("execution") == "paused":
            issue_type, next_action = "Paused handoff", "Resume from the durable handoff or reassign it."
        if issue_type:
            attention.append(
                {
                    **base,
                    "type": issue_type,
                    "reason": state.get("blocker") or "No additional reason was recorded.",
                    "next_action": next_action,
                }
            )

    priority = {"needs-rework": 0, "working": 1, "ready": 2, "paused": 3, "blocked": 4, "locked": 5}
    executable = [node for node in primary if node.get("kind") in EXECUTABLE_NODE_KINDS]
    recommended = min(
        executable or primary or nodes,
        key=lambda node: (
            priority.get(node.get("availability"), 9),
            node.get("wave", 0),
            node.get("level", 0),
            node["id"],
        ),
        default=None,
    )
    recommended_target = _target_outcome(recommended, node_by_id) if recommended else None
    if recommended:
        availability = recommended.get("availability")
        reason = {
            "working": "Continue the active work and record its evidence.",
            "needs-rework": "Repair the failed proof before advancing dependent outcomes.",
            "ready": "This is the next executable task whose prerequisites are satisfied.",
            "paused": "Resume from the handoff before starting duplicate work.",
            "blocked": "Resolve its blocker or choose another ready task.",
            "locked": "No executable work is ready; inspect the blockers on the next outcome.",
        }.get(availability, "Inspect this task as the current planning focus.")
        recommended_view = {
            "id": recommended["id"],
            "title": recommended["title"],
            "summary": recommended["summary"],
            "availability": availability,
            "reason": reason,
            "target_outcome": (
                {"id": recommended_target["id"], "title": recommended_target["title"]}
                if recommended_target
                else None
            ),
        }
    else:
        recommended_view = None

    assurance = graph.get("assurance", {}).get("summary") if graph.get("assurance") else None
    if assurance and (
        assurance.get("status") == "blocked"
        or assurance.get("open_scope_drift", 0)
        or assurance.get("open_material_findings", 0)
    ):
        attention.append(
            {
                "id": "CHANGE-ASSURANCE",
                "title": "Change assurance needs attention",
                "summary": "Brownfield inspection, findings, or scope drift can block acceptance.",
                "kind": "assurance",
                "owner": None,
                "availability": assurance.get("status"),
                "updated_at": None,
                "target_outcome": None,
                "type": "Assurance",
                "reason": (
                    f"{assurance.get('open_scope_drift', 0)} open scope drift; "
                    f"{assurance.get('open_material_findings', 0)} material findings."
                ),
                "next_action": "Reconcile impact and inspection coverage before the affected audit.",
            }
        )

    intent_verified = intent.get("state", {}).get("verification") == "passed"
    return {
        "intent": {
            "id": graph["intent"]["id"],
            "statement": graph["intent"].get("statement") or intent.get("summary"),
            "success_evidence": graph["intent"].get("success_evidence", []),
            "verified": intent_verified,
        },
        "progress": {
            "label": (
                "Intent verified"
                if intent_verified
                else f"{len(verified_stages)} of {len(stages)} outcomes verified"
                if stages
                else f"{graph['summary']['verified_primary_nodes']} of {graph['summary']['primary_nodes']} primary nodes verified"
            ),
            "verified_outcomes": len(verified_stages),
            "outcomes": len(stages),
            "working": len(work_items),
            "attention": len(attention),
            "ready": graph.get("summary", {}).get("availability", {}).get("ready", 0),
        },
        "last_verified": last_verified,
        "next_outcome": next_stage,
        "outcomes": stages,
        "working": sorted(work_items, key=lambda item: (item["title"], item["id"])),
        "attention": sorted(
            attention,
            key=lambda item: (
                {"Failed proof": 0, "Blocked": 1, "Assurance": 2, "At risk": 3, "Paused handoff": 4}.get(item["type"], 9),
                item["title"],
            ),
        ),
        "recommended": recommended_view,
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pyramid Task Map</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f7f8fb;
    --fg: #18202d;
    --muted: #657084;
    --panel: #ffffff;
    --border: #ccd3df;
    --edge: #9aa4b5;
    --ready: #12a594;
    --working: #2878d0;
    --paused: #d88426;
    --implemented: #8a63d2;
    --rework: #d45d18;
    --verified: #258a4b;
    --blocked: #c43d4e;
    --locked: #7c8798;
    --audit: #c57a13;
    --focus: #2867c7;
    --assurance-covered: #1b9a72;
    --assurance-blocked: #e05a36;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #11151d;
      --fg: #edf1f7;
      --muted: #a9b2c1;
      --panel: #191f2a;
      --border: #3b4556;
      --edge: #596579;
      --ready: #39c6b4;
      --working: #66a9ef;
      --paused: #f0ae56;
      --implemented: #aa8ee8;
      --rework: #ff985f;
      --verified: #61c782;
      --blocked: #ed7180;
      --locked: #909bad;
      --audit: #e3a74d;
      --focus: #8dc3ff;
      --assurance-covered: #4fd3a8;
      --assurance-blocked: #ff8d69;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.45 system-ui, sans-serif; }
  main { max-width: 1500px; margin: 0 auto; padding: 18px; }
  h1 { margin: 0 0 4px; font-size: 1.35rem; font-weight: 600; }
  .meta { color: var(--muted); margin-bottom: 10px; }
  [hidden] { display: none !important; }
  .intent-statement { max-width: 920px; margin: 5px 0 14px; font-size: 1.02rem; }
  .surface-switch { display: inline-flex; gap: 4px; padding: 4px; margin: 0 0 16px; border: 1px solid var(--border); border-radius: 10px; background: var(--panel); }
  .surface-switch button { border-color: transparent; background: transparent; }
  .surface-switch button[aria-pressed="true"] { background: var(--bg); border-color: var(--border); box-shadow: none; }
  .observer { display: grid; gap: 14px; }
  .observer-summary { display: grid; grid-template-columns: 1.2fr 1.2fr .8fr; gap: 10px; }
  .story-card, .observer-panel { background: var(--panel); border: 1px solid var(--border); border-radius: 11px; }
  .story-card { min-height: 132px; padding: 15px; }
  .story-card .eyebrow, .observer-panel .eyebrow { color: var(--muted); font-size: .75rem; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; }
  .story-card h2, .observer-panel h2 { margin: 5px 0 6px; font-size: 1.05rem; }
  .story-card p, .observer-panel p { margin: 5px 0; }
  .story-card.verified { border-color: var(--verified); }
  .story-card.attention { border-color: var(--blocked); }
  .observer-panel { padding: 15px; min-width: 0; }
  .observer-panel > h2 { margin-top: 0; }
  .outcome-path { display: flex; gap: 8px; align-items: stretch; overflow-x: auto; padding: 3px 2px 8px; }
  .outcome-step { position: relative; flex: 1 0 210px; max-width: 340px; min-height: 122px; padding: 12px; text-align: left; border-radius: 9px; }
  .outcome-step::after { content: '→'; position: absolute; right: -10px; top: 48%; color: var(--muted); z-index: 2; }
  .outcome-step:last-child::after { content: ''; }
  .outcome-step strong { display: block; margin: 5px 0; }
  .outcome-step small { color: var(--muted); }
  .outcome-step.verified { border-color: var(--verified); }
  .outcome-step.in-progress, .outcome-step.proof-pending { border-color: var(--working); }
  .outcome-step.needs-attention { border-color: var(--blocked); }
  .outcome-step.ready, .outcome-step.work-ready, .outcome-step.ready-for-proof { border-color: var(--ready); }
  .observer-columns { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
  .semantic-list { display: grid; gap: 8px; }
  .semantic-item { width: 100%; padding: 10px; text-align: left; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; }
  .semantic-item strong { display: block; }
  .semantic-item span, .empty-state { color: var(--muted); font-size: .84rem; }
  .semantic-item.issue { border-left: 4px solid var(--blocked); }
  .semantic-item.work { border-left: 4px solid var(--working); }
  .recommended-action { border-left: 4px solid var(--ready); padding: 10px 12px; background: var(--bg); border-radius: 8px; }
  .recommended-action strong { display: block; margin: 3px 0; }
  .observer-lower { display: grid; grid-template-columns: minmax(300px, .9fr) minmax(380px, 1.1fr); gap: 10px; align-items: start; }
  .structure-tree, .structure-tree ul { list-style: none; margin: 0; padding-left: 16px; }
  .structure-tree { padding-left: 0; }
  .structure-tree li { margin: 5px 0; }
  .tree-node { width: 100%; padding: 7px 9px; text-align: left; border-color: transparent; background: transparent; }
  .tree-node:hover, .tree-node.selected { border-color: var(--focus); background: var(--bg); }
  .tree-node .tree-status { float: right; color: var(--muted); font-size: .78rem; }
  .proof-status { display: inline-flex; padding: 3px 7px; border: 1px solid var(--border); border-radius: 999px; color: var(--muted); font-size: .78rem; }
  .proof-grid { display: grid; grid-template-columns: repeat(3, minmax(90px, 1fr)); gap: 7px; margin: 10px 0; }
  .proof-metric { padding: 8px; background: var(--bg); border-radius: 7px; }
  .proof-metric strong { display: block; font-size: 1rem; }
  .proof-metric span { color: var(--muted); font-size: .76rem; }
  .technical-details { margin-top: 12px; color: var(--muted); }
  .technical-details summary { cursor: pointer; }
  .live-status { display: inline-flex; align-items: center; gap: 7px; margin: 0 0 12px; padding: 5px 9px; border: 1px solid var(--border); border-radius: 999px; color: var(--muted); font-size: .82rem; }
  .live-status[hidden] { display: none; }
  .live-status::before { content: ''; width: 8px; height: 8px; border-radius: 50%; background: var(--locked); }
  .live-status.connected::before { background: var(--ready); }
  .live-status.syncing::before { background: var(--working); }
  .live-status.error { color: var(--blocked); border-color: var(--blocked); }
  .live-status.error::before { background: var(--blocked); }
  .overview { display: grid; grid-template-columns: repeat(5, minmax(92px, 1fr)) minmax(220px, 2fr); gap: 8px; margin-bottom: 12px; }
  .metric, .recommended { min-height: 72px; text-align: left; background: var(--panel); }
  .metric strong { display: block; font-size: 1.35rem; line-height: 1.1; }
  .metric span, .recommended span { color: var(--muted); font-size: .78rem; }
  .recommended strong { display: block; margin-top: 3px; font-size: .94rem; }
  .recommended.ready { border-color: var(--ready); }
  .recommended.working { border-color: var(--working); }
  .recommended.paused { border-color: var(--paused); }
  .recommended.needs-rework { border-color: var(--rework); }
  .recommended.blocked, .recommended.locked { border-color: var(--blocked); }
  .assurance-panel { display: none; margin: 0 0 12px; padding: 10px 12px; background: var(--panel); border: 1px solid var(--border); border-radius: 9px; }
  .assurance-panel.visible { display: block; }
  .assurance-panel strong { margin-right: 8px; }
  .assurance-panel.blocked { border-color: var(--assurance-blocked); }
  .assurance-panel.ready { border-color: var(--assurance-covered); }
  .toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: end; margin-bottom: 12px; }
  .group { display: flex; gap: 6px; flex-wrap: wrap; }
  .group[hidden] { display: none; }
  button, select { font: inherit; color: var(--fg); background: var(--panel); border: 1px solid var(--border); border-radius: 7px; padding: 7px 10px; }
  button { cursor: pointer; }
  button[aria-pressed="true"] { border-color: var(--focus); box-shadow: 0 0 0 2px color-mix(in srgb, var(--focus) 30%, transparent); }
  label { display: grid; gap: 3px; color: var(--muted); font-size: .82rem; }
  select { min-width: 210px; }
  .layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 340px); gap: 14px; align-items: start; }
  .plot, .detail { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; }
  .plot { min-width: 0; overflow: auto; }
  svg { display: block; width: 100%; min-width: 680px; height: auto; }
  .detail { padding: 14px; position: sticky; top: 12px; }
  .detail h2 { margin: 0 0 6px; font-size: 1.08rem; }
  .detail dl { display: grid; grid-template-columns: max-content 1fr; gap: 5px 9px; margin: 12px 0; }
  .detail dt { color: var(--muted); }
  .detail dd { margin: 0; overflow-wrap: anywhere; }
  .detail ul { margin: 5px 0 12px; padding-left: 20px; }
  .detail a { color: var(--focus); }
  .node { cursor: pointer; }
  .node text { fill: var(--fg); font-size: 12px; pointer-events: none; }
  .node .node-id { fill: var(--muted); font-size: 10px; }
  .node .mark { fill: var(--locked); stroke: var(--panel); stroke-width: 2; }
  .node.ready .mark { fill: var(--ready); }
  .node.working .mark { fill: var(--working); }
  .node.paused .mark { fill: var(--paused); }
  .node.implemented .mark { fill: var(--implemented); }
  .node.needs-rework .mark { fill: var(--rework); }
  .node.verified .mark { fill: var(--verified); }
  .node.blocked .mark { fill: var(--blocked); }
  .node.not-selected { opacity: .34; }
  .node.audit .mark { stroke: var(--audit); stroke-width: 4; }
  .node.work-package .mark { stroke: var(--focus); stroke-width: 4; }
  .node.verification-pending .verify { stroke: var(--audit); stroke-dasharray: 4 3; }
  .node.verification-failed .verify { stroke: var(--blocked); }
  .node.verification-passed .verify { stroke: var(--verified); }
  .node .verify { fill: none; stroke: transparent; stroke-width: 3; }
  .node .assure { fill: none; stroke: transparent; stroke-width: 3; stroke-dasharray: 3 3; }
  .node.assurance-covered .assure { stroke: var(--assurance-covered); }
  .node.assurance-blocked .assure { stroke: var(--assurance-blocked); }
  .node.assurance-hidden .assure { stroke: transparent; }
  .node.selected .verify { stroke: var(--focus); stroke-width: 4; }
  .node.changed .mark { animation: node-change 1.4s ease-out; }
  .edge { stroke: var(--edge); stroke-width: 1.25; fill: none; opacity: .65; }
  .edge.dependency { stroke-dasharray: 5 4; }
  .edge.highlight { stroke: var(--focus); stroke-width: 2.5; opacity: 1; }
  .level-label { fill: var(--muted); font-size: 12px; }
  .legend { display: flex; flex-wrap: wrap; gap: 10px 16px; padding: 10px 12px; color: var(--muted); border-top: 1px solid var(--border); }
  .swatch { display: inline-flex; align-items: center; gap: 5px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--locked); }
  .dot.ready { background: var(--ready); } .dot.working { background: var(--working); }
  .dot.paused { background: var(--paused); }
  .dot.verified { background: var(--verified); } .dot.blocked { background: var(--blocked); }
  .dot.rework { background: var(--rework); }
  @keyframes node-change { 0%, 30% { filter: drop-shadow(0 0 9px var(--focus)); transform: scale(1.28); transform-origin: center; } 100% { filter: none; transform: scale(1); } }
  @media (max-width: 1080px) { .overview { grid-template-columns: repeat(3, minmax(92px, 1fr)); } }
  @media (max-width: 920px) { .layout, .observer-summary, .observer-columns, .observer-lower { grid-template-columns: 1fr; } .detail { position: static; } }
  @media (max-width: 620px) { .overview { grid-template-columns: repeat(2, minmax(92px, 1fr)); } .recommended { grid-column: 1 / -1; } .surface-switch { display: flex; } .surface-switch button { flex: 1; } }
  @media (prefers-reduced-motion: no-preference) { .node, .edge { transition: opacity .18s, transform .18s; } }
  @media (prefers-reduced-motion: reduce) { .node.changed .mark { animation: none; } }
</style>
</head>
<body>
<main>
  <h1 id="page-title"></h1>
  <p class="intent-statement" id="intent-statement"></p>
  <div class="meta" id="page-meta"></div>
  <div class="live-status" id="live-status" role="status" aria-live="polite" hidden>Connecting…</div>
  <nav class="surface-switch" aria-label="Dashboard view">
    <button type="button" data-surface="observer" aria-pressed="true">Intent observer</button>
    <button type="button" data-surface="graph" aria-pressed="false">Technical graph</button>
  </nav>
  <section class="observer" id="observer-view" aria-label="Intent observer dashboard">
    <section class="observer-summary" id="observer-summary" aria-label="Intent progress summary"></section>
    <section class="observer-panel" aria-labelledby="outcome-path-title">
      <div class="eyebrow">Delivery path</div>
      <h2 id="outcome-path-title">Verified outcomes toward the intent</h2>
      <div class="outcome-path" id="outcome-path"></div>
    </section>
    <section class="observer-columns" aria-label="Current execution picture">
      <article class="observer-panel">
        <div class="eyebrow">Now</div><h2>Actually working</h2>
        <div class="semantic-list" id="working-list"></div>
      </article>
      <article class="observer-panel">
        <div class="eyebrow">Attention</div><h2>What needs intervention</h2>
        <div class="semantic-list" id="attention-list"></div>
      </article>
      <article class="observer-panel">
        <div class="eyebrow">Next</div><h2>Recommended action</h2>
        <div id="recommended-action"></div>
      </article>
    </section>
    <section class="observer-lower">
      <article class="observer-panel">
        <div class="eyebrow">Structure</div><h2>How the intent is organized</h2>
        <ul class="structure-tree" id="structure-tree"></ul>
      </article>
      <article class="observer-panel" id="observer-detail" aria-live="polite"></article>
    </section>
  </section>
  <section id="graph-view" hidden>
  <section class="overview" id="overview" aria-label="Execution summary"></section>
  <div class="assurance-panel" id="assurance-panel"></div>
  <div class="toolbar">
    <div class="group" aria-label="Graph view">
      <button type="button" data-view="focus" aria-pressed="true">Focus</button>
      <button type="button" data-view="star" aria-pressed="false">Star</button>
      <button type="button" data-view="pyramid" aria-pressed="false">Pyramid</button>
      <button type="button" data-view="dependency" aria-pressed="false">Dependencies</button>
    </div>
    <div class="group" aria-label="Status filter">
      <button type="button" data-filter="all" aria-pressed="true">All</button>
      <button type="button" data-filter="ready" aria-pressed="false">Ready</button>
      <button type="button" data-filter="working" aria-pressed="false">Working</button>
      <button type="button" data-filter="paused" aria-pressed="false">Paused</button>
      <button type="button" data-filter="needs-rework" aria-pressed="false">Rework</button>
      <button type="button" data-filter="blocked" aria-pressed="false">Blocked</button>
      <button type="button" data-filter="audit" aria-pressed="false">Audit</button>
      <button type="button" data-filter="work-package" aria-pressed="false">Work packages</button>
      <button type="button" data-filter="verified" aria-pressed="false">Verified</button>
      <button type="button" id="assurance-filter" data-filter="assurance-blocked" aria-pressed="false">Assurance blocked</button>
    </div>
    <div class="group" id="assurance-controls" aria-label="Assurance overlay">
      <button type="button" data-overlay="none" aria-pressed="false">No assurance</button>
      <button type="button" data-overlay="status" aria-pressed="true">Assurance status</button>
      <button type="button" data-overlay="impact" aria-pressed="false">Impact</button>
      <button type="button" data-overlay="inspection" aria-pressed="false">Inspections</button>
      <button type="button" data-overlay="finding" aria-pressed="false">Findings</button>
      <button type="button" data-overlay="drift" aria-pressed="false">Scope drift</button>
    </div>
    <label>Selected node<select id="node-select"></select></label>
  </div>
  <div class="layout">
    <section class="plot" aria-label="Task graph">
      <svg id="graph" viewBox="0 0 1000 720" role="img" aria-labelledby="graph-title graph-desc">
        <title id="graph-title">Pyramid task graph</title>
        <desc id="graph-desc">Interactive graph of task outcomes, dependencies, execution, verification, and blockers.</desc>
        <g id="level-layer"></g><g id="edge-layer"></g><g id="node-layer"></g>
      </svg>
      <div class="legend" aria-label="Status legend">
        <span class="swatch"><span class="dot ready"></span>Ready</span>
        <span class="swatch"><span class="dot working"></span>Working</span>
        <span class="swatch"><span class="dot paused"></span>Paused / handoff</span>
        <span class="swatch"><span class="dot rework"></span>Needs rework</span>
        <span class="swatch"><span class="dot verified"></span>Verified</span>
        <span class="swatch"><span class="dot blocked"></span>Blocked</span>
        <span class="swatch"><span class="dot"></span>Locked or inactive</span>
        <span class="swatch">Dashed ring: brownfield assurance</span>
      </div>
    </section>
    <aside class="detail" id="detail" aria-live="polite"></aside>
  </div>
  </section>
</main>
<script id="pyramid-data" type="application/json">__GRAPH_DATA__</script>
<script>
(() => {
  let data = JSON.parse(document.getElementById('pyramid-data').textContent);
  const liveMode = __LIVE_MODE__;
  const svg = document.getElementById('graph');
  const nodeLayer = document.getElementById('node-layer');
  const edgeLayer = document.getElementById('edge-layer');
  const levelLayer = document.getElementById('level-layer');
  const detail = document.getElementById('detail');
  const select = document.getElementById('node-select');
  const assurancePanel = document.getElementById('assurance-panel');
  const assuranceControls = document.getElementById('assurance-controls');
  const assuranceFilterButton = document.getElementById('assurance-filter');
  const overview = document.getElementById('overview');
  const observerView = document.getElementById('observer-view');
  const graphView = document.getElementById('graph-view');
  const observerSummary = document.getElementById('observer-summary');
  const outcomePath = document.getElementById('outcome-path');
  const workingList = document.getElementById('working-list');
  const attentionList = document.getElementById('attention-list');
  const recommendedAction = document.getElementById('recommended-action');
  const structureTree = document.getElementById('structure-tree');
  const observerDetail = document.getElementById('observer-detail');
  let nodeById = new Map(data.nodes.map(node => [node.id, node]));
  let surface = 'observer';
  let view = 'focus';
  let filter = 'all';
  let overlay = data.assurance ? 'status' : 'none';
  let selected = preferredNode(data).id;
  let positions = new Map();
  let canvas = {width: 1000, height: 720};
  let changedNodeIds = new Set();

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  }
  function preferredNode(graph) {
    const recommendedId = graph.observer?.recommended?.id;
    if (recommendedId && graph.nodes.some(node => node.id === recommendedId)) {
      return graph.nodes.find(node => node.id === recommendedId);
    }
    const priorities = ['working', 'needs-rework', 'ready', 'paused', 'blocked', 'locked'];
    for (const availability of priorities) {
      const match = graph.nodes.find(node => node.availability === availability && node.selection === 'primary');
      if (match) return match;
    }
    return graph.nodes.find(node => node.id === graph.intent.id) || graph.nodes[0];
  }
  function statusLabel(status) {
    return ({
      'verified': 'Verified', 'in-progress': 'In progress', 'proof-pending': 'Proof pending',
      'ready-for-proof': 'Ready for proof', 'work-ready': 'Work ready', 'ready': 'Ready', 'needs-attention': 'Needs attention',
      'working': 'Working', 'paused': 'Paused', 'needs-rework': 'Needs rework',
      'blocked': 'Blocked', 'locked': 'Waiting', 'implemented': 'Awaiting audit',
      'planned': 'Planned', 'pending': 'Pending', 'passed': 'Passed', 'failed': 'Failed',
      'unverified': 'Not yet verified'
    })[status] || String(status || 'Unknown').replaceAll('-', ' ');
  }
  function targetText(item) {
    return item?.target_outcome ? `Supports ${esc(item.target_outcome.title)}` : 'Supports the final intent';
  }
  function renderObserver() {
    const observer = data.observer;
    if (!observer) return;
    const last = observer.last_verified;
    const next = observer.next_outcome;
    observerSummary.innerHTML = `
      <article class="story-card ${last ? 'verified' : ''}">
        <div class="eyebrow">Last proven</div>
        <h2>${last ? esc(last.title) : 'No outcome has passed its audit yet'}</h2>
        <p>${last ? esc(last.summary) : 'Progress is visible, but no usable outcome is claimed without passing proof.'}</p>
        ${last ? `<button type="button" data-node-id="${esc(last.id)}">Inspect accepted proof</button>` : ''}
      </article>
      <article class="story-card ${next?.status === 'needs-attention' ? 'attention' : ''}">
        <div class="eyebrow">Next proof</div>
        <h2>${next ? esc(next.title) : observer.intent.verified ? 'Intent is verified' : 'No outcome milestone is declared'}</h2>
        <p>${next ? esc(next.gate?.summary || 'This outcome has no explicit audit gate.') : observer.intent.verified ? 'The final intent and its required evidence have passed.' : 'Inspect the plan structure and add outcome gates when a runnable ladder is intended.'}</p>
        ${next ? `<span class="proof-status">${esc(statusLabel(next.status))}</span>` : ''}
      </article>
      <article class="story-card ${observer.progress.attention ? 'attention' : ''}">
        <div class="eyebrow">Current picture</div>
        <h2>${esc(observer.progress.label)}</h2>
        <p>${observer.progress.working} actively working · ${observer.progress.ready} ready · ${observer.progress.attention} need attention</p>
        <small>Evidence-backed counts; no estimated completion percentage.</small>
      </article>`;

    const stages = observer.outcomes || [];
    outcomePath.innerHTML = stages.length ? stages.map((stage, index) => `
      <button type="button" class="outcome-step ${esc(stage.status)}" data-node-id="${esc(stage.id)}">
        <small>Outcome ${index + 1} · ${esc(statusLabel(stage.status))}</small>
        <strong>${esc(stage.title)}</strong>
        <span>${stage.gate ? `Proof: ${esc(statusLabel(stage.gate.verification || stage.gate.availability))}` : 'Proof gate missing'}</span>
      </button>`).join('') + `
      <button type="button" class="outcome-step ${observer.intent.verified ? 'verified' : 'planned'}" data-node-id="${esc(observer.intent.id)}">
        <small>Final intent · ${observer.intent.verified ? 'Verified' : 'Not yet verified'}</small>
        <strong>${esc(data.title)}</strong>
        <span>${observer.intent.verified ? 'Success evidence accepted' : 'Requires the complete outcome path'}</span>
      </button>` : `
      <div class="empty-state">No explicit outcome milestones are present. The task tree remains available below, but the dashboard will not invent a runnable increment from waves or status counts.</div>`;

    workingList.innerHTML = observer.working.length ? observer.working.map(item => `
      <button type="button" class="semantic-item work" data-node-id="${esc(item.id)}">
        <strong>${esc(item.title)}</strong>
        <span>${esc(item.owner || 'Unassigned')} · ${targetText(item)}</span>
      </button>`).join('') : '<p class="empty-state">No task is currently claimed as working.</p>';

    attentionList.innerHTML = observer.attention.length ? observer.attention.map(item => `
      ${item.id === 'CHANGE-ASSURANCE' ? '<div' : `<button type="button" data-node-id="${esc(item.id)}"`} class="semantic-item issue">
        <strong>${esc(item.type)} · ${esc(item.title)}</strong>
        <span>${esc(item.reason)}</span>
      ${item.id === 'CHANGE-ASSURANCE' ? '</div>' : '</button>'}`).join('') : '<p class="empty-state">No failed proof, blocker, risk, or paused handoff is recorded.</p>';

    const recommended = observer.recommended;
    recommendedAction.innerHTML = recommended ? `
      <div class="recommended-action">
        <span class="proof-status">${esc(statusLabel(recommended.availability))}</span>
        <strong>${esc(recommended.title)}</strong>
        <p>${esc(recommended.reason)}</p>
        <span>${targetText(recommended)}</span>
        <p><button type="button" data-node-id="${esc(recommended.id)}">Inspect task</button></p>
      </div>` : '<p class="empty-state">No next action is available from the current graph.</p>';

    renderStructure();
    renderObserverDetail();
    document.querySelectorAll('#observer-view [data-node-id]').forEach(button => {
      button.addEventListener('click', () => choose(button.dataset.nodeId));
    });
  }
  function renderStructure() {
    const primaryIds = new Set(data.nodes.filter(node => node.selection === 'primary').map(node => node.id));
    const visited = new Set();
    function structureStatus(node) {
      if (node.kind === 'intent') return data.observer?.intent?.verified ? 'Verified' : 'Final intent';
      if (node.kind === 'outcome') {
        const stage = data.observer?.outcomes?.find(item => item.id === node.id);
        return statusLabel(stage?.status || 'planned');
      }
      return statusLabel(node.availability);
    }
    function branch(id) {
      const node = nodeById.get(id);
      if (!node || !primaryIds.has(id)) return '';
      if (visited.has(id)) return `<li><button type="button" class="tree-node" data-node-id="${esc(id)}">↳ ${esc(node.title)} <span class="tree-status">shared</span></button></li>`;
      visited.add(id);
      const children = (node.children || []).filter(child => primaryIds.has(child)).sort((a, b) => {
        const left = nodeById.get(a), right = nodeById.get(b);
        return (left?.wave || 0) - (right?.wave || 0) || (left?.title || '').localeCompare(right?.title || '');
      });
      return `<li><button type="button" class="tree-node ${id === selected ? 'selected' : ''}" data-node-id="${esc(id)}">
        ${esc(node.title)} <span class="tree-status">${esc(structureStatus(node))}</span></button>
        ${children.length ? `<ul>${children.map(branch).join('')}</ul>` : ''}</li>`;
    }
    structureTree.innerHTML = branch(data.intent.id) || '<li class="empty-state">The intent structure is unavailable.</li>';
  }
  function renderObserverDetail() {
    const node = nodeById.get(selected);
    if (!node) return;
    const target = (node.goal_trace || []).map(id => nodeById.get(id)).find(item => item?.kind === 'outcome' && item.id !== node.id);
    const stage = data.observer?.outcomes?.find(item => item.id === node.id);
    const proof = node.proof || {};
    const implementation = proof.implementation_checks || {passed: 0, failed: 0, total: 0};
    const acceptance = proof.acceptance_checks || {passed: 0, failed: 0, total: 0};
    const audit = proof.audit_checks || {passed: 0, failed: 0, total: 0};
    const sourceHref = node.source_path && liveMode
      ? `/project/${node.source_path.split('/').map(encodeURIComponent).join('/')}`
      : node.source_path ? `../${node.source_path}` : '';
    const stageGate = stage?.gate;
    observerDetail.innerHTML = `
      <div class="eyebrow">Selected work</div>
      <h2>${esc(node.title)}</h2>
      <span class="proof-status">${esc(statusLabel(stage?.status || node.availability))}</span>
      <p>${esc(node.summary)}</p>
      <p><strong>Why it matters:</strong> ${target ? `supports ${esc(target.title)}` : node.id === data.intent.id ? 'this is the final intent' : 'supports the intent path'}</p>
      ${node.state.blocker ? `<p><strong>Issue:</strong> ${esc(node.state.blocker)}</p>` : ''}
      <div class="proof-grid">
        <div class="proof-metric"><strong>${implementation.passed}/${implementation.total}</strong><span>implementation checks</span></div>
        <div class="proof-metric"><strong>${acceptance.passed}/${acceptance.total}</strong><span>acceptance checks</span></div>
        <div class="proof-metric"><strong>${audit.passed}/${audit.total}</strong><span>audit checks</span></div>
      </div>
      <strong>Definition of done for this work</strong>
      ${list(node.acceptance_criteria, item => esc(item.description))}
      <strong>Required proof</strong>
      ${list(node.required_evidence, item => `${esc(item.type)} — ${esc(item.description)}`)}
      ${stageGate ? `<strong>Outcome gate · ${esc(stageGate.title)}</strong><p>${esc(stageGate.summary)}</p>${list(stageGate.required_evidence, item => `${esc(item.type)} — ${esc(item.description)}`)}` : ''}
      ${sourceHref ? `<p><a href="${esc(sourceHref)}">Open generated task</a></p>` : ''}
      <details class="technical-details"><summary>Technical details</summary>
        <dl><dt>ID</dt><dd>${esc(node.id)}</dd><dt>Kind</dt><dd>${esc(node.kind)}</dd>
        <dt>Level / wave</dt><dd>${node.level} / ${node.wave}</dd><dt>Workstream</dt><dd>${esc(node.workstream)}</dd>
        <dt>Execution</dt><dd>${esc(node.state.execution)}</dd><dt>Verification</dt><dd>${esc(node.state.verification)}</dd>
        <dt>Graph</dt><dd>revision ${data.revision} · version ${data.graph_version}</dd></dl>
      </details>`;
  }
  function renderOverview() {
    const count = status => data.nodes.filter(node => {
      if (status === 'blocked') return node.availability === 'blocked' || node.availability === 'locked';
      return node.availability === status;
    }).length;
    const recommended = preferredNode(data);
    const metrics = [
      ['working', 'Working'], ['ready', 'Ready'], ['paused', 'Paused'],
      ['needs-rework', 'Rework'], ['blocked', 'Blocked / locked']
    ];
    overview.innerHTML = metrics.map(([status, label]) => `
      <button type="button" class="metric" data-summary-filter="${status}">
        <strong>${count(status)}</strong><span>${label}</span>
      </button>`).join('') + `
      <button type="button" class="recommended ${esc(recommended.availability)}" data-recommended="${esc(recommended.id)}">
        <span>Recommended focus · ${esc(recommended.availability)}</span>
        <strong>${esc(recommended.title)}</strong>
        <span>${esc(recommended.id)}</span>
      </button>`;
    overview.querySelectorAll('[data-summary-filter]').forEach(button => {
      button.addEventListener('click', () => setFilter(button.dataset.summaryFilter));
    });
    overview.querySelector('[data-recommended]')?.addEventListener('click', event => {
      setFilter('all', false);
      choose(event.currentTarget.dataset.recommended);
    });
  }
  function syncChrome() {
    document.getElementById('page-title').textContent = data.title;
    document.getElementById('intent-statement').textContent = data.observer?.intent?.statement || '';
    const projectMode = data.project?.mode || 'legacy';
    document.getElementById('page-meta').textContent = `${projectMode} project · ${data.lifecycle.status} · ${data.observer?.progress?.label || 'progress unavailable'}`;
    assurancePanel.className = 'assurance-panel';
    assurancePanel.replaceChildren();
    assuranceControls.hidden = !data.assurance;
    assuranceFilterButton.hidden = !data.assurance;
    if (data.assurance) {
      const summary = data.assurance.summary;
      assurancePanel.classList.add('visible', summary.status);
      assurancePanel.innerHTML = `<strong>Change assurance: ${esc(summary.status)}</strong> baseline r${summary.baseline_revision} (${esc(summary.baseline_status)}) · ${summary.sufficiently_inspected_assets}/${summary.impacted_assets} impacted assets sufficiently inspected · ${summary.open_scope_drift} open drift · ${summary.open_material_findings} material findings`;
    }
    select.replaceChildren();
    data.nodes.forEach(node => {
      const option = document.createElement('option');
      option.value = node.id;
      option.textContent = `${node.title} — ${node.id}`;
      select.appendChild(option);
    });
    select.value = selected;
    document.querySelectorAll('[data-overlay]').forEach(button => {
      button.disabled = !data.assurance;
      button.setAttribute('aria-pressed', String(button.dataset.overlay === overlay));
    });
    renderOverview();
    renderObserver();
  }
  function applyData(nextData) {
    const previous = nodeById;
    changedNodeIds = new Set(nextData.nodes.filter(node => {
      const before = previous.get(node.id);
      return !before || JSON.stringify(before) !== JSON.stringify(node);
    }).map(node => node.id));
    data = nextData;
    nodeById = new Map(data.nodes.map(node => [node.id, node]));
    if (!nodeById.has(selected)) selected = preferredNode(data).id;
    if (!data.assurance) overlay = 'none';
    syncChrome();
    render();
    window.setTimeout(() => changedNodeIds.clear(), 1600);
  }
  function starPoints(cx, cy, outer, inner) {
    const points = [];
    for (let i = 0; i < 10; i++) {
      const angle = -Math.PI / 2 + i * Math.PI / 5;
      const radius = i % 2 === 0 ? outer : inner;
      points.push(`${cx + Math.cos(angle) * radius},${cy + Math.sin(angle) * radius}`);
    }
    return points.join(' ');
  }
  function visible(node) {
    if (filter === 'all') return true;
    if (filter === 'audit') return node.kind === 'audit';
    if (filter === 'work-package') return node.kind === 'work-package';
    if (filter === 'assurance-blocked') return node.assurance?.status === 'blocked';
    if (filter === 'blocked') return node.availability === 'blocked' || node.availability === 'locked';
    return node.availability === filter;
  }
  function computePositions() {
    const map = new Map();
    if (view === 'focus') {
      const focus = nodeById.get(selected) || preferredNode(data);
      const relatedIds = new Set([
        focus.id,
        ...(focus.goal_trace || []),
        ...(focus.parents || []),
        ...(focus.children || []),
        ...(focus.blocked_by || []),
        ...(focus.audit_gates || []),
        ...(focus.dependencies || []).map(item => item.id)
      ]);
      data.edges.forEach(edge => {
        if (edge.from === focus.id || edge.to === focus.id) {
          relatedIds.add(edge.from); relatedIds.add(edge.to);
        }
      });
      const related = data.nodes
        .filter(node => relatedIds.has(node.id) && node.id !== focus.id)
        .sort((a,b) => a.level-b.level || a.wave-b.wave || a.id.localeCompare(b.id));
      const rings = Math.max(1, Math.ceil(related.length / 10));
      const width = Math.max(1000, 720 + rings * 180);
      const height = Math.max(620, 480 + rings * 130);
      const cx = width / 2, cy = height / 2;
      map.set(focus.id, {x: cx, y: cy});
      related.forEach((node, index) => {
        const ring = Math.floor(index / 10);
        const members = Math.min(10, related.length - ring * 10);
        const offset = index % 10;
        const radius = 175 + ring * 120;
        const angle = -Math.PI / 2 + offset * Math.PI * 2 / members;
        map.set(node.id, {x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius});
      });
      return {map, width, height};
    } else if (view === 'star') {
      const groups = new Map();
      data.nodes.forEach(node => {
        if (!groups.has(node.level)) groups.set(node.level, []);
        groups.get(node.level).push(node);
      });
      const levels = [...groups.keys()].sort((a,b) => a-b);
      const radii = new Map();
      let previous = 0;
      levels.filter(level => level > 0).forEach(level => {
        const count = groups.get(level).length;
        const circumferenceRadius = count * 92 / (Math.PI * 2);
        const radius = Math.max(92 + (level - 1) * 108, previous + 108, circumferenceRadius);
        radii.set(level, radius);
        previous = radius;
      });
      const outer = Math.max(270, previous);
      const width = Math.max(1000, outer * 2 + 190);
      const height = width;
      const cx = width / 2, cy = height / 2;
      levels.forEach(level => {
        const nodes = groups.get(level);
        nodes.sort((a,b) => a.wave-b.wave || a.id.localeCompare(b.id));
        if (level === 0) { nodes.forEach(node => map.set(node.id, {x: cx, y: cy})); return; }
        const radius = radii.get(level);
        nodes.forEach((node, index) => {
          const angle = -Math.PI / 2 + (index * Math.PI * 2 / nodes.length) + level * 0.17;
          map.set(node.id, {x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius});
        });
      });
      return {map, width, height};
    } else if (view === 'pyramid') {
      const groups = new Map();
      data.nodes.forEach(node => {
        if (!groups.has(node.level)) groups.set(node.level, []);
        groups.get(node.level).push(node);
      });
      const levels = [...groups.keys()].sort((a,b) => a-b);
      const largestLevel = Math.max(...levels.map(level => groups.get(level).length));
      const width = Math.max(1000, largestLevel * 155 + 140);
      levels.forEach((level, levelIndex) => {
        const nodes = groups.get(level).sort((a,b) => a.wave-b.wave || a.id.localeCompare(b.id));
        const span = Math.max(140, (nodes.length - 1) * 150);
        nodes.forEach((node, index) => {
          const x = nodes.length === 1 ? width/2 : width/2 - span/2 + index * span/(nodes.length-1);
          map.set(node.id, {x, y: 85 + levelIndex * 145});
        });
      });
      return {map, width, height: Math.max(430, 155 + (levels.length - 1) * 145)};
    } else {
      const workstreams = [...new Set(data.nodes.map(node => node.workstream))].sort();
      const waves = [...new Set(data.nodes.map(node => node.wave))].sort((a,b) => a-b);
      const rowCounts = new Map();
      data.nodes.slice().sort((a,b) => a.id.localeCompare(b.id)).forEach(node => {
        const key = `${node.wave}:${node.workstream}`;
        const offset = rowCounts.get(key) || 0;
        rowCounts.set(key, offset + 1);
        map.set(node.id, {x: 110 + waves.indexOf(node.wave) * 190, y: 80 + workstreams.indexOf(node.workstream) * 125 + offset * 32});
      });
      return {
        map,
        width: Math.max(1000, 220 + Math.max(0, waves.length - 1) * 190),
        height: Math.max(430, 130 + workstreams.length * 125)
      };
    }
  }
  function render() {
    const layout = computePositions();
    positions = layout.map;
    canvas = {width: layout.width, height: layout.height};
    svg.setAttribute('viewBox', `0 0 ${canvas.width} ${canvas.height}`);
    svg.style.minWidth = `${Math.max(680, canvas.width)}px`;
    edgeLayer.replaceChildren(); nodeLayer.replaceChildren(); levelLayer.replaceChildren();
    const highlight = new Set(nodeById.get(selected)?.goal_trace || []);
    data.edges.forEach(edge => {
      const a = positions.get(edge.from), b = positions.get(edge.to);
      if (!a || !b) return;
      const sourceVisible = visible(nodeById.get(edge.from));
      const targetVisible = visible(nodeById.get(edge.to));
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
      line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
      line.setAttribute('class', `edge ${edge.type === 'contributes-to' ? '' : 'dependency'} ${highlight.has(edge.from) && highlight.has(edge.to) ? 'highlight' : ''}`);
      if (!sourceVisible || !targetVisible) line.style.opacity = '.08';
      edgeLayer.appendChild(line);
    });
    data.nodes.forEach(node => {
      const p = positions.get(node.id);
      if (!p) return;
      const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      const classes = ['node', node.availability, node.kind === 'audit' ? 'audit' : '', node.kind === 'work-package' ? 'work-package' : '', `verification-${node.state.verification}`, node.selection !== 'primary' ? 'not-selected' : '', node.id === selected ? 'selected' : '', changedNodeIds.has(node.id) ? 'changed' : ''].filter(Boolean);
      const assuranceStatus = node.assurance?.status;
      if (assuranceStatus) classes.push(`assurance-${assuranceStatus}`);
      const overlayRecords = overlay === 'impact' ? node.assurance?.impact_ids : overlay === 'inspection' ? node.assurance?.inspection_ids : overlay === 'finding' ? node.assurance?.finding_ids : overlay === 'drift' ? node.assurance?.scope_drift_ids : null;
      if (overlay === 'none' || (overlayRecords && !overlayRecords.length)) classes.push('assurance-hidden');
      group.setAttribute('class', classes.join(' '));
      group.dataset.id = node.id;
      group.style.opacity = visible(node) ? '' : '.08';
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = `${node.id}: ${node.title}; ${node.availability}; verification ${node.state.verification}`;
      group.appendChild(title);
      const ring = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      ring.setAttribute('class', 'verify'); ring.setAttribute('cx', p.x); ring.setAttribute('cy', p.y); ring.setAttribute('r', node.level === 0 ? 25 : 20);
      group.appendChild(ring);
      const assure = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      assure.setAttribute('class', 'assure'); assure.setAttribute('cx', p.x); assure.setAttribute('cy', p.y); assure.setAttribute('r', node.level === 0 ? 30 : 25);
      group.appendChild(assure);
      const mark = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      mark.setAttribute('class', 'mark'); mark.setAttribute('points', starPoints(p.x, p.y, node.level === 0 ? 22 : 17, node.level === 0 ? 10 : 8));
      group.appendChild(mark);
      const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      label.setAttribute('x', p.x); label.setAttribute('y', p.y + 34); label.setAttribute('text-anchor', 'middle');
      label.textContent = node.title.length > 28 ? node.title.slice(0, 27) + '…' : node.title;
      group.appendChild(label);
      const idLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      idLabel.setAttribute('class', 'node-id'); idLabel.setAttribute('x', p.x); idLabel.setAttribute('y', p.y + 49); idLabel.setAttribute('text-anchor', 'middle');
      idLabel.textContent = node.id.length > 22 ? node.id.slice(0, 21) + '…' : node.id;
      group.appendChild(idLabel);
      group.addEventListener('click', () => choose(node.id));
      nodeLayer.appendChild(group);
    });
    renderDetail();
  }
  function list(items, formatter = item => item) {
    return items?.length ? `<ul>${items.map(item => `<li>${formatter(item)}</li>`).join('')}</ul>` : '<p>None</p>';
  }
  function renderDetail() {
    const node = nodeById.get(selected);
    if (!node) return;
    const sourceHref = node.source_path && liveMode
      ? `/project/${node.source_path.split('/').map(encodeURIComponent).join('/')}`
      : node.source_path ? `../${node.source_path}` : '';
    const source = sourceHref ? `<a href="${esc(sourceHref)}">Open generated task</a>` : '';
    const assurance = node.assurance;
    const pause = node.state.execution === 'paused' ? `
      <strong>Pause handoff</strong>
      <dl>
        <dt>Handoff</dt><dd>${esc(node.state.active_handoff_id || '—')}</dd>
        <dt>Mode</dt><dd>${esc(node.state.pause_mode || '—')}</dd>
        <dt>Paused by</dt><dd>${esc(node.state.paused_by || '—')}</dd>
        <dt>Paused at</dt><dd>${esc(node.state.paused_at || '—')}</dd>
        <dt>Resume deadline</dt><dd>${esc(node.state.resume_deadline || '—')}</dd>
      </dl>` : (node.state.last_handoff ? `<strong>Latest handoff</strong><p>${esc(node.state.last_handoff.id || '—')} · resumed by ${esc(node.state.last_handoff.resumed_by || '—')}</p>` : '');
    const assuranceDetail = assurance ? `
      <strong>Assurance status</strong><p>${esc(assurance.status)}</p>
      <strong>Affected assets</strong>${list(assurance.asset_ids, item => `<code>${esc(item)}</code>`)}
      <strong>Impact records</strong>${list(assurance.impact_ids, item => `<code>${esc(item)}</code>`)}
      <strong>Inspections</strong>${list(assurance.inspection_ids, item => `<code>${esc(item)}</code>`)}
      <strong>Findings</strong>${list(assurance.finding_ids, item => `<code>${esc(item)}</code>`)}
      <strong>Scope drift</strong>${list(assurance.scope_drift_ids, item => `<code>${esc(item)}</code>`)}
      <strong>Assurance blockers</strong>${list(assurance.blockers, item => esc(item))}` : '';
    detail.innerHTML = `
      <h2>${esc(node.id)}: ${esc(node.title)}</h2>
      <p>${esc(node.summary)}</p>
      <dl>
        <dt>Kind</dt><dd>${esc(node.kind)}</dd><dt>Selection</dt><dd>${esc(node.selection)}</dd>
        <dt>Level / wave</dt><dd>${node.level} / ${node.wave}</dd><dt>Workstream</dt><dd>${esc(node.workstream)}</dd>
        <dt>Execution</dt><dd>${esc(node.state.execution)}</dd><dt>Verification</dt><dd>${esc(node.state.verification)}</dd>
        <dt>Health</dt><dd>${esc(node.state.health)}</dd><dt>Availability</dt><dd>${esc(node.availability)}</dd>
        <dt>Owner</dt><dd>${esc(node.state.owner || '—')}</dd>
        <dt>Plan lifecycle</dt><dd>${esc(data.lifecycle.status)}</dd>
      </dl>
      <strong>Goal trace</strong>${list(node.goal_trace, item => esc(item))}
      <strong>Parent nodes</strong>${list(node.parents, item => esc(item))}
      <strong>Child nodes</strong>${list(node.children, item => esc(item))}
      <strong>Blocked by</strong>${list(node.blocked_by, item => esc(item))}
      <strong>Audit gates</strong>${list(node.audit_gates, item => esc(item))}
      <strong>Acceptance</strong>${list(node.acceptance_criteria, item => `<code>${esc(item.id)}</code> — ${esc(item.description)}`)}
      ${pause}
      ${assuranceDetail}
      ${source}`;
  }
  function choose(id) {
    selected = id;
    select.value = id;
    render();
    renderStructure();
    renderObserverDetail();
    document.querySelectorAll('#structure-tree [data-node-id]').forEach(button => {
      button.addEventListener('click', () => choose(button.dataset.nodeId));
    });
  }
  function setFilter(nextFilter, rerender = true) {
    filter = nextFilter;
    document.querySelectorAll('[data-filter]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.filter === filter)));
    if (rerender) render();
  }
  select.addEventListener('change', event => choose(event.target.value));
  document.querySelectorAll('[data-surface]').forEach(button => button.addEventListener('click', () => {
    surface = button.dataset.surface;
    observerView.hidden = surface !== 'observer';
    graphView.hidden = surface !== 'graph';
    document.querySelectorAll('[data-surface]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    if (surface === 'graph') render();
  }));
  document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
    view = button.dataset.view;
    document.querySelectorAll('[data-view]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    render();
  }));
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    setFilter(button.dataset.filter);
  }));
  document.querySelectorAll('[data-overlay]').forEach(button => {
    if (!data.assurance) button.disabled = true;
    button.setAttribute('aria-pressed', String(button.dataset.overlay === overlay));
    button.addEventListener('click', () => {
      overlay = button.dataset.overlay;
      document.querySelectorAll('[data-overlay]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      render();
    });
  });
__LIVE_SCRIPT__
  syncChrome();
  render();
})();
</script>
</body>
</html>
"""


LIVE_SCRIPT = r"""
  const liveStatus = document.getElementById('live-status');
  liveStatus.hidden = false;
  let liveEtag = null;
  function setLiveStatus(mode, message, detail = '') {
    liveStatus.className = `live-status ${mode}`;
    liveStatus.textContent = message;
    liveStatus.title = detail;
  }
  async function refreshLiveGraph() {
    setLiveStatus('syncing', 'Live · syncing…');
    const headers = liveEtag ? {'If-None-Match': liveEtag} : {};
    try {
      const response = await fetch('/api/graph', {cache: 'no-store', headers});
      if (response.status === 304) {
        setLiveStatus('connected', `Live · graph ${data.graph_version} · up to date`);
        return;
      }
      if (!response.ok) throw new Error(`Graph request failed (${response.status})`);
      const nextData = await response.json();
      liveEtag = response.headers.get('ETag');
      applyData(nextData);
      setLiveStatus('connected', `Live · graph ${data.graph_version} · updated just now`);
    } catch (error) {
      setLiveStatus('error', 'Live · refresh failed; showing last valid graph', error.message);
    }
  }
  const events = new EventSource('/events');
  events.addEventListener('ready', event => {
    const publication = JSON.parse(event.data);
    if (publication.graph_version !== data.graph_version) {
      refreshLiveGraph();
      return;
    }
    liveEtag = `"${publication.etag}"`;
    setLiveStatus('connected', `Live · graph ${data.graph_version} · connected`);
  });
  events.addEventListener('graph', () => refreshLiveGraph());
  events.addEventListener('graph-error', event => {
    const publication = JSON.parse(event.data);
    setLiveStatus('error', 'Live · publication rejected; showing last valid graph', publication.message);
  });
  events.onerror = () => setLiveStatus('error', 'Live · reconnecting…', 'The event stream was interrupted.');
"""


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def visualization_snapshot(graph: dict[str, Any]) -> dict[str, Any]:
    node_fields = (
        "id",
        "title",
        "summary",
        "kind",
        "selection",
        "level",
        "wave",
        "workstream",
        "availability",
        "blocked_by",
        "goal_trace",
        "parents",
        "children",
        "dependencies",
        "audit_gates",
        "acceptance_criteria",
        "required_evidence",
        "assurance",
        "source_path",
    )
    state_fields = (
        "execution",
        "verification",
        "health",
        "owner",
        "blocker",
        "updated_at",
        "active_handoff_id",
        "paused_at",
        "paused_by",
        "pause_mode",
        "resume_deadline",
        "last_handoff",
    )
    nodes = []
    for node in graph["nodes"]:
        item = {field: node.get(field) for field in node_fields if field in node}
        item["state"] = {
            field: node.get("state", {}).get(field)
            for field in state_fields
            if field in node.get("state", {})
        }
        item["proof"] = _proof_summary(node)
        nodes.append(item)
    assurance = graph.get("assurance")
    snapshot = {
        "schema": "pyramid-visualization-v2",
        "graph_version": graph["graph_version"],
        "context": graph.get("context"),
        "plan_id": graph.get("plan_id"),
        "title": graph["title"],
        "revision": graph["revision"],
        "intent": {
            "id": graph["intent"]["id"],
            "statement": graph["intent"].get("statement"),
            "success_evidence": graph["intent"].get("success_evidence", []),
        },
        "lifecycle": graph["lifecycle"],
        "summary": graph["summary"],
        "nodes": nodes,
        "edges": graph["edges"],
        "project": {
            "format_version": graph.get("project", {}).get("format_version"),
            "mode": graph.get("project", {}).get("mode", "legacy"),
        },
        "assurance": {"summary": assurance["summary"]} if assurance else None,
    }
    snapshot["observer"] = observer_projection(graph, nodes)
    return snapshot


def load_visualization_graph(project: str | Path) -> dict[str, Any]:
    paths = project_paths(project)
    _, plan, state = load_project(project)
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if lifecycle_status(state) == "archived":
        graph = (
            load_json(paths["graph"])
            if paths["graph"].exists()
            else graph_snapshot(plan, state, baseline, assurance, manifest)
        )
    else:
        graph = compile_and_load_graph(project)
    return visualization_snapshot(graph)


def build_visualization_html(graph: dict[str, Any], *, live: bool = False) -> str:
    graph_json = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    return (
        HTML_TEMPLATE.replace("__LIVE_MODE__", "true" if live else "false")
        .replace("__LIVE_SCRIPT__", LIVE_SCRIPT if live else "")
        .replace("__GRAPH_DATA__", graph_json)
    )


def render_visualization(project: str | Path, output: str | Path | None = None) -> dict[str, Any]:
    paths = project_paths(project)
    graph = load_visualization_graph(project)
    html = build_visualization_html(graph)
    destination = Path(output).expanduser().resolve() if output else paths["html"]
    write_text_atomic(destination, html)
    return {
        "status": "rendered",
        "output": str(destination),
        "graph_version": graph["graph_version"],
        "nodes": len(graph["nodes"]),
        "views": ["observer", "focus", "star", "pyramid", "dependency"],
        "overlays": ["assurance-status", "impact", "inspection", "finding", "scope-drift"],
    }
