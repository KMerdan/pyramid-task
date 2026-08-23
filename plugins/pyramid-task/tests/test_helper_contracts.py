from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import jsonschema


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def load_schema(name: str) -> dict:
    return json.loads((PLUGIN_ROOT / "schemas" / name).read_text(encoding="utf-8"))


def helper_job() -> dict:
    return {
        "schema": "helper-job-v1",
        "helper_id": "HELPER-TASK-203-RESEARCH-01",
        "parent_task": "TASK-203",
        "task_guard": "GUARD-TASK-0123456789ABCDEF0123456789ABCDEF",
        "kind": "research",
        "phase": "preflight",
        "snapshot": {
            "kind": "git-commit",
            "id": "0123456789abcdef0123456789abcdef01234567",
            "immutable": True,
        },
        "read_scope": ["src/router/**", "tests/router/**"],
        "purpose": "Identify routing invariants before implementation.",
        "questions": ["Which tests define fallback behavior?"],
        "acceptance_criteria": ["AC-203-01"],
        "execution_isolation": "none",
        "prohibited_actions": [
            "write-canonical-worktree",
            "mutate-pyramid",
            "spawn-agents",
            "publish-or-deploy",
            "change-git-history",
        ],
        "join_before": "load-bearing-decision",
        "result_budget": {
            "max_findings": 8,
            "max_evidence_items": 12,
            "max_output_chars": 8000,
        },
    }


def helper_result() -> dict:
    return {
        "schema": "helper-result-v1",
        "helper_id": "HELPER-TASK-203-RESEARCH-01",
        "parent_task": "TASK-203",
        "task_guard": "GUARD-TASK-0123456789ABCDEF0123456789ABCDEF",
        "kind": "research",
        "phase": "preflight",
        "snapshot": {
            "kind": "git-commit",
            "id": "0123456789abcdef0123456789abcdef01234567",
            "immutable": True,
        },
        "status": "completed",
        "summary": "Fallback behavior is covered by the router contract tests.",
        "findings": [
            {
                "claim": "Fallback retries once before returning the terminal error.",
                "confidence": "high",
                "evidence": ["tests/router/test_fallback.py"],
                "recommendation": "Preserve the retry boundary.",
            }
        ],
        "evidence": ["tests/router/test_fallback.py"],
        "checks": [],
        "stale_if": ["The router implementation or fallback tests change."],
        "evidence_use": "advisory",
        "freshness": "pending",
        "final_evidence_eligible": False,
        "eligibility_reason": "Preflight evidence is advisory.",
        "changed_files": [],
        "changed_assets": [],
        "risks": [],
    }


class HelperContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.job_schema = load_schema("helper-job.schema.json")
        self.result_schema = load_schema("helper-result.schema.json")

    def test_schemas_are_valid_draft_2020_12(self) -> None:
        jsonschema.Draft202012Validator.check_schema(self.job_schema)
        jsonschema.Draft202012Validator.check_schema(self.result_schema)

    def test_published_examples_are_valid(self) -> None:
        jsonschema.validate(helper_job(), self.job_schema)
        jsonschema.validate(helper_result(), self.result_schema)

    def test_job_requires_an_immutable_snapshot_and_all_prohibitions(self) -> None:
        mutable = helper_job()
        mutable["snapshot"]["immutable"] = False
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(mutable, self.job_schema)

        incomplete = helper_job()
        incomplete["prohibited_actions"].remove("mutate-pyramid")
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(incomplete, self.job_schema)

    def test_candidate_validation_requires_isolation_and_candidate_join(self) -> None:
        candidate = helper_job()
        candidate.update(
            {
                "kind": "validation",
                "phase": "candidate",
                "join_before": "candidate-acceptance",
            }
        )
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(candidate, self.job_schema)

        candidate["execution_isolation"] = "disposable-worktree"
        jsonschema.validate(candidate, self.job_schema)

    def test_result_cannot_report_writes_or_promote_preflight_evidence(self) -> None:
        changed = helper_result()
        changed["changed_files"] = ["src/router.py"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(changed, self.result_schema)

        promoted = helper_result()
        promoted["evidence_use"] = "candidate-bound"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(promoted, self.result_schema)

    def test_candidate_result_is_bound_to_its_snapshot(self) -> None:
        result = copy.deepcopy(helper_result())
        result["kind"] = "validation"
        result["phase"] = "candidate"
        result["evidence_use"] = "candidate-bound"
        result["freshness"] = "current"
        result["final_evidence_eligible"] = True
        result["eligibility_reason"] = "Coordinator matched the accepted candidate snapshot."
        result["checks"] = [
            {
                "command": "python3 -m unittest",
                "result": "passed",
                "isolation": "disposable-worktree",
                "evidence": "test-output.txt",
            }
        ]
        jsonschema.validate(result, self.result_schema)
        self.assertEqual(
            "0123456789abcdef0123456789abcdef01234567",
            result["snapshot"]["id"],
        )

    def test_stale_candidate_cannot_be_final_evidence(self) -> None:
        result = helper_result()
        result["kind"] = "validation"
        result["phase"] = "candidate"
        result["evidence_use"] = "candidate-bound"
        result["freshness"] = "stale"
        result["final_evidence_eligible"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(result, self.result_schema)


if __name__ == "__main__":
    unittest.main()
