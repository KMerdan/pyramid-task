"""Explicit value corpus for independent old/new modularization execution.

Fixtures come from shipped examples. No canonical project is initialized.
JSON strings retain mapping order; tagged sets/tuples/paths retain result types.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = "2026-10-10T00:00:00Z"


def load_example(name):
    return json.loads((PLUGIN_ROOT / "assets" / name).read_text())


def state_for(plan):
    return {"schema_version": 1, "graph_version": 1,
            "created_at": FIXED_TIME, "updated_at": FIXED_TIME,
            "nodes": {n["id"]: {
                "execution": "planned", "verification": "unverified", "health": "clear",
                "owner": None, "lease_expires_at": None, "work_origin": None,
                "active_handoff_id": None, "paused_at": None, "paused_by": None,
                "pause_mode": None, "resume_deadline": None, "last_handoff": None,
                "blocker": None, "updated_at": FIXED_TIME, "last_result": None,
                "last_audit": None, "last_reopen": None,
            } for n in plan["nodes"]}}


def normalized(value):
    if isinstance(value, Path):
        return {"$path": str(value)}
    if isinstance(value, set):
        return {"$set": sorted(normalized(x) for x in value)}
    if isinstance(value, tuple):
        return {"$tuple": [normalized(x) for x in value]}
    if isinstance(value, list):
        return [normalized(x) for x in value]
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()}
    return value


def encoded(value):
    return json.dumps(normalized(value), ensure_ascii=False, separators=(",", ":"))


def run_case(api, case):
    args = copy.deepcopy(case["args"])
    calls = []
    def clock():
        calls.append(FIXED_TIME)
        if case.get("clock_raises"):
            raise RuntimeError("oracle clock boundary")
        return FIXED_TIME
    original_clock = api.utc_now
    api.utc_now = clock
    try:
        try:
            value = getattr(api, case["function"])(*args)
            result = {"value_json": encoded(value), "error": None}
        except Exception as exc:
            result = {"value_json": None, "error": {
                "type": type(exc).__name__, "module": type(exc).__module__, "message": str(exc)}}
    finally:
        api.utc_now = original_clock
    return {"name": case["name"], "function": case["function"], **result,
            "args_after_json": encoded(args), "clock_calls": len(calls)}


def value_cases():
    plan = load_example("example-plan.json")
    bound = load_example("example-harness-plan.json")
    baseline = load_example("example-baseline.json")
    assurance = load_example("example-assurance.json")
    expansion = load_example("example-expansion.json")
    state = state_for(plan)
    cases = []
    def add(function, *args, label=None, **extra):
        cases.append({"name": label or f"{function}-{sum(c['function'] == function for c in cases)}",
                      "function": function, "args": copy.deepcopy(list(args)), **extra})
    node = next(n for n in plan["nodes"] if n["id"] == "TASK-201")
    add("default_lifecycle")
    for item in [{}, {"lifecycle": {"status": "completed"}}, {"lifecycle": None}]:
        add("lifecycle_state", item)
        add("lifecycle_status", item)
    for status in ["active", "completed", "archived"]:
        add("require_active", {"lifecycle": {"status": status}}, "change work")
    add("active_claims", state)
    claimed = copy.deepcopy(state)
    claimed["nodes"]["TASK-201"].update(execution="working", owner="worker")
    claimed["nodes"]["RESEARCH-101"].update(execution="paused", owner=None)
    add("active_claims", claimed)
    for value in [{"b": [1, None], "a": "汉字"}, {}, ["x", True]]:
        add("canonical_sha256", value)
    add("canonical_context_id", plan, state)
    add("canonical_context_id", plan, {**state, "context_id": "CTX-" + "A" * 32})
    add("context_identity", plan, state)
    add("context_identity", plan, {**state, "context_id": "CTX-" + "A" * 32})
    add("_guard_token", "task", {"node": node})
    for nid in [n["id"] for n in plan["nodes"]]:
        add("task_mutation_guard", plan, state, nid, None, None)
        add("audit_mutation_guard", plan, state, nid, baseline, assurance, {})
        add("_covered_assurance_tasks", plan, next(n for n in plan["nodes"] if n["id"] == nid))
        add("dependent_claims", plan, nid)
    for expected in [None, "actual", "stale"]:
        add("check_expected_guard", "actual", expected, "task")
    for now in [None, "", "explicit-time"]:
        add("initial_node_state", node, now)
    add("initial_node_state", {**node, "selection": "superseded"}, FIXED_TIME)
    add("clear_active_pause", {"active_handoff_id": "h", "paused_at": "t", "paused_by": "a",
                               "pause_mode": "hold", "resume_deadline": "d", "other": 1})
    add("validate_state", plan, state)
    add("validate_state", bound, state_for(bound))
    for key, value in [("schema_version", 99), ("graph_version", 0), ("context_id", "bad"),
                       ("nodes", None), ("lifecycle", {"status": "unknown"}),
                       ("lifecycle", {"status": "completed"}), ("lifecycle", {"status": "archived"})]:
        changed = copy.deepcopy(state); changed[key] = value
        add("validate_state", plan, changed)
    for key, value in [("execution", "working"), ("execution", "paused"), ("execution", "bad"),
                       ("health", "bad"), ("verification", "bad"), ("owner", "unowned"),
                       ("active_handoff_id", "unexpected")]:
        changed = copy.deepcopy(state); changed["nodes"]["TASK-201"][key] = value
        add("validate_state", plan, changed)
    changed = copy.deepcopy(state); changed["nodes"]["TASK-201"].update(
        execution="paused", pause_mode="hold", paused_at=FIXED_TIME, paused_by="owner",
        owner="other", active_handoff_id="h", resume_deadline="later", lease_expires_at="earlier")
    add("validate_state", plan, changed)
    add("completion_errors", plan, state)
    add("completion_errors", plan, state, baseline, assurance, {})
    for expected in [None, 1, 2, {"graph_version": 1, "context_id": "stale"}, {"graph_version": 2}]:
        add("check_expected_version", plan, state, expected)
    verified = copy.deepcopy(state)
    for item in verified["nodes"].values(): item.update(execution="implemented", verification="passed")
    add("completion_errors", plan, verified)
    add("invalidate_dependent_claims", plan, verified, "TASK-201", "repair dependency")
    add("invalidate_dependent_claims", plan, state, "TASK-201", "no recorded claim")
    add("_edge_key", plan["edges"][0])
    add("_semantic_node", node)
    add("expansion_parent_snapshot", node)
    add("prepare_replan", plan, plan)
    for key, value in [("plan_id", "different"), ("title", ""), ("schema_version", 2)]:
        candidate = copy.deepcopy(plan); candidate[key] = value
        add("prepare_replan", plan, candidate)
    candidate = copy.deepcopy(bound); candidate["schema_version"] = 1
    add("prepare_replan", bound, candidate)
    for key, value in [("schema", "bad"), ("target", "missing"), ("base_graph_version", 2),
                       ("reason", ""), ("trigger_signals", []), ("evidence", None),
                       ("preserved_parent", {}), ("user_decisions", None), ("impact", {}),
                       ("nodes", None), ("audit_gate", "missing"), ("audit_coverage", []),
                       ("internal_edges", [{"from": "TASK-211", "to": "missing", "type": "requires"}]),
                       ("dependency_mapping", [])]:
        proposal = copy.deepcopy(expansion); proposal[key] = value
        add("_expansion_errors", plan, state, proposal)
        add("prepare_expansion", plan, state, proposal)
    add("_expansion_errors", plan, state, expansion)
    add("prepare_expansion", plan, state, expansion)
    add("prepare_expansion", plan, claimed, expansion)
    paths = {"root": Path("/oracle/project"), "docs": Path("/oracle/project/docs/tasks")}
    for value in ["A title", "汉字", "  ", "a/b.c"]:
        add("slugify", value)
    add("_markdown_list", [])
    add("_markdown_list", ["one", "two 汉字"])
    for p in [plan, bound]:
        s = state_for(p)
        for n in p["nodes"]:
            add("goal_trace", p, n["id"])
            add("task_packet", p, s, n["id"])
            add("task_summary", p, s, n["id"])
            add("node_doc_path", paths, n)
            add("render_node_markdown", paths, p, s, n)
        add("graph_snapshot", p, s)
        add("graph_snapshot", p, s, baseline, assurance, {"format_version": 3, "mode": "brownfield"}, {})
    add("task_packet", plan, state, "missing")
    add("task_summary", plan, state, "missing")
    add("task_packet", plan, state, "TASK-201", baseline, assurance, {})
    add("task_summary", plan, state, "TASK-201", baseline, assurance, {})
    invalid_graph = copy.deepcopy(state); del invalid_graph["nodes"]["TASK-201"]
    add("graph_snapshot", plan, invalid_graph, label="graph-error-before-clock")
    add("graph_snapshot", plan, state, label="graph-clock-error", clock_raises=True)
    add("initial_node_state", node, None, label="initial-clock-error", clock_raises=True)
    add("invalidate_dependent_claims", plan, verified, "TASK-201", "r", label="invalidation-clock-error", clock_raises=True)
    report = {"title": "Fixture", "plan_id": plan["plan_id"], "revision": 1, "graph_version": 2,
              "completed_at": FIXED_TIME, "completed_by": "owner", "intent": plan["intent"],
              "success_evidence": [{"id": "REQ-001", "description": "fixture", "covered_by": ["TASK-201"]}],
              "verified_primary_nodes": [{"id": "TASK-201", "title": "Executor"}], "residual_risks": []}
    add("_report_markdown", report)
    dossier = {**report, "dossier_id": "DOSSIER-1", "baseline_before": baseline,
               "baseline_after": {**baseline, "revision": baseline["revision"] + 1},
               "predicted_impacts": [], "actual_changes": [], "inspections": [], "scope_drift": [],
               "findings": [], "controls": assurance["controls"]}
    add("_dossier_markdown", dossier)
    add("_build_change_dossier", plan, verified, baseline, assurance, "owner", FIXED_TIME, "DOSSIER-1")
    add("_completion_report", plan, verified, "owner", FIXED_TIME)
    return cases
