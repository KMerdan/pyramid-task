"""Boundary behavior beyond the retained integration tests."""
from __future__ import annotations
import copy
import pickle
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock
from runtime_modularization_support import PLUGIN_ROOT, FIXED_TIME, load_example, state_for
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
import pyramid_core as core
import pyramid_errors as errors
import pyramid_projection as projection
import pyramid_state as state_rules
import pyramid_topology as topology


class RuntimeModularizationTests(unittest.TestCase):
    def setUp(self):
        self.plan = load_example("example-plan.json")
        self.state = state_for(self.plan)
        self.node = next(n for n in self.plan["nodes"] if n["id"] == "TASK-201")

    def test_shared_error_keeps_legacy_identity_and_serialization(self):
        self.assertIs(core.PyramidError, errors.PyramidError)
        self.assertEqual("pyramid_core", errors.PyramidError.__module__)
        restored = pickle.loads(pickle.dumps(core.PyramidError("failure")))
        self.assertIs(type(restored), core.PyramidError)
        self.assertEqual("failure", str(restored))

    def test_clock_wrapper_keeps_initial_short_circuit(self):
        with mock.patch.object(core, "utc_now", return_value=FIXED_TIME) as clock:
            self.assertEqual("explicit", core.initial_node_state(self.node, "explicit")["updated_at"])
            clock.assert_not_called()
            self.assertEqual(FIXED_TIME, core.initial_node_state(self.node, "")["updated_at"])
            clock.assert_called_once_with()
        self.assertEqual("value-time", state_rules.initial_node_state(self.node, "value-time")["updated_at"])

    def test_invalidation_obtains_one_time_even_without_claims(self):
        with mock.patch.object(core, "utc_now", return_value=FIXED_TIME) as clock:
            self.assertEqual([], core.invalidate_dependent_claims(self.plan, self.state, "TASK-201", "r"))
            clock.assert_called_once_with()
        affected = state_rules.dependent_claims(self.plan, "TASK-201")
        for nid in affected:
            self.state["nodes"][nid].update(execution="implemented", verification="passed")
        changed = state_rules.invalidate_dependent_claims(self.plan, self.state, "TASK-201", "r", timestamp="explicit")
        self.assertEqual(affected, changed)
        self.assertTrue(all(self.state["nodes"][nid]["updated_at"] == "explicit" for nid in changed))

    def test_graph_preparation_failure_does_not_call_clock(self):
        del self.state["nodes"]["TASK-201"]
        with mock.patch.object(core, "utc_now", side_effect=AssertionError("clock must not run")) as clock:
            with self.assertRaises(KeyError):
                core.graph_snapshot(self.plan, self.state)
            clock.assert_not_called()

    def test_graph_clock_stays_before_lifecycle_defaulting(self):
        before = copy.deepcopy(self.state)
        with mock.patch.object(core, "utc_now", side_effect=RuntimeError("clock failure")) as clock:
            with self.assertRaisesRegex(RuntimeError, "clock failure"):
                core.graph_snapshot(self.plan, self.state)
            clock.assert_called_once_with()
        self.assertEqual(before, self.state)
        self.assertNotIn("lifecycle", self.state)

    def test_explicit_graph_timestamp_and_legacy_path_agree(self):
        with mock.patch.object(core, "utc_now", return_value=FIXED_TIME):
            legacy = core.graph_snapshot(self.plan, copy.deepcopy(self.state))
        explicit = projection.graph_snapshot(self.plan, copy.deepcopy(self.state), generated_at=FIXED_TIME)
        self.assertEqual(legacy, explicit)
        self.assertEqual(FIXED_TIME, explicit["generated_at"])

    def test_declared_in_memory_mutations_are_preserved(self):
        lifecycle = state_rules.lifecycle_state(self.state)
        self.assertIs(lifecycle, self.state["lifecycle"])
        self.assertEqual("active", lifecycle["status"])
        item = {"active_handoff_id": "h", "paused_at": "t", "paused_by": "a",
                "pause_mode": "hold", "resume_deadline": "d", "other": 1}
        self.assertIsNone(state_rules.clear_active_pause(item))
        self.assertEqual(1, item["other"])
        self.assertTrue(all(item[k] is None for k in item if k != "other"))

    def test_rule_and_projection_calls_require_no_project_io(self):
        proposal = load_example("example-expansion.json")
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("read")), \
             mock.patch.object(Path, "write_text", side_effect=AssertionError("write")), \
             mock.patch.object(subprocess, "run", side_effect=AssertionError("process")):
            self.assertEqual([], state_rules.validate_state(self.plan, self.state))
            self.assertTrue(state_rules.task_mutation_guard(self.plan, self.state, "TASK-201", None, None).startswith("GUARD-TASK-"))
            self.assertEqual([], topology._expansion_errors(self.plan, self.state, proposal))
            candidate, diff = topology.prepare_expansion(self.plan, self.state, proposal)
            self.assertEqual("work-package", next(n for n in candidate["nodes"] if n["id"] == "TASK-201")["kind"])
            self.assertEqual("TASK-201", diff["target"])
            self.assertEqual("TASK-201", projection.task_packet(self.plan, self.state, "TASK-201")["task"])
            self.assertEqual(FIXED_TIME, projection.graph_snapshot(self.plan, self.state, generated_at=FIXED_TIME)["generated_at"])

    def test_topology_rejections_do_not_modify_inputs(self):
        proposal = load_example("example-expansion.json")
        proposal["preserved_parent"] = {}
        before = copy.deepcopy((self.plan, self.state, proposal))
        with self.assertRaisesRegex(core.PyramidError, "preserved_parent"):
            topology.prepare_expansion(self.plan, self.state, proposal)
        self.assertEqual(before, (self.plan, self.state, proposal))

    def test_packet_projects_contracts_without_harness_query(self):
        plan = load_example("example-harness-plan.json")
        state = state_for(plan)
        with mock.patch.object(core, "query_harness", side_effect=AssertionError("harness I/O")), \
             mock.patch.object(core, "load_project", side_effect=AssertionError("project I/O")):
            packet = projection.task_packet(plan, state, "TASK-201")
        self.assertEqual("inspect --harness TASK-201", packet["harness"]["capture"])
        self.assertTrue(packet["harness"]["contracts"])


if __name__ == "__main__":
    unittest.main()
