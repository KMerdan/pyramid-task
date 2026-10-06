#!/usr/bin/env python3
"""Read-only planning checks. Outputs a report; never writes canonical state."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parents[2]
INSTALLED = Path("/Users/merdankiji/.codex/plugins/cache/kmerdan-skills/pyramid-task/4.1.0")
before_path = ROOT / "candidate-plan.r2.json"
after_path = ROOT / "candidate-plan.json"
before = json.loads(before_path.read_text())
after = json.loads(after_path.read_text())
errors = []
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

from jsonschema import Draft202012Validator
for owner in (INSTALLED, SOURCE / "plugins/pyramid-task"):
    schema = json.loads((owner / "schemas/plan.schema.json").read_text())
    errors.extend(f"{owner}: {e.json_path}: {e.message}" for e in Draft202012Validator(schema).iter_errors(after))

env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYRAMID_USAGE="off")
runtime_reports = []
for owner in (INSTALLED, SOURCE / "plugins/pyramid-task"):
    script = ("import json,sys;sys.path.insert(0,sys.argv[1]);"
              "import pyramid_core as c;"
              "p=json.load(open(sys.argv[2]));print(json.dumps(c.validate_plan(p)))")
    run = subprocess.run([sys.executable, "-c", script, str(owner / "scripts"), str(after_path)],
                         capture_output=True, text=True, env=env, check=False)
    found = json.loads(run.stdout) if run.returncode == 0 else [run.stderr.strip()]
    runtime_reports.append({"owner": str(owner), "errors": found})
    errors.extend(found)

old_nodes = {n["id"]: n for n in before["nodes"]}
nodes = {n["id"]: n for n in after["nodes"]}
preserved = {
    "intent_id_statement": all(before["intent"][k] == after["intent"][k] for k in ("id", "statement")),
    "requirements": all(r in after["intent"]["success_evidence"] for r in before["intent"]["success_evidence"]),
    "constraints": all(r in after["intent"]["constraints"] for r in before["intent"]["constraints"]),
    "non_goals": all(r in after["intent"]["non_goals"] for r in before["intent"]["non_goals"]),
    "node_ids": set(nodes) == set(old_nodes),
    "topology": before["edges"] == after["edges"],
    "existing_acceptance": all(c in nodes[nid]["acceptance_criteria"] for nid,n in old_nodes.items() for c in n["acceptance_criteria"]),
    "existing_evidence_ids": all(e["id"] in {v["id"] for v in nodes[nid]["required_evidence"]} for nid,n in old_nodes.items() for e in n["required_evidence"]),
}
errors.extend(f"Preservation failed: {k}" for k,v in preserved.items() if not v)

selected = {n["id"] for n in after["nodes"] if n["selection"] == "primary"}
parents = {"intent", "outcome", "capability", "work-package"}
audit_edges = {"requires", "contract-requires", "integration-requires", "validation-requires", "validated-by"}
adj = {nid: set() for nid in selected}
for e in after["edges"]:
    if e["from"] in selected and e["to"] in selected:
        if e["type"] in audit_edges:
            adj[e["from"]].add(e["to"])
        elif e["type"] == "contributes-to" and nodes[e["to"]]["kind"] in parents:
            adj[e["to"]].add(e["from"])
visiting, done, stack, cycles = set(), set(), [], []
def visit(nid):
    if nid in visiting:
        cycles.append(stack[stack.index(nid):] + [nid])
        return
    if nid in done:
        return
    visiting.add(nid)
    stack.append(nid)
    for dep in sorted(adj[nid]):
        visit(dep)
    stack.pop()
    visiting.remove(nid)
    done.add(nid)
for nid in sorted(adj):
    visit(nid)
if cycles:
    errors.append(f"Effective acceptance cycles: {cycles}")

criteria_missing = {}
for nid,n in nodes.items():
    covered = {cid for ev in n["required_evidence"] for cid in ev["verification"]["criteria"]}
    missing = sorted({c["id"] for c in n["acceptance_criteria"]} - covered)
    if missing:
        criteria_missing[nid] = missing
if criteria_missing:
    errors.append(f"Criteria without declared proof: {criteria_missing}")

coverage = []
for req in after["intent"]["success_evidence"]:
    rid = req["id"]
    work = [n["id"] for n in after["nodes"] if rid in n["source_requirements"] and n["kind"] in {"research","contract","implementation","integration","risk-control"}]
    gates = [n["id"] for n in after["nodes"] if rid in n["source_requirements"] and n["kind"] == "audit"]
    outcomes = [n["id"] for n in after["nodes"] if rid in n["source_requirements"] and n["kind"] == "outcome"]
    coverage.append({"requirement": rid, "work": work, "gates": gates, "outcomes": outcomes})
    if not work or not gates or not outcomes:
        errors.append(f"Requirement lacks work/gate/outcome trace: {rid}")

def metrics(p):
    return {"nodes": len(p["nodes"]), "executable_nodes": sum(n["kind"] in {"research","contract","implementation","integration","risk-control","audit"} for n in p["nodes"]),
            "edges":len(p["edges"]), "hard_dependencies":sum(e["type"] in {"requires","contract-requires"} for e in p["edges"]),
            "audit_gates":sum(n["kind"] == "audit" for n in p["nodes"])}
result = {
    "scope": "planning structure and preservation only; no product acceptance or canonical mutation",
    "source_plan_sha256": sha(before_path), "candidate_plan_sha256": sha(after_path),
    "errors": errors, "valid": not errors, "runtime_validation": runtime_reports,
    "preserved": preserved, "acceptance_cycles": cycles, "criteria_missing_proof": criteria_missing,
    "metrics": {"before": metrics(before), "after": metrics(after)}, "coverage": coverage,
    "changed_nodes": [nid for nid in nodes if nodes[nid] != old_nodes[nid]],
    "unchanged_nodes": [nid for nid in nodes if nodes[nid] == old_nodes[nid]],
    "canonical_hashes": {str(p.relative_to(SOURCE)):sha(p) for p in [SOURCE/".pyramid/plan.json",SOURCE/".pyramid/state.json"]},
    "limits": ["Trace checks are structural, not semantic test sufficiency.",
               "Known source counterexamples are not fixed by changing a plan.",
               "No new real-host, visual or human qualification ran.",
               "Doctor could not complete because it requires canonical-root projection/lock writes."]
}
print(json.dumps(result, indent=2))
sys.exit(0 if not errors else 1)
