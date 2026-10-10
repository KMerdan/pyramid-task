"""Validation fixtures shared by local tests and pinned-baseline qualification."""
from __future__ import annotations

import copy
import json
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validation_cases() -> dict[str, dict]:
    """The 25 predeclared S0 inputs; no project, lock or history fixture."""
    base = load_json(PLUGIN_ROOT / "assets/example-plan.json")
    harness = load_json(PLUGIN_ROOT / "assets/example-harness-plan.json")
    cases = {
        "valid-legacy": base,
        "valid-harness": harness,
        "empty-plan": {},
        "intent-object": {**copy.deepcopy(base), "intent": []},
        "empty-nodes": {**copy.deepcopy(base), "nodes": []},
    }

    def change(name: str, path: list, value, source: dict = base) -> None:
        plan = copy.deepcopy(source)
        item = plan
        for key in path[:-1]:
            item = item[key]
        item[path[-1]] = value
        cases[name] = plan

    change("revision-zero", ["revision"], 0)
    change("schema-unknown", ["schema_version"], 3)
    change("empty-title", ["title"], "")
    change("agent-commands-type", ["nodes", 2, "agent", "commands"], [42])
    change("agent-effect-unknown", ["nodes", 2, "agent", "effect"], "unknown-effect")
    change("generated-asset-ids", ["nodes", 2, "agent", "generated_outputs"],
           [{"pattern": "generated/**", "asset_ids": []}])
    change("unknown-requirement", ["nodes", 2, "source_requirements"], ["REQ-UNKNOWN"])
    change("negative-level", ["nodes", 2, "level"], -1)
    change("bad-node-kind", ["nodes", 2, "kind"], "unknown-kind")
    change("unknown-evidence-confidence", ["evidence", 0, "confidence"], "certain")
    change("unknown-decision-evidence", ["decisions", 0, "evidence"], ["EV-UNKNOWN"])
    change("legacy-with-harness", ["schema_version"], 1, harness)
    change("invalid-proof-criteria", ["nodes", 2, "required_evidence", 0,
                                    "verification", "criteria"], ["AC-UNKNOWN"], harness)
    for name, edge in [
        ("hard-cycle", {"from": "RESEARCH-101", "to": "CONTRACT-102", "type": "requires"}),
        ("self-edge", {"from": "RESEARCH-101", "to": "RESEARCH-101", "type": "requires"}),
        ("unknown-edge", {"from": "RESEARCH-101", "to": "MISSING-999", "type": "requires"}),
    ]:
        plan = copy.deepcopy(base)
        plan["edges"].append(edge)
        cases[name] = plan
    plan = copy.deepcopy(base)
    plan["nodes"].append(copy.deepcopy(plan["nodes"][2]))
    cases["duplicate-node"] = plan
    plan = copy.deepcopy(base)
    plan["edges"] = [edge for edge in plan["edges"] if edge["type"] != "validated-by"]
    cases["missing-joint-gate"] = plan
    plan = copy.deepcopy(base)
    del plan["title"]
    cases["missing-top-field"] = plan
    plan = copy.deepcopy(base)
    plan["edges"].append({"from": [], "to": "RESEARCH-101", "type": "requires"})
    cases["malformed-edge-exception"] = plan
    return cases
