from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jsonschema

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))
import pyramid_core as core
from pyramid_amendment import prepare_amendment
from pyramid_output import compact_response
import pyramid_history


class EfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        core.create_project(self.root, PLUGIN / "assets/example-plan.json", "planner", mode="greenfield")
        self.file = self.root / "src/executor/connection.py"
        self.file.parent.mkdir(parents=True)
        self.file.write_text("# test source\n")
        self.proposal = {
            "schema": "pyramid-amendment-v1", "task": "RESEARCH-101",
            "reason": "Include an existing connection owner discovered during investigation.",
            "boundary_review": "Existing outcome only; no changed acceptance, dependencies, authority or non-goals.",
            "add_write_paths": ["src/executor/connection.py"], "add_context_paths": [],
        }
        self.path = Path(self.temp.name) / "amendment.json"
        self.save()
        self.taken = core.take_task(self.root, "worker", nid="RESEARCH-101")

    def save(self):
        self.path.write_text(json.dumps(self.proposal))

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in (self.root / ".pyramid").rglob("*") if p.is_file() and p.name != "lock"}

    def apply(self):
        preview = core.amend_task(self.root, self.path, "worker")
        return core.amend_task(self.root, self.path, "worker", True, preview["amendment_id"])

    def test_preview_is_read_only_and_apply_preserves_contract_ownership_and_history(self):
        before = self.snapshot()
        _, old_plan, old_state = core.load_project(self.root)
        preview = core.amend_task(self.root, self.path, "worker")
        self.assertEqual(before, self.snapshot())
        self.assertEqual(preview, core.amend_task(self.root, self.path, "worker"))
        result = core.amend_task(self.root, self.path, "worker", True, preview["amendment_id"])
        _, plan, state = core.load_project(self.root)
        expected = copy.deepcopy(old_plan)
        expected["revision"] += 1
        next(n for n in expected["nodes"] if n["id"] == "RESEARCH-101")["agent"]["allowed_write_scope"].append(str(self.file.relative_to(self.root)))
        self.assertEqual(expected, plan)
        for nid, item in old_state["nodes"].items():
            self.assertEqual({k: v for k, v in item.items() if k != "updated_at"},
                             {k: v for k, v in state["nodes"][nid].items() if k != "updated_at"})
        self.assertEqual(old_state["graph_version"] + 1, state["graph_version"])
        event = core.load_json(self.root / ".pyramid/events" / f"{result['event']['id']}.json")
        self.assertEqual(self.proposal, event["payload"]["amendment"])
        self.assertEqual("task.amended", event["type"])
        self.assertNotEqual(self.taken["packet"]["mutation_guard"], result["mutation_guard"])
        validation = core.validate_project(self.root)
        self.assertTrue(validation["valid"], validation["errors"])
        # New guard continues the same claim; the old guard is now invalid.
        with self.assertRaises(core.PyramidError):
            core.update_task(self.root, "RESEARCH-101", "worker", "clear", expected_guard=self.taken["packet"]["mutation_guard"])
        core.update_task(self.root, "RESEARCH-101", "worker", "clear", expected_guard=result["mutation_guard"])

    def test_rejects_semantic_fields_and_malformed_paths_without_mutating(self):
        original = copy.deepcopy(self.proposal)
        candidates = []
        for field in ("acceptance_criteria", "commands", "edges", "non_goals", "effect"):
            candidates.append({**original, field: []})
        for value in ("../outside.py", "/tmp/out.py", "src/**", "src/../out.py", ".", "src//file.py",
                      ".git/config", ".pyramid/plan.json", "docs/tasks/task.md", "src\\file.py", "missing.py"):
            candidates.append({**original, "add_write_paths": [value]})
        candidates.extend([
            {**original, "add_write_paths": []},
            {**original, "add_write_paths": original["add_write_paths"] * 2},
            {**original, "boundary_review": " "},
            {**original, "task": "MISSING-001"},
        ])
        before = self.snapshot()
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.proposal = candidate
                self.save()
                with self.assertRaises(core.PyramidError):
                    core.amend_task(self.root, self.path, "worker")
                self.assertEqual(before, self.snapshot())

    def test_rejects_symlinks_and_directories(self):
        link = self.root / "alias.py"
        link.symlink_to(self.file)
        for value in ("alias.py", "src/executor"):
            self.proposal["add_write_paths"] = [value]
            self.save()
            with self.assertRaisesRegex(core.PyramidError, "non-symlink"):
                core.amend_task(self.root, self.path, "worker")

    def test_preview_token_binds_state_proposal_and_actor(self):
        preview = core.amend_task(self.root, self.path, "worker")
        before = self.snapshot()
        for token in (None, "AMEND-wrong"):
            with self.assertRaises(core.PyramidError):
                core.amend_task(self.root, self.path, "worker", True, token)
        with self.assertRaises(core.PyramidError):
            core.amend_task(self.root, self.path, "other", True, preview["amendment_id"])
        self.assertEqual(before, self.snapshot())
        self.proposal["reason"] += " Revised."
        self.save()
        with self.assertRaisesRegex(core.PyramidError, "Stale"):
            core.amend_task(self.root, self.path, "worker", True, preview["amendment_id"])
        preview = core.amend_task(self.root, self.path, "worker")
        core.update_task(self.root, "RESEARCH-101", "worker", "at-risk", reason="New evidence")
        with self.assertRaisesRegex(core.PyramidError, "Stale"):
            core.amend_task(self.root, self.path, "worker", True, preview["amendment_id"])

    def test_already_covered_scope_needs_no_amendment(self):
        paths, plan, state = core.load_project(self.root)
        next(n for n in plan["nodes"] if n["id"] == "RESEARCH-101")["agent"]["allowed_write_scope"].append("src/executor/**")
        with mock.patch.object(core, "load_project", return_value=(paths, plan, state)):
            with self.assertRaisesRegex(core.PyramidError, "already permitted"):
                core.amend_task(self.root, self.path, "worker")

    def test_amendment_remains_a_history_turning_point(self):
        result = self.apply()
        _, plan, state = core.load_project(self.root)
        events = pyramid_history._event_records(self.root / ".pyramid/events")
        journey = pyramid_history._journey(plan, state, events)
        self.assertIn(result["event"]["id"], [event["id"] for event in journey["turning_points"]])

    def test_completed_paused_unowned_and_expired_work_cannot_amend(self):
        # Inject states at the read boundary without corrupting a canonical fixture.
        paths, plan, state = core.load_project(self.root)
        for execution in ("paused", "implemented", "planned"):
            candidate = copy.deepcopy(state)
            candidate["nodes"]["RESEARCH-101"]["execution"] = execution
            with mock.patch.object(core, "load_project", return_value=(paths, plan, candidate)):
                with self.assertRaises(core.PyramidError):
                    core.amend_task(self.root, self.path, "worker")
        for status in ("completed", "archived"):
            candidate = copy.deepcopy(state)
            candidate["lifecycle"]["status"] = status
            with mock.patch.object(core, "load_project", return_value=(paths, plan, candidate)):
                with self.assertRaises(core.PyramidError):
                    core.amend_task(self.root, self.path, "worker")
        candidate = copy.deepcopy(state)
        candidate["nodes"]["RESEARCH-101"]["lease_expires_at"] = "2000-01-01T00:00:00Z"
        with mock.patch.object(core, "load_project", return_value=(paths, plan, candidate)):
            with self.assertRaisesRegex(core.PyramidError, "unexpired"):
                core.amend_task(self.root, self.path, "worker")

    def test_active_write_and_generated_output_conflicts_are_rejected(self):
        paths, plan, state = core.load_project(self.root)
        for execution in ("working", "paused"):
            for field in ("allowed_write_scope", "generated_outputs"):
                candidate, candidate_state = copy.deepcopy(plan), copy.deepcopy(state)
                other = next(n for n in candidate["nodes"] if n["id"] == "CONTRACT-102")
                other["agent"]["allowed_write_scope"] = []
                other["agent"][field] = (["src/executor/**"] if field == "allowed_write_scope"
                                          else [{"pattern": "src/executor/**", "asset_ids": []}])
                candidate_state["nodes"]["CONTRACT-102"]["execution"] = execution
                with mock.patch.object(core, "load_project", return_value=(paths, candidate, candidate_state)):
                    with self.assertRaisesRegex(core.PyramidError, "conflicts with active"):
                        core.amend_task(self.root, self.path, "worker")

    def brownfield(self):
        root = Path(self.temp.name) / "brownfield"
        core.create_project(root, PLUGIN / "assets/example-plan.json", "planner", mode="brownfield",
                            baseline_path=PLUGIN / "assets/example-baseline.json",
                            assurance_path=PLUGIN / "assets/example-assurance.json")
        target = root / "src/executor/connection.py"
        target.parent.mkdir(parents=True)
        target.write_text("# source\n")
        core.take_task(root, "worker", nid="RESEARCH-101")
        self.root = root

    def test_brownfield_preserves_mapping_but_stales_affected_inspections(self):
        self.brownfield()
        result = self.apply()
        self.assertEqual(["INSPECTION-001"], result["stale_inspections"])
        assurance = core.load_json(self.root / ".pyramid/assurance.json")
        self.assertEqual("stale", assurance["inspections"][0]["status"])
        self.assertTrue(core.validate_project(self.root)["valid"])

    def test_brownfield_rejects_unmapped_asset(self):
        self.brownfield()
        (self.root / "other.py").write_text("# unmapped\n")
        self.proposal["add_write_paths"] = ["other.py"]
        self.save()
        before = self.snapshot()
        with self.assertRaisesRegex(core.PyramidError, "impact mapping"):
            self.apply()
        self.assertEqual(before, self.snapshot())

    def test_context_only_addition_preserves_inspections(self):
        self.brownfield()
        self.proposal["add_context_paths"] = self.proposal["add_write_paths"]
        self.proposal["add_write_paths"] = []
        self.save()
        before = (self.root / ".pyramid/assurance.json").read_bytes()
        self.assertEqual([], self.apply()["stale_inspections"])
        self.assertEqual(before, (self.root / ".pyramid/assurance.json").read_bytes())

    def test_compact_update_retains_safety_and_full_results_stay_on_disk(self):
        full = core.update_task(self.root, "RESEARCH-101", "worker", "blocked", reason="Missing provider credentials")
        original = copy.deepcopy(full)
        compact = compact_response(full, "update")
        self.assertEqual(original, full)
        self.assertLess(len(json.dumps(compact)), 0.8 * len(json.dumps(full)))
        for key in ("blocker", "blocked_by", "health", "execution", "verification", "dependencies", "mutation_guards"):
            self.assertEqual(full["packet"][key], compact["packet"][key])
        self.assertEqual(full["event"]["payload"], compact["event"]["payload"])
        self.assertEqual(full["event"], core.load_json(self.root / compact["event"]["path"]))
        for schema, value in (("agent-status", compact["packet"]), ("event-reference", compact["event"]), ("amendment", self.proposal)):
            jsonschema.validate(value, core.load_json(PLUGIN / "schemas" / f"{schema}.schema.json"))

    def test_compact_take_keeps_entire_task_contract(self):
        self.assertEqual(self.taken["packet"], compact_response(self.taken, "take")["packet"])
        self.assertEqual(self.taken["packet"], compact_response(self.taken, "resume")["packet"])

    def test_compact_is_a_noop_when_projection_would_add_overhead(self):
        preview = core.amend_task(self.root, self.path, "worker")
        self.assertEqual(preview, compact_response(preview, "amend"))
        full = {"event": {"schema": "pyramid-event-v1", "id": "EV-1", "before": {}, "after": {}}}
        self.assertEqual(full, compact_response(full, "create"))

    def test_compact_keeps_full_packet_when_another_mutation_intervenes(self):
        full = core.update_task(self.root, "RESEARCH-101", "worker", "clear")
        path = self.root / "context.txt"
        path.write_text("new required context")
        self.proposal["add_write_paths"] = []
        self.proposal["add_context_paths"] = ["context.txt"]
        self.save()
        self.apply()
        # Reproduce a packet assembled after a concurrent contract change.
        full["packet"] = core.inspect_project(self.root, nid="RESEARCH-101")
        compact = compact_response(full, "update")
        self.assertEqual(full["packet"], compact["packet"])
        self.assertEqual("agent-task-v1", compact["packet"]["schema"])
        self.assertIn("context.txt", compact["packet"]["required_context"])

    def test_malformed_amendment_roots_are_rejected_cleanly(self):
        plan = core.load_project(self.root)[1]
        for proposal in (None, [], "proposal", 123):
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                prepare_amendment(plan, proposal)

    def test_compact_brownfield_keeps_assurance_and_unknown_warnings(self):
        self.brownfield()
        full = core.update_task(self.root, "RESEARCH-101", "worker", "at-risk", reason="Review needed")
        full["warnings"] = ["Unknown future safety field"]
        result = compact_response(full, "update")
        self.assertEqual(full["packet"]["assurance"], result["packet"]["assurance"])
        self.assertEqual(full["warnings"], result["warnings"])

    def test_cli_amend_and_compact_update(self):
        def cli(*args):
            result = subprocess.run([sys.executable, str(PLUGIN / "scripts/pyramid.py"), *args,
                                     "--project", str(self.root), "--json"],
                                    capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            return json.loads(result.stdout)
        preview = cli("amend", "--proposal", str(self.path), "--actor", "worker", "--preview")
        result = cli("amend", "--proposal", str(self.path), "--actor", "worker", "--apply", "--expected-amendment", preview["amendment_id"])
        self.assertEqual("applied", result["status"])
        updated = cli("update", "--node", "RESEARCH-101", "--actor", "worker", "--status", "clear", "--expected-guard", result["mutation_guard"])
        self.assertEqual("agent-status-v1", updated["packet"]["schema"])
        self.assertNotIn("before", updated["event"])
        self.assertEqual("pyramid-event-reference-v1", updated["event"]["schema"])
        full = cli("update", "--node", "RESEARCH-101", "--actor", "worker", "--status", "clear",
                   "--expected-guard", updated["packet"]["mutation_guard"], "--full")
        self.assertEqual("agent-task-v1", full["packet"]["schema"])
        self.assertEqual("pyramid-event-v1", full["event"]["schema"])
        self.assertIn("before", full["event"])
        self.assertNotIn("response_format", full)
        saved = core.load_json(self.root / ".pyramid/events" / f"{full['event']['id']}.json")
        self.assertEqual(saved, full["event"])
        explicit = cli("update", "--node", "RESEARCH-101", "--actor", "worker", "--status", "clear",
                       "--expected-guard", full["packet"]["mutation_guard"], "--compact")
        self.assertEqual("agent-status-v1", explicit["packet"]["schema"])
        packet = cli("inspect", "--node", "RESEARCH-101")
        self.assertEqual("agent-task-v1", packet["schema"])
        self.assertIn("acceptance_criteria", packet)

    def test_cli_conflicting_output_flags_do_not_mutate(self):
        before = self.snapshot()
        result = subprocess.run([sys.executable, str(PLUGIN / "scripts/pyramid.py"),
                                 "update", "--project", str(self.root), "--node", "RESEARCH-101",
                                 "--actor", "worker", "--status", "clear", "--json", "--compact", "--full"],
                                capture_output=True, text=True,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(2, result.returncode)
        self.assertIn("not allowed", result.stderr)
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
