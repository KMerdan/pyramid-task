from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from pyramid_core import (  # noqa: E402
    PyramidError,
    archive_project,
    audit_node,
    clean_project,
    close_project,
    create_project,
    inspect_lifecycle,
    inspect_project,
    load_json,
    replan_project,
    reopen_node,
    reset_project,
    restore_project,
    take_task,
    update_task,
    validate_plan,
    validate_project,
)
from pyramid_visualizer import render_visualization  # noqa: E402


class PyramidRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.example = PLUGIN_ROOT / "assets" / "example-plan.json"
        create_project(self.root, self.example, "planner")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_json(self, name: str, value: dict) -> Path:
        path = Path(self.temp.name) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def result_for(self, nid: str, criteria: list[str]) -> Path:
        return self.write_json(
            f"{nid}-result.json",
            {
                "schema": "agent-result-v1",
                "task": nid,
                "outcome": "implemented",
                "changed_files": [f"work/{nid}.txt"],
                "checks": [{"command": "test", "result": "passed"}],
                "acceptance_evidence": [
                    {"criterion": criterion, "result": "passed", "reference": f"evidence/{criterion}.txt"}
                    for criterion in criteria
                ],
                "discovered_risks": [],
                "suggested_graph_changes": [],
            },
        )

    def audit_for(self, nid: str, result: str = "pass") -> Path:
        return self.write_json(
            f"{nid}-audit.json",
            {
                "schema": "audit-result-v1",
                "target": nid,
                "result": result,
                "checks": [
                    {
                        "id": f"CHECK-{nid}",
                        "result": "passed" if result == "pass" else "failed",
                        "evidence": [f"evidence/{nid}.txt"],
                    }
                ],
                "affected_claims": [nid],
                "recommended_action": "advance" if result == "pass" else "replan",
            },
        )

    def complete_and_audit(self, nid: str, criteria: list[str], actor: str = "worker") -> None:
        take_task(self.root, actor, nid=nid)
        update_task(self.root, nid, actor, "implemented", result_path=self.result_for(nid, criteria))
        audit_node(self.root, nid, "auditor", "pass", self.audit_for(nid))

    def complete_graph(self) -> None:
        self.complete_and_audit("RESEARCH-101", ["AC-101-01"])
        self.complete_and_audit("CONTRACT-102", ["AC-102-01"])
        self.complete_and_audit("TASK-201", ["AC-201-01", "AC-201-02"])
        self.complete_and_audit("GATE-290", ["AC-290-01"], actor="audit-worker")
        audit_node(self.root, "OUTCOME-010", "auditor", "pass", self.audit_for("OUTCOME-010"))
        audit_node(self.root, "INTENT-001", "owner", "pass", self.audit_for("INTENT-001"))

    def test_create_materializes_human_and_agent_views(self) -> None:
        validation = validate_project(self.root)
        self.assertTrue(validation["valid"], validation["errors"])
        ready = inspect_project(self.root, ready=True)
        self.assertEqual(["RESEARCH-101"], [task["task"] for task in ready["tasks"]])
        self.assertTrue((self.root / "docs" / "tasks" / "README.md").exists())
        self.assertTrue((self.root / ".pyramid" / "graph.json").exists())

    def test_full_execution_and_audit_chain(self) -> None:
        self.complete_graph()
        summary = inspect_project(self.root, summary=True)
        self.assertEqual(6, summary["summary"]["verified_primary_nodes"])
        self.assertEqual([], summary["ready"])
        self.assertTrue(summary["closure_ready"])

    def test_audit_cannot_skip_unverified_dependencies(self) -> None:
        with self.assertRaises(PyramidError):
            audit_node(self.root, "OUTCOME-010", "auditor", "pass", self.audit_for("OUTCOME-010"))

    def test_stale_version_is_rejected(self) -> None:
        packet = take_task(self.root, "worker", nid="RESEARCH-101", expected_version=1)["packet"]
        self.assertEqual(2, packet["graph_version"])
        with self.assertRaises(PyramidError):
            update_task(self.root, "RESEARCH-101", "worker", "release", expected_version=1)

    def test_replan_preview_and_apply(self) -> None:
        candidate = load_json(self.example)
        candidate["nodes"][2]["title"] = "Revalidate operation schema stability"
        path = self.write_json("replan.json", candidate)
        preview = replan_project(self.root, path, "planner", "New repository evidence", apply=False)
        self.assertIn("RESEARCH-101", preview["diff"]["changed_nodes"])
        applied = replan_project(self.root, path, "planner", "New repository evidence", apply=True)
        self.assertEqual(2, applied["diff"]["to_revision"])
        self.assertTrue(validate_project(self.root)["valid"])

    def test_cycle_is_rejected(self) -> None:
        candidate = load_json(self.example)
        candidate["edges"].append({"from": "RESEARCH-101", "to": "CONTRACT-102", "type": "requires"})
        errors = validate_plan(candidate)
        self.assertTrue(any("cycle" in error.lower() for error in errors), errors)

    def test_visualization_is_self_contained(self) -> None:
        output = Path(self.temp.name) / "map.html"
        rendered = render_visualization(self.root, output)
        text = output.read_text(encoding="utf-8")
        self.assertEqual(6, rendered["nodes"])
        self.assertIn("pyramid-data", text)
        self.assertIn("Star", text)
        self.assertIn("Needs rework", text)
        self.assertNotIn("fetch(", text)

    def test_failed_audit_enters_rework_and_can_recover(self) -> None:
        take_task(self.root, "worker", nid="RESEARCH-101")
        update_task(
            self.root,
            "RESEARCH-101",
            "worker",
            "implemented",
            result_path=self.result_for("RESEARCH-101", ["AC-101-01"]),
        )
        failed = audit_node(self.root, "RESEARCH-101", "auditor", "fail", self.audit_for("RESEARCH-101", "fail"))
        self.assertEqual("needs-rework", failed["packet"]["availability"])
        self.assertEqual("failed", failed["packet"]["verification"])
        repaired = take_task(self.root, "repairer", nid="RESEARCH-101")
        self.assertEqual("working", repaired["packet"]["availability"])
        update_task(
            self.root,
            "RESEARCH-101",
            "repairer",
            "implemented",
            result_path=self.result_for("RESEARCH-101", ["AC-101-01"]),
        )
        audit_node(self.root, "RESEARCH-101", "auditor", "pass", self.audit_for("RESEARCH-101"))
        self.assertEqual(["CONTRACT-102"], [item["task"] for item in inspect_project(self.root, ready=True)["tasks"]])

    def test_close_freezes_mutations_and_reopen_reactivates_with_invalidation(self) -> None:
        self.complete_graph()
        closed = close_project(self.root, "owner")
        self.assertEqual("completed", inspect_lifecycle(self.root)["lifecycle"]["status"])
        self.assertTrue(Path(closed["report"]).exists())
        with self.assertRaises(PyramidError):
            take_task(self.root, "worker", nid="RESEARCH-101")
        reopened = reopen_node(self.root, "TASK-201", "owner", "A production regression disproved the implementation")
        self.assertTrue(reopened["plan_reactivated"])
        self.assertIn("INTENT-001", reopened["invalidated"])
        self.assertIn("OUTCOME-010", reopened["invalidated"])
        lifecycle = inspect_lifecycle(self.root)
        self.assertEqual("active", lifecycle["lifecycle"]["status"])
        self.assertFalse(lifecycle["closure_ready"])
        self.assertEqual("needs-rework", inspect_project(self.root, nid="TASK-201")["availability"])

    def test_archive_is_valid_frozen_and_visualizable(self) -> None:
        archived = archive_project(self.root, "owner", "Pause this plan")
        archive_root = Path(archived["archive"])
        self.assertTrue(validate_project(archive_root)["valid"])
        self.assertEqual("archived", inspect_lifecycle(archive_root)["lifecycle"]["status"])
        with self.assertRaises(PyramidError):
            take_task(self.root, "worker", nid="RESEARCH-101")
        output = archive_root / "archive-map.html"
        render_visualization(archive_root, output)
        self.assertTrue(output.exists())

    def test_reset_archives_current_and_starts_new_plan(self) -> None:
        candidate = load_json(self.example)
        candidate["plan_id"] = "PLAN-002"
        candidate["title"] = "Replacement plan"
        candidate_path = self.write_json("reset-plan.json", candidate)
        reset = reset_project(self.root, candidate_path, "owner", "Start a clean planning cycle")
        self.assertEqual("PLAN-002", inspect_project(self.root, summary=True)["plan_id"])
        self.assertEqual("active", inspect_lifecycle(self.root)["lifecycle"]["status"])
        archived = [item for item in inspect_lifecycle(self.root)["archives"] if item["archive_id"] == reset["previous_archive"]]
        self.assertEqual(1, len(archived))
        self.assertTrue(validate_project(Path(archived[0]["path"]))["valid"])

    def test_reset_refuses_active_claims(self) -> None:
        take_task(self.root, "worker", nid="RESEARCH-101")
        candidate = load_json(self.example)
        candidate["plan_id"] = "PLAN-002"
        candidate_path = self.write_json("reset-plan.json", candidate)
        with self.assertRaises(PyramidError):
            reset_project(self.root, candidate_path, "owner", "Unsafe while claimed")

    def test_clean_regenerates_only_derived_artifacts(self) -> None:
        plan_before = (self.root / ".pyramid" / "plan.json").read_bytes()
        state_before = (self.root / ".pyramid" / "state.json").read_bytes()
        events_before = sorted(path.read_bytes() for path in (self.root / ".pyramid" / "events").glob("*.json"))
        stale = self.root / "docs" / "tasks" / "stale.md"
        stale.write_text("stale", encoding="utf-8")
        cleaned = clean_project(self.root)
        self.assertTrue(cleaned["canonical_preserved"])
        self.assertFalse(stale.exists())
        self.assertEqual(plan_before, (self.root / ".pyramid" / "plan.json").read_bytes())
        self.assertEqual(state_before, (self.root / ".pyramid" / "state.json").read_bytes())
        self.assertEqual(events_before, sorted(path.read_bytes() for path in (self.root / ".pyramid" / "events").glob("*.json")))

    def test_restore_auto_archives_current_and_restores_selected_plan(self) -> None:
        candidate = load_json(self.example)
        candidate["plan_id"] = "PLAN-002"
        candidate_path = self.write_json("reset-plan.json", candidate)
        reset = reset_project(self.root, candidate_path, "owner", "Move to second plan")
        restored = restore_project(self.root, reset["previous_archive"], "owner", "Return to the first plan")
        self.assertEqual("PLAN-001", inspect_project(self.root, summary=True)["plan_id"])
        self.assertEqual(reset["previous_archive"], restored["restored_from"])
        self.assertIsNotNone(restored["previous_archive"])
        self.assertGreaterEqual(len(inspect_lifecycle(self.root)["archives"]), 2)

    def test_generated_lifecycle_artifacts_match_published_schemas(self) -> None:
        self.complete_graph()
        closed = close_project(self.root, "owner")
        archived = archive_project(self.root, "owner", "Schema validation")
        schema_dir = PLUGIN_ROOT / "schemas"
        artifacts = [
            (schema_dir / "plan.schema.json", self.root / ".pyramid" / "plan.json"),
            (schema_dir / "state.schema.json", self.root / ".pyramid" / "state.json"),
            (schema_dir / "final-report.schema.json", Path(closed["report"])),
            (schema_dir / "archive-manifest.schema.json", Path(archived["archive"]) / "manifest.json"),
        ]
        for schema_path, artifact_path in artifacts:
            schema = load_json(schema_path)
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.validate(load_json(artifact_path), schema)
        event_schema = load_json(schema_dir / "event.schema.json")
        for event_path in (self.root / ".pyramid" / "events").glob("*.json"):
            jsonschema.validate(load_json(event_path), event_schema)

    def test_lifecycle_cli_returns_machine_readable_status(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(PLUGIN_ROOT / "scripts" / "pyramid.py"),
                "lifecycle",
                "--project",
                str(self.root),
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual("pyramid-lifecycle-v1", payload["schema"])
        self.assertEqual("active", payload["lifecycle"]["status"])


if __name__ == "__main__":
    unittest.main()
