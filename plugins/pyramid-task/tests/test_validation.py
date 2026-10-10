from __future__ import annotations

import copy
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from plan_validation_support import PLUGIN_ROOT, load_json, validation_cases

sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
from pyramid_validation import validate_plan  # noqa: E402


class PlanValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.example = PLUGIN_ROOT / "assets/example-plan.json"

    def test_cycle_is_rejected(self) -> None:
        candidate = load_json(self.example)
        candidate["edges"].append({"from": "RESEARCH-101", "to": "CONTRACT-102", "type": "requires"})
        errors = validate_plan(candidate)
        self.assertTrue(any("cycle" in error.lower() for error in errors), errors)

    def test_accepts_legacy_and_harness_examples(self) -> None:
        cases = validation_cases()
        for name in ("valid-legacy", "valid-harness"):
            with self.subTest(name=name):
                self.assertEqual([], validate_plan(cases[name]))

    def test_structural_error_order_is_stable(self) -> None:
        candidate = load_json(self.example)
        candidate["title"] = ""
        candidate["revision"] = 0
        candidate["nodes"][2]["agent"]["commands"] = [42]
        self.assertEqual([
            "title must be a non-empty string",
            "revision must be a positive integer",
            "RESEARCH-101: agent.commands must be a string array",
        ], validate_plan(candidate))

    def test_harness_validation_runs_only_after_structural_checks(self) -> None:
        candidate = load_json(self.example)
        with mock.patch("pyramid_validation.validate_contracts", return_value=["proof-error"]) as proof:
            self.assertEqual(["proof-error"], validate_plan(candidate))
            proof.assert_called_once_with(candidate)
            proof.reset_mock()
            candidate["title"] = ""
            self.assertEqual(["title must be a non-empty string"], validate_plan(candidate))
            proof.assert_not_called()

    def test_validation_does_not_mutate_inputs(self) -> None:
        for name, candidate in validation_cases().items():
            if name == "malformed-edge-exception":
                continue
            with self.subTest(name=name):
                before = copy.deepcopy(candidate)
                validate_plan(candidate)
                self.assertEqual(before, candidate)

    def test_validation_needs_no_project_io(self) -> None:
        cases = validation_cases()
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("read")), \
             mock.patch.object(Path, "write_text", side_effect=AssertionError("write")), \
             mock.patch.object(subprocess, "run", side_effect=AssertionError("process")):
            self.assertEqual([], validate_plan(cases["valid-legacy"]))
            self.assertEqual([], validate_plan(cases["valid-harness"]))

    def test_core_keeps_validation_compatibility_exports(self) -> None:
        import pyramid_core as core
        import pyramid_validation as validation
        self.assertIs(core.validate_plan, validation.validate_plan)
        self.assertIs(core._cycle, validation._cycle)
        self.assertIs(core._is_string_list, validation._is_string_list)
        self.assertEqual([], core.validate_plan(load_json(self.example)))

    def test_invalid_agent_effect_and_generated_assets_are_rejected(self) -> None:
        cases = validation_cases()
        self.assertEqual(["RESEARCH-101: agent.effect is invalid"],
                         validate_plan(cases["agent-effect-unknown"]))
        self.assertEqual(["RESEARCH-101: agent.generated_outputs[0].asset_ids must be a non-empty string array"],
                         validate_plan(cases["generated-asset-ids"]))


if __name__ == "__main__":
    unittest.main()
