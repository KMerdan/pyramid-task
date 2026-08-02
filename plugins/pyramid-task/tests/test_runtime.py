from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import jsonschema


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from pyramid_core import (  # noqa: E402
    PyramidError,
    archive_project,
    assess_project,
    audit_node,
    clean_project,
    close_project,
    create_project,
    expand_project,
    expansion_parent_snapshot,
    inspect_lifecycle,
    inspect_project,
    impact_project,
    load_json,
    replan_project,
    reopen_node,
    reset_project,
    restore_project,
    take_task,
    update_task,
    upgrade_project,
    validate_plan,
    validate_project,
)
from pyramid_visualizer import render_visualization  # noqa: E402


class PyramidRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.example = PLUGIN_ROOT / "assets" / "example-plan.json"
        self.expansion = PLUGIN_ROOT / "assets" / "example-expansion.json"
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

    def assurance_audit_for(self, nid: str, result: str = "pass") -> Path:
        payload = load_json(self.audit_for(nid, result))
        payload["assurance"] = {
            "impact_ids": ["IMPACT-001"],
            "inspection_ids": ["INSPECTION-001"],
            "finding_ids": [],
            "scope_review": "complete",
            "limitations": [],
        }
        return self.write_json(f"{nid}-assurance-audit.json", payload)

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

    def proposal_for(self, target: str, suffix: str) -> dict:
        plan = load_json(self.root / ".pyramid" / "plan.json")
        state = load_json(self.root / ".pyramid" / "state.json")
        parent = next(node for node in plan["nodes"] if node["id"] == target)
        level = parent["level"] + 1
        first = f"TASK-{suffix}1"
        second = f"TASK-{suffix}2"
        gate = f"GATE-{suffix}9"
        requirements = parent["source_requirements"]

        def child(nid: str, kind: str, title: str, wave: int) -> dict:
            return {
                "id": nid,
                "kind": kind,
                "title": title,
                "summary": f"Bounded child work for {target}.",
                "level": level,
                "wave": wave,
                "workstream": f"nested-{suffix}",
                "selection": "primary",
                "source_requirements": requirements,
                "acceptance_criteria": [
                    {"id": f"AC-{nid}-01", "description": f"{title} is demonstrated."}
                ],
                "required_evidence": [
                    {"id": f"EVREQ-{nid}-01", "type": "test", "description": f"Evidence for {title}."}
                ],
                "agent": {
                    "required_context": [],
                    "allowed_write_scope": [f"work/{nid}/**"],
                    "commands": ["test"],
                    "deliverables": [title],
                    "non_goals": [],
                },
            }

        current_dependencies = [
            edge
            for edge in plan["edges"]
            if edge["from"] == target
            and edge["type"] in {"requires", "contract-requires", "integration-requires", "validation-requires"}
        ]
        return {
            "schema": "expansion-proposal-v1",
            "target": target,
            "base_graph_version": state["graph_version"],
            "reason": "The task has two independently reviewable child outcomes.",
            "trigger_signals": ["Two independently reviewable deliverables"],
            "evidence": [{"claim": "The task contract contains separable work.", "reference": target}],
            "preserved_parent": expansion_parent_snapshot(parent),
            "nodes": [
                child(first, "implementation", "Implement first half", parent["wave"]),
                child(second, "implementation", "Implement second half", parent["wave"] + 1),
                child(gate, "audit", "Audit child composition", parent["wave"] + 2),
            ],
            "audit_gate": gate,
            "audit_coverage": [
                {"node": first, "type": "integration-requires"},
                {"node": second, "type": "integration-requires"},
            ],
            "internal_edges": [{"from": second, "to": first, "type": "requires"}],
            "dependency_mapping": [
                {
                    "dependency": {"to": edge["to"], "type": edge["type"]},
                    "consumers": [first, second],
                    "rationale": "Both child branches preserve the current prerequisite.",
                }
                for edge in current_dependencies
            ],
            "user_decisions": [],
            "impact": {
                "scope": "The parent contract and external edges are unchanged.",
                "risk": "One additional coordination gate is introduced.",
                "execution_order": "The second branch follows the first; the gate follows both.",
            },
        }

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

    def test_expand_preview_requires_explicit_approval_and_does_not_mutate(self) -> None:
        preview = expand_project(self.root, self.expansion, "planner", apply=False)
        self.assertEqual("preview", preview["status"])
        self.assertTrue(preview["approval_required"])
        self.assertEqual(64, len(preview["proposal_sha256"]))
        self.assertEqual(1, load_json(self.root / ".pyramid" / "state.json")["graph_version"])
        with self.assertRaises(PyramidError):
            expand_project(self.root, self.expansion, "planner", apply=True)
        with self.assertRaisesRegex(PyramidError, "hash"):
            expand_project(
                self.root,
                self.expansion,
                "planner",
                apply=True,
                approved_by="owner",
                approval_reference="conversation-message-42",
                approved_proposal_sha256="wrong",
            )

    def test_expand_applies_stable_work_package_and_records_approval(self) -> None:
        preview = expand_project(self.root, self.expansion, "planner", apply=False)
        before = load_json(self.root / ".pyramid" / "plan.json")
        incident_before = [
            edge for edge in before["edges"] if "TASK-201" in {edge["from"], edge["to"]}
        ]
        result = expand_project(
            self.root,
            self.expansion,
            "planner",
            apply=True,
            approved_by="owner",
            approval_reference="conversation-message-42",
            approved_proposal_sha256=preview["proposal_sha256"],
        )
        self.assertEqual("applied", result["status"])
        self.assertEqual("work-package", result["parent"]["kind"])
        self.assertEqual("not-executable", result["parent"]["availability"])
        self.assertEqual({"TASK-211", "TASK-212", "GATE-219"}, set(result["parent"]["children"]))
        after = load_json(self.root / ".pyramid" / "plan.json")
        for edge in incident_before:
            self.assertIn(edge, after["edges"])
        event = result["event"]
        self.assertEqual("task.expanded", event["type"])
        self.assertEqual("owner", event["payload"]["approval"]["approved_by"])
        self.assertEqual("conversation-message-42", event["payload"]["approval"]["reference"])
        self.assertEqual(preview["proposal_sha256"], event["payload"]["approval"]["proposal_sha256"])
        self.assertTrue(validate_project(self.root)["valid"])

    def test_expand_rejects_stale_changed_or_incomplete_proposals(self) -> None:
        proposal = load_json(self.expansion)
        proposal["base_graph_version"] = 99
        with self.assertRaisesRegex(PyramidError, "stale"):
            expand_project(self.root, self.write_json("stale-expansion.json", proposal), "planner", apply=False)
        proposal = load_json(self.expansion)
        proposal["preserved_parent"]["summary"] = "Changed purpose"
        with self.assertRaisesRegex(PyramidError, "preserved_parent"):
            expand_project(self.root, self.write_json("changed-expansion.json", proposal), "planner", apply=False)
        proposal = load_json(self.expansion)
        proposal["audit_coverage"] = proposal["audit_coverage"][:1]
        with self.assertRaisesRegex(PyramidError, "cover every"):
            expand_project(self.root, self.write_json("uncovered-expansion.json", proposal), "planner", apply=False)

    def test_expand_refuses_an_active_claim(self) -> None:
        take_task(self.root, "worker", nid="RESEARCH-101")
        proposal = self.proposal_for("RESEARCH-101", "31")
        with self.assertRaisesRegex(PyramidError, "release the active claim"):
            expand_project(self.root, self.write_json("claimed-expansion.json", proposal), "planner", apply=False)

    def test_expansion_subtree_audits_to_closure(self) -> None:
        preview = expand_project(self.root, self.expansion, "planner", apply=False)
        expand_project(
            self.root,
            self.expansion,
            "planner",
            apply=True,
            approved_by="owner",
            approval_reference="conversation-message-42",
            approved_proposal_sha256=preview["proposal_sha256"],
        )
        self.complete_and_audit("RESEARCH-101", ["AC-101-01"])
        self.complete_and_audit("CONTRACT-102", ["AC-102-01"])
        self.complete_and_audit("TASK-211", ["AC-211-01"])
        self.complete_and_audit("TASK-212", ["AC-212-01"])
        self.complete_and_audit("GATE-219", ["AC-219-01"], actor="audit-worker")
        audit_node(self.root, "TASK-201", "auditor", "pass", self.audit_for("TASK-201"))
        self.complete_and_audit("GATE-290", ["AC-290-01"], actor="audit-worker")
        audit_node(self.root, "OUTCOME-010", "auditor", "pass", self.audit_for("OUTCOME-010"))
        audit_node(self.root, "INTENT-001", "owner", "pass", self.audit_for("INTENT-001"))
        self.assertTrue(inspect_project(self.root, summary=True)["closure_ready"])
        self.assertEqual("completed", close_project(self.root, "owner")["status"])

    def test_expansion_is_recursive_and_deep_visualization_scales(self) -> None:
        first_preview = expand_project(self.root, self.expansion, "planner", apply=False)
        expand_project(
            self.root,
            self.expansion,
            "planner",
            apply=True,
            approved_by="owner",
            approval_reference="first-approval",
            approved_proposal_sha256=first_preview["proposal_sha256"],
        )
        nested = self.proposal_for("TASK-212", "22")
        nested_path = self.write_json("nested-expansion.json", nested)
        nested_preview = expand_project(self.root, nested_path, "planner", apply=False)
        expand_project(
            self.root,
            nested_path,
            "planner",
            apply=True,
            approved_by="owner",
            approval_reference="second-approval",
            approved_proposal_sha256=nested_preview["proposal_sha256"],
        )
        graph = load_json(self.root / ".pyramid" / "graph.json")
        task = next(node for node in graph["nodes"] if node["id"] == "TASK-212")
        self.assertEqual("work-package", task["kind"])
        self.assertEqual(4, max(node["level"] for node in graph["nodes"]))
        output = Path(self.temp.name) / "deep-map.html"
        render_visualization(self.root, output)
        html = output.read_text(encoding="utf-8")
        self.assertIn("Work packages", html)
        self.assertIn("previous + 108", html)
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
            (schema_dir / "project.schema.json", self.root / ".pyramid" / "project.json"),
            (schema_dir / "final-report.schema.json", Path(closed["report"])),
            (schema_dir / "archive-manifest.schema.json", Path(archived["archive"]) / "manifest.json"),
        ]
        for schema_path, artifact_path in artifacts:
            schema = load_json(schema_path)
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.validate(load_json(artifact_path), schema)
        jsonschema.validate(load_json(self.expansion), load_json(schema_dir / "expansion-proposal.schema.json"))
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

    def test_auto_mode_makes_existing_repository_brownfield_by_default(self) -> None:
        root = Path(self.temp.name) / "existing-project"
        (root / "src").mkdir(parents=True)
        (root / "src" / "existing.py").write_text("value = 1\n", encoding="utf-8")
        created = create_project(root, self.example, "planner")
        self.assertEqual("brownfield", created["mode"])
        self.assertEqual("incomplete", load_json(root / ".pyramid" / "baseline.json")["status"])
        assurance = inspect_project(root, assurance_view=True)
        self.assertEqual("brownfield", assurance["mode"])
        self.assertEqual("blocked", assurance["summary"]["status"])

    def test_brownfield_audits_require_inspection_coverage_and_close_with_dossier(self) -> None:
        root = Path(self.temp.name) / "assured-project"
        create_project(
            root,
            self.example,
            "planner",
            mode="brownfield",
            baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
            assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
        )

        def refresh_assurance(label: str) -> None:
            candidate = load_json(root / ".pyramid" / "assurance.json")
            candidate["status"] = "ready"
            candidate["stale_reasons"] = []
            candidate["inspections"][0]["status"] = "performed"
            candidate["inspections"][0]["result"] = "pass"
            candidate["inspections"][0]["sufficiency"] = "sufficient"
            candidate["inspections"][0]["performed_at"] = datetime.now(timezone.utc).isoformat()
            candidate["inspections"][0]["performed_by"] = "auditor"
            impact_project(
                root,
                self.write_json(f"{label}-assurance.json", candidate),
                "auditor",
                apply=True,
            )

        def complete(nid: str, criteria: list[str], actor: str = "worker") -> None:
            take_task(root, actor, nid=nid)
            result = load_json(self.result_for(nid, criteria))
            result["changed_files"] = []
            result["changed_assets"] = ["ASSET-EXECUTOR"]
            result_path = self.write_json(f"{nid}-assured-result.json", result)
            update_task(root, nid, actor, "implemented", result_path=result_path)
            refresh_assurance(nid)
            audit_node(root, nid, "auditor", "pass", self.assurance_audit_for(nid))

        take_task(root, "worker", nid="RESEARCH-101")
        result = load_json(self.result_for("RESEARCH-101", ["AC-101-01"]))
        result["changed_files"] = []
        result["changed_assets"] = ["ASSET-EXECUTOR"]
        update_task(
            root,
            "RESEARCH-101",
            "worker",
            "implemented",
            result_path=self.write_json("research-assured-result.json", result),
        )
        refresh_assurance("RESEARCH-101-initial")
        with self.assertRaisesRegex(PyramidError, "assurance coverage"):
            audit_node(root, "RESEARCH-101", "auditor", "pass", self.audit_for("RESEARCH-101"))
        audit_node(root, "RESEARCH-101", "auditor", "pass", self.assurance_audit_for("RESEARCH-101"))
        complete("CONTRACT-102", ["AC-102-01"])
        complete("TASK-201", ["AC-201-01", "AC-201-02"])
        complete("GATE-290", ["AC-290-01"], actor="audit-worker")
        audit_node(root, "OUTCOME-010", "auditor", "pass", self.assurance_audit_for("OUTCOME-010"))
        audit_node(root, "INTENT-001", "owner", "pass", self.assurance_audit_for("INTENT-001"))
        closed = close_project(root, "owner")
        self.assertTrue(Path(closed["change_dossier"]).exists())
        self.assertTrue(Path(closed["change_dossier_markdown"]).exists())
        self.assertEqual(2, load_json(root / ".pyramid" / "baseline.json")["revision"])
        self.assertEqual("passed", load_json(root / ".pyramid" / "assurance.json")["status"])
        schema = load_json(PLUGIN_ROOT / "schemas" / "change-dossier.schema.json")
        jsonschema.validate(load_json(Path(closed["change_dossier"])), schema)
        visual = render_visualization(root, Path(self.temp.name) / "assured-map.html")
        visual_text = Path(visual["output"]).read_text(encoding="utf-8")
        self.assertIn("Assurance status", visual_text)
        self.assertIn("Impact", visual_text)
        self.assertIn("INSPECTION-001", visual_text)

    def test_scope_drift_stales_assurance_until_impact_is_reconciled(self) -> None:
        root = Path(self.temp.name) / "drift-project"
        create_project(
            root,
            self.example,
            "planner",
            mode="brownfield",
            baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
            assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
        )
        take_task(root, "worker", nid="RESEARCH-101")
        result = load_json(self.result_for("RESEARCH-101", ["AC-101-01"]))
        result["changed_files"] = ["outside/unknown.py"]
        updated = update_task(
            root,
            "RESEARCH-101",
            "worker",
            "implemented",
            result_path=self.write_json("drift-result.json", result),
        )
        self.assertEqual(1, len(updated["scope_drift"]))
        with self.assertRaisesRegex(PyramidError, "stale|Scope drift"):
            audit_node(root, "RESEARCH-101", "auditor", "pass", self.assurance_audit_for("RESEARCH-101"))
        candidate = load_json(root / ".pyramid" / "assurance.json")
        candidate["scope_drift"][0]["status"] = "resolved"
        candidate["scope_drift"][0]["resolved_impact_id"] = "IMPACT-001"
        candidate["inspections"][0]["status"] = "performed"
        candidate["inspections"][0]["result"] = "pass"
        candidate["inspections"][0]["sufficiency"] = "sufficient"
        candidate["inspections"][0]["performed_at"] = datetime.now(timezone.utc).isoformat()
        candidate["inspections"][0]["performed_by"] = "auditor"
        candidate["stale_reasons"] = []
        candidate["status"] = "ready"
        applied = impact_project(
            root,
            self.write_json("reconciled-assurance.json", candidate),
            "planner",
            apply=True,
        )
        self.assertEqual("ready", applied["assurance_status"])
        audit_node(root, "RESEARCH-101", "auditor", "pass", self.assurance_audit_for("RESEARCH-101"))

    def test_assess_invalidates_performed_inspections(self) -> None:
        root = Path(self.temp.name) / "reassessed-project"
        create_project(
            root,
            self.example,
            "planner",
            mode="brownfield",
            baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
            assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
        )
        baseline = load_json(root / ".pyramid" / "baseline.json")
        baseline["revision"] = 2
        baseline["captured_at"] = "2026-08-02T01:00:00Z"
        applied = assess_project(
            root,
            self.write_json("baseline-r2.json", baseline),
            "assessor",
            apply=True,
        )
        self.assertEqual("applied", applied["status"])
        assurance = load_json(root / ".pyramid" / "assurance.json")
        self.assertEqual("stale", assurance["status"])
        self.assertEqual("stale", assurance["inspections"][0]["status"])

    def test_upgrade_v21_plan_in_place_preserves_running_work_and_history(self) -> None:
        root = Path(self.temp.name) / "legacy-project"
        create_project(root, self.example, "planner", mode="greenfield")
        take_task(root, "worker", nid="RESEARCH-101")
        (root / "src").mkdir(parents=True)
        (root / "src" / "legacy.py").write_text("value = 1\n", encoding="utf-8")
        (root / ".pyramid" / "project.json").unlink()
        legacy_state = load_json(root / ".pyramid" / "state.json")
        legacy_state["lifecycle"].pop("change_dossier", None)
        (root / ".pyramid" / "state.json").write_text(
            json.dumps(legacy_state, indent=2) + "\n",
            encoding="utf-8",
        )
        before_plan = (root / ".pyramid" / "plan.json").read_bytes()
        before_state = load_json(root / ".pyramid" / "state.json")
        before_events = sorted((root / ".pyramid" / "events").glob("*.json"))
        self.assertTrue(validate_project(root)["valid"])
        self.assertEqual("legacy", inspect_project(root, summary=True)["project"]["mode"])

        preview = upgrade_project(root, "migrator", source_version="2.1", mode="auto")
        repeated = upgrade_project(root, "migrator", source_version="2.1", mode="auto")
        self.assertEqual(preview["upgrade_sha256"], repeated["upgrade_sha256"])
        self.assertEqual("brownfield", preview["generated"]["mode"])
        jsonschema.validate(
            preview,
            load_json(PLUGIN_ROOT / "schemas" / "upgrade-preview.schema.json"),
        )
        applied = upgrade_project(
            root,
            "migrator",
            source_version="2.1",
            mode="auto",
            apply=True,
            approved_by="owner",
            approval_reference="upgrade-approval-001",
            approved_upgrade_sha256=preview["upgrade_sha256"],
            expected_version=before_state["graph_version"],
        )
        after_state = load_json(root / ".pyramid" / "state.json")
        self.assertEqual(before_plan, (root / ".pyramid" / "plan.json").read_bytes())
        self.assertEqual(before_state["nodes"], after_state["nodes"])
        self.assertEqual(before_state["graph_version"] + 1, after_state["graph_version"])
        self.assertEqual(len(before_events) + 1, len(list((root / ".pyramid" / "events").glob("*.json"))))
        self.assertEqual("working", after_state["nodes"]["RESEARCH-101"]["execution"])
        self.assertEqual("worker", after_state["nodes"]["RESEARCH-101"]["owner"])
        self.assertTrue(Path(applied["archive"]).exists())
        self.assertTrue(validate_project(Path(applied["archive"]))["valid"])
        self.assertEqual("incomplete", load_json(root / ".pyramid" / "baseline.json")["status"])
        self.assertEqual("pending", load_json(root / ".pyramid" / "assurance.json")["legacy_bridge"]["status"])
        self.assertEqual("up-to-date", upgrade_project(root, "migrator")["status"])
        self.assertTrue(validate_project(root)["valid"])

    def test_brownfield_reset_carries_baseline_and_archives_assurance(self) -> None:
        root = Path(self.temp.name) / "reset-brownfield"
        create_project(
            root,
            self.example,
            "planner",
            mode="brownfield",
            baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
            assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
        )
        baseline_before = load_json(root / ".pyramid" / "baseline.json")
        candidate = load_json(self.example)
        candidate["plan_id"] = "PLAN-RESET-BROWNFIELD"
        reset = reset_project(
            root,
            self.write_json("brownfield-reset-plan.json", candidate),
            "owner",
            "Start the next change",
        )
        baseline_after = load_json(root / ".pyramid" / "baseline.json")
        self.assertEqual(baseline_before, baseline_after)
        next_assurance = load_json(root / ".pyramid" / "assurance.json")
        self.assertEqual("PLAN-RESET-BROWNFIELD", next_assurance["plan_id"])
        self.assertEqual("incomplete", next_assurance["status"])
        archive_meta = Path(reset["previous_archive"])
        archived = next(
            item
            for item in inspect_lifecycle(root)["archives"]
            if item["archive_id"] == archive_meta.name
        )
        self.assertTrue((Path(archived["path"]) / ".pyramid" / "assurance.json").exists())

    def test_v3_cli_exposes_brownfield_and_upgrade_interfaces(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "pyramid.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        for command in ("upgrade", "assess", "impact"):
            self.assertIn(command, completed.stdout)


if __name__ == "__main__":
    unittest.main()
