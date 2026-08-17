from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import jsonschema


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from pyramid_core import (  # noqa: E402
    PyramidError,
    archive_project,
    assess_project,
    audit_mutation_guard,
    audit_node,
    clean_project,
    close_project,
    compile_project,
    create_project,
    expand_project,
    expansion_parent_snapshot,
    inspect_changes,
    inspect_lifecycle,
    inspect_project,
    impact_project,
    implementation_frontier,
    intent_transition_route,
    load_assurance_bundle,
    load_json,
    load_project,
    new_intent_project,
    pause_task,
    replan_project,
    reopen_node,
    resume_task,
    reset_project,
    restore_project,
    take_task,
    update_task,
    upgrade_project,
    validate_plan,
    validate_project,
)
from pyramid_live import LiveGraphState, LiveVisualizationServer  # noqa: E402
from pyramid_visualizer import load_visualization_graph, render_visualization  # noqa: E402


class PyramidRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.example = PLUGIN_ROOT / "assets" / "example-plan.json"
        self.expansion = PLUGIN_ROOT / "assets" / "example-expansion.json"
        self.handoff_draft = PLUGIN_ROOT / "assets" / "example-handoff-draft.json"
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

    def handoff_for(self, name: str = "handoff.json") -> Path:
        return self.write_json(name, load_json(self.handoff_draft))

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

    def test_composite_context_guard_rejects_another_state_generation(self) -> None:
        current = inspect_project(self.root, summary=True)["context"]
        with self.assertRaisesRegex(PyramidError, "Stale context"):
            take_task(
                self.root,
                "worker",
                nid="RESEARCH-101",
                expected_version={
                    "graph_version": current["graph_version"],
                    "context_id": "CTX-00000000000000000000000000000000",
                },
            )
        taken = take_task(
            self.root,
            "worker",
            nid="RESEARCH-101",
            expected_version={
                "graph_version": current["graph_version"],
                "context_id": current["id"],
            },
        )
        self.assertNotEqual(current["id"], taken["packet"]["context"]["id"])

    def test_head_and_hash_linked_events_detect_out_of_band_changes(self) -> None:
        take_task(self.root, "worker", nid="RESEARCH-101")
        head = load_json(self.root / ".pyramid" / "head.json")
        state = load_json(self.root / ".pyramid" / "state.json")
        self.assertEqual(head["context"]["id"], state["context_id"])
        event_paths = sorted((self.root / ".pyramid" / "events").glob("*.json"))
        self.assertGreaterEqual(len(event_paths), 2)
        first = load_json(event_paths[0])
        first["actor"] = "out-of-band-editor"
        event_paths[0].write_text(json.dumps(first), encoding="utf-8")
        validation = validate_project(self.root)
        self.assertFalse(validation["valid"])
        self.assertTrue(
            any("event hash" in error or "event chain" in error for error in validation["errors"]),
            validation["errors"],
        )

    def test_head_rejects_unpublished_canonical_state(self) -> None:
        state_path = self.root / ".pyramid" / "state.json"
        state = load_json(state_path)
        state["updated_at"] = "2099-01-01T00:00:00Z"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        validation = validate_project(self.root)
        self.assertFalse(validation["valid"])
        self.assertIn(
            "canonical files do not match the atomically published head",
            validation["errors"],
        )
        with self.assertRaisesRegex(PyramidError, "atomically published head"):
            inspect_project(self.root, summary=True)

    def test_context_bound_project_rejects_a_removed_head(self) -> None:
        (self.root / ".pyramid" / "head.json").unlink()
        validation = validate_project(self.root)
        self.assertFalse(validation["valid"])
        self.assertIn(
            "context-bound state is missing .pyramid/head.json",
            validation["errors"],
        )

    def test_inspection_is_compact_until_detail_is_requested(self) -> None:
        ready = inspect_project(self.root, ready=True)
        self.assertNotIn("required_context", ready["tasks"][0])
        self.assertNotIn("acceptance_criteria", ready["tasks"][0])
        node = inspect_project(self.root, nid="RESEARCH-101")
        self.assertIn("required_context", node)
        self.assertIn("acceptance_criteria", node)

        root = Path(self.temp.name) / "compact-assurance"
        create_project(
            root,
            self.example,
            "planner",
            mode="brownfield",
            baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
            assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
        )
        summary = inspect_project(root, assurance_summary_view=True)
        detail = inspect_project(root, assurance_detail=True)
        self.assertNotIn("baseline", summary)
        self.assertNotIn("assurance", summary)
        self.assertIn("baseline", detail)
        self.assertIn("assurance", detail)

    def test_change_query_is_compact_by_default_and_detailed_on_demand(self) -> None:
        take_task(self.root, "worker", nid="RESEARCH-101")
        update_task(self.root, "RESEARCH-101", "worker", "at-risk", reason="Needs review")
        compact = inspect_changes(self.root, 1)
        self.assertEqual([2, 3], [item["graph_version"] for item in compact["changes"]])
        self.assertNotIn("before", compact["changes"][0])
        self.assertIn("changed_fields", compact["changes"][0])
        detailed = inspect_changes(self.root, 1, detail=True)
        self.assertIn("before", detailed["changes"][0])
        self.assertIn("after", detailed["changes"][0])
        self.assertIn("payload", detailed["changes"][0])

    def test_pause_resume_persists_handoff_and_blocks_lifecycle_mutation(self) -> None:
        taken = take_task(self.root, "worker", nid="RESEARCH-101")
        draft_path = self.handoff_for()
        jsonschema.validate(
            load_json(draft_path),
            load_json(PLUGIN_ROOT / "schemas" / "handoff-draft.schema.json"),
        )
        paused = pause_task(
            self.root,
            "RESEARCH-101",
            "worker",
            "Coffee break after validation research",
            draft_path,
            mode="hold",
            resume_minutes=60,
            expected_version=taken["packet"]["graph_version"],
        )
        self.assertEqual("paused", paused["status"])
        handoff_path = Path(paused["handoff"]["json"])
        handoff = load_json(handoff_path)
        jsonschema.validate(handoff, load_json(PLUGIN_ROOT / "schemas" / "handoff.schema.json"))
        state = load_json(self.root / ".pyramid" / "state.json")
        task_state = state["nodes"]["RESEARCH-101"]
        self.assertEqual("paused", task_state["execution"])
        self.assertEqual("worker", task_state["owner"])
        self.assertEqual(handoff["id"], task_state["active_handoff_id"])
        self.assertEqual(
            ["RESEARCH-101"],
            [node["id"] for node in inspect_project(self.root, paused=True)["nodes"]],
        )
        with self.assertRaisesRegex(PyramidError, "paused"):
            take_task(self.root, "other", nid="RESEARCH-101")
        with self.assertRaisesRegex(PyramidError, "resume"):
            update_task(self.root, "RESEARCH-101", "worker", "at-risk", reason="Still paused")
        with self.assertRaisesRegex(PyramidError, "resume"):
            audit_node(self.root, "RESEARCH-101", "auditor", "fail", self.audit_for("RESEARCH-101", "fail"))
        with self.assertRaisesRegex(PyramidError, "held by worker"):
            resume_task(self.root, "RESEARCH-101", "other", takeover=True)
        with self.assertRaisesRegex(PyramidError, "active claims"):
            archive_project(self.root, "owner", "Do not discard a handoff")

        resumed = resume_task(self.root, "RESEARCH-101", "worker")
        self.assertEqual("resumed", resumed["status"])
        self.assertEqual(handoff["id"], resumed["packet"]["handoff"]["id"])
        self.assertEqual("working", resumed["packet"]["execution"])
        self.assertTrue(validate_project(self.root)["valid"])
        event_types = [
            load_json(path)["type"]
            for path in sorted((self.root / ".pyramid" / "events").glob("*.json"))
        ]
        self.assertIn("task.paused", event_types)
        self.assertIn("task.resumed", event_types)
        update_task(self.root, "RESEARCH-101", "worker", "release")
        archived = archive_project(self.root, "owner", "Preserve completed handoff history")
        archived_handoffs = list((Path(archived["archive"]) / ".pyramid" / "handoffs").glob("*"))
        self.assertEqual(2, len(archived_handoffs))

    def test_resume_detects_stale_handoff_and_handoff_mode_allows_transfer(self) -> None:
        source = self.root / "src" / "worker.py"
        source.parent.mkdir(parents=True)
        source.write_text("value = 1\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Pyramid Test"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "pyramid@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "src/worker.py"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "fixture"], check=True)
        take_task(self.root, "worker", nid="RESEARCH-101")
        paused = pause_task(
            self.root,
            "RESEARCH-101",
            "worker",
            "Transfer work safely",
            self.handoff_for("transfer-handoff.json"),
            mode="handoff",
        )
        source.write_text("value = 2\n", encoding="utf-8")
        stale = resume_task(self.root, "RESEARCH-101", "next-worker")
        self.assertEqual("stale-handoff", stale["status"])
        self.assertIn("worktree changed", " ".join(stale["drift"]))
        resumed = resume_task(
            self.root,
            "RESEARCH-101",
            "next-worker",
            handoff_id=paused["handoff"]["id"],
            accept_stale=True,
        )
        self.assertEqual("resumed", resumed["status"])
        self.assertEqual("next-worker", resumed["packet"]["owner"])

    def test_handoff_content_is_hash_bound_to_pause_event(self) -> None:
        take_task(self.root, "worker", nid="RESEARCH-101")
        paused = pause_task(
            self.root,
            "RESEARCH-101",
            "worker",
            "Protect the continuation record",
            self.handoff_for("tamper-handoff.json"),
        )
        path = Path(paused["handoff"]["json"])
        handoff = load_json(path)
        handoff["summary"] = "Edited after the pause event"
        path.write_text(json.dumps(handoff), encoding="utf-8")
        validation = validate_project(self.root)
        self.assertFalse(validation["valid"])
        self.assertIn("content hash no longer matches", " ".join(validation["errors"]))
        with self.assertRaisesRegex(PyramidError, "content hash"):
            resume_task(self.root, "RESEARCH-101", "worker")

    def test_replan_preview_and_apply(self) -> None:
        original_context = inspect_project(self.root, summary=True)["context"]["id"]
        candidate = load_json(self.example)
        candidate["nodes"][2]["title"] = "Revalidate operation schema stability"
        path = self.write_json("replan.json", candidate)
        preview = replan_project(self.root, path, "planner", "New repository evidence", apply=False)
        self.assertIn("RESEARCH-101", preview["diff"]["changed_nodes"])
        applied = replan_project(self.root, path, "planner", "New repository evidence", apply=True)
        self.assertEqual(2, applied["diff"]["to_revision"])
        self.assertNotEqual(original_context, applied["context"]["id"])
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
        graph = load_visualization_graph(self.root)
        text = output.read_text(encoding="utf-8")
        self.assertEqual(6, rendered["nodes"])
        self.assertIn("pyramid-data", text)
        self.assertIn("Focus", text)
        self.assertIn("Star", text)
        self.assertIn("Needs rework", text)
        self.assertNotIn("fetch(", text)
        self.assertNotIn("agent", graph["nodes"][0])
        self.assertNotIn("required_evidence", graph["nodes"][0])

    def test_live_graph_follows_complete_publications_and_keeps_last_valid_snapshot(self) -> None:
        graph = load_visualization_graph(self.root)
        live = LiveGraphState(self.root, graph, poll_interval=0.02)
        initial_sequence = live.event()["sequence"]
        live.start()
        try:
            take_task(self.root, "worker", nid="RESEARCH-101")
            published = live.wait_for_event(initial_sequence, timeout=2.0)
            self.assertIsNotNone(published)
            self.assertEqual("graph", published["type"])
            self.assertEqual(2, published["graph_version"])
            body, _, current = live.snapshot()
            self.assertEqual(2, current["graph_version"])
            self.assertEqual("working", next(node for node in current["nodes"] if node["id"] == "RESEARCH-101")["availability"])
            self.assertEqual(2, json.loads(body)["graph_version"])

            graph_path = self.root / ".pyramid" / "graph.json"
            tampered = json.loads(graph_path.read_text(encoding="utf-8"))
            tampered["nodes"][0]["title"] = "Tampered outside the canonical runtime"
            graph_path.write_text(json.dumps(tampered), encoding="utf-8")
            rejected = live.wait_for_event(published["sequence"], timeout=2.0)
            self.assertIsNotNone(rejected)
            self.assertEqual("graph-error", rejected["type"])
            self.assertIn("canonical runtime projection", rejected["message"])
            _, _, last_valid = live.snapshot()
            self.assertEqual(2, last_valid["graph_version"])

            compile_project(self.root)
            recovered = live.wait_for_event(rejected["sequence"], timeout=2.0)
            self.assertIsNotNone(recovered)
            self.assertEqual("ready", recovered["type"])
            self.assertEqual(2, recovered["graph_version"])
        finally:
            live.stop()

    def test_live_server_serves_focus_view_graph_api_and_generated_task(self) -> None:
        server = LiveVisualizationServer(self.root, port=0, poll_interval=0.05)
        self.assertEqual("127.0.0.1", server.httpd.server_address[0])
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 2.0
            while not server._serving.is_set() and time.monotonic() < deadline:
                time.sleep(0.01)
            with urlopen(server.url, timeout=2.0) as response:
                html = response.read().decode("utf-8")
                self.assertEqual("DENY", response.headers["X-Frame-Options"])
            self.assertIn("new EventSource('/events')", html)
            self.assertIn("Focus", html)
            rebinding_request = Request(server.url, headers={"Host": "project-data.example"})
            with self.assertRaises(HTTPError) as rejected:
                urlopen(rebinding_request, timeout=2.0)
            self.assertEqual(HTTPStatus.MISDIRECTED_REQUEST, rejected.exception.code)
            with urlopen(server.url + "api/graph", timeout=2.0) as response:
                graph = json.loads(response.read())
                self.assertTrue(response.headers["ETag"])
            self.assertEqual(1, graph["graph_version"])
            source_path = next(node["source_path"] for node in graph["nodes"] if node["id"] == "RESEARCH-101")
            with urlopen(server.url + "project/" + source_path, timeout=2.0) as response:
                source = response.read().decode("utf-8")
            self.assertIn("RESEARCH-101", source)
        finally:
            server.shutdown()
            thread.join(timeout=2.0)

    def test_live_graph_ignores_metadata_only_recompiles(self) -> None:
        graph = load_visualization_graph(self.root)
        live = LiveGraphState(self.root, graph, poll_interval=0.02)
        initial = live.event()
        compile_project(self.root)
        self.assertFalse(live.refresh())
        self.assertEqual(initial, live.event())

    def test_live_graph_reports_a_context_waiting_for_projection(self) -> None:
        graph = load_visualization_graph(self.root)
        live = LiveGraphState(self.root, graph, poll_interval=0.02)
        with mock.patch("pyramid_core.compile_project", side_effect=OSError("projection failed")):
            with self.assertRaisesRegex(OSError, "projection failed"):
                take_task(self.root, "worker", nid="RESEARCH-101")
        self.assertEqual(2, load_json(self.root / ".pyramid" / "head.json")["context"]["graph_version"])
        self.assertEqual(1, load_json(self.root / ".pyramid" / "graph.json")["graph_version"])
        self.assertFalse(live.refresh())
        self.assertFalse(live.refresh())
        self.assertEqual("graph-error", live.event()["type"])
        self.assertIn("does not match canonical runtime state", live.event()["message"])
        compile_project(self.root)
        self.assertTrue(live.refresh())
        self.assertEqual("graph", live.event()["type"])
        self.assertEqual(2, live.event()["graph_version"])

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

    def test_graph_is_published_only_after_other_projections_complete(self) -> None:
        graph_path = self.root / ".pyramid" / "graph.json"
        graph_before = graph_path.read_bytes()
        original_write_text = Path.write_text

        def fail_final_readme(path: Path, data: str, *args: object, **kwargs: object) -> int:
            if path.name == "README.md" and "tasks" in path.parts:
                raise OSError("simulated projection failure")
            return original_write_text(path, data, *args, **kwargs)

        with mock.patch.object(Path, "write_text", new=fail_final_readme):
            with self.assertRaisesRegex(OSError, "simulated projection failure"):
                compile_project(self.root)
        self.assertEqual(graph_before, graph_path.read_bytes())

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
            (schema_dir / "head.schema.json", self.root / ".pyramid" / "head.json"),
            (schema_dir / "project.schema.json", self.root / ".pyramid" / "project.json"),
            (schema_dir / "final-report.schema.json", Path(closed["report"])),
            (schema_dir / "archive-manifest.schema.json", Path(archived["archive"]) / "manifest.json"),
        ]
        for schema_path, artifact_path in artifacts:
            schema = load_json(schema_path)
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.validate(load_json(artifact_path), schema)
        jsonschema.validate(load_json(self.expansion), load_json(schema_dir / "expansion-proposal.schema.json"))
        review_schema = load_json(schema_dir / "plan-review.schema.json")
        jsonschema.Draft202012Validator.check_schema(review_schema)
        example_review = load_json(PLUGIN_ROOT / "assets" / "example-plan-review.json")
        jsonschema.validate(example_review, review_schema)
        example_plan_hash = hashlib.sha256((PLUGIN_ROOT / "assets" / "example-plan.json").read_bytes()).hexdigest()
        self.assertEqual(example_plan_hash, example_review["source_plan"]["sha256"])
        self.assertEqual(example_plan_hash, example_review["revised_plan"]["sha256"])
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

    def test_impact_preview_hash_is_stable_for_identical_semantic_content(self) -> None:
        root = Path(self.temp.name) / "stable-impact-project"
        create_project(
            root,
            self.example,
            "planner",
            mode="brownfield",
            baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
            assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
        )
        candidate = PLUGIN_ROOT / "assets" / "example-assurance.json"
        first = impact_project(root, candidate, "auditor")
        second = impact_project(root, candidate, "auditor")
        self.assertEqual(first["assurance_sha256"], second["assurance_sha256"])

    def test_task_guard_survives_an_inspection_only_assurance_refresh(self) -> None:
        root = Path(self.temp.name) / "scoped-guard-project"
        create_project(
            root,
            self.example,
            "planner",
            mode="brownfield",
            baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
            assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
        )
        packet = take_task(root, "worker", nid="RESEARCH-101")["packet"]
        impact_project(
            root,
            PLUGIN_ROOT / "assets" / "example-assurance.json",
            "auditor",
            apply=True,
        )
        updated = update_task(
            root,
            "RESEARCH-101",
            "worker",
            "clear",
            expected_guard=packet["mutation_guard"],
        )
        self.assertEqual("clear", updated["status"])

    def test_scoped_audit_guard_ignores_global_assurance_status(self) -> None:
        root = Path(self.temp.name) / "scoped-audit-guard-project"
        create_project(
            root,
            self.example,
            "planner",
            mode="brownfield",
            baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
            assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
        )
        paths, plan, state = load_project(root)
        _, baseline, assurance = load_assurance_bundle(paths, plan)
        frontier = implementation_frontier(paths)
        before = audit_mutation_guard(
            plan, state, "RESEARCH-101", baseline, assurance, frontier
        )
        changed = copy.deepcopy(assurance)
        changed["status"] = "incomplete"
        changed["stale_reasons"] = ["Unrelated work is awaiting review."]
        after = audit_mutation_guard(
            plan, state, "RESEARCH-101", baseline, changed, frontier
        )
        self.assertEqual(before, after)

    def test_readiness_exposes_the_same_freshness_failure_as_audit(self) -> None:
        root = Path(self.temp.name) / "freshness-parity-project"
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
        result["changed_files"] = []
        result["changed_assets"] = ["ASSET-EXECUTOR"]
        update_task(
            root,
            "RESEARCH-101",
            "worker",
            "implemented",
            result_path=self.write_json("freshness-result.json", result),
        )
        impact_project(
            root,
            PLUGIN_ROOT / "assets" / "example-assurance.json",
            "auditor",
            apply=True,
        )
        summary = inspect_project(root, assurance_summary_view=True)["summary"]
        blocker = "Inspection INSPECTION-001 predates implementation for: RESEARCH-101"
        self.assertEqual("blocked", summary["status"])
        self.assertIn(blocker, summary["blockers"])
        readiness = inspect_project(root, audit_readiness="RESEARCH-101")
        self.assertFalse(readiness["ready"])
        self.assertIn(blocker, readiness["blockers"])
        with self.assertRaisesRegex(PyramidError, "predates implementation"):
            audit_node(
                root,
                "RESEARCH-101",
                "auditor",
                "pass",
                self.assurance_audit_for("RESEARCH-101"),
            )

    def test_evidence_only_result_does_not_stale_product_inspections(self) -> None:
        root = Path(self.temp.name) / "evidence-only-project"
        plan = load_json(self.example)
        research = next(node for node in plan["nodes"] if node["id"] == "RESEARCH-101")
        research["agent"]["effect"] = "evidence-only"
        research["agent"]["evidence_outputs"] = ["docs/reports/**"]
        research["agent"]["allowed_write_scope"] = ["docs/reports/**"]
        plan_path = self.write_json("evidence-only-plan.json", plan)
        create_project(
            root,
            plan_path,
            "planner",
            mode="brownfield",
            baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
            assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
        )
        take_task(root, "worker", nid="RESEARCH-101")
        result = load_json(self.result_for("RESEARCH-101", ["AC-101-01"]))
        result["changed_files"] = ["docs/reports/research.md"]
        result["change_effect"] = "evidence-only"
        result["changes"] = [
            {"path": "docs/reports/research.md", "class": "evidence"}
        ]
        updated = update_task(
            root,
            "RESEARCH-101",
            "worker",
            "implemented",
            result_path=self.write_json("evidence-only-result.json", result),
        )
        self.assertEqual([], updated["scope_drift"])
        self.assertEqual([], updated["stale_inspections"])
        assurance = load_json(root / ".pyramid" / "assurance.json")
        self.assertEqual("performed", assurance["inspections"][0]["status"])

    def test_declared_generated_output_avoids_drift_but_stales_covered_behavior(self) -> None:
        root = Path(self.temp.name) / "generated-output-project"
        plan = load_json(self.example)
        research = next(node for node in plan["nodes"] if node["id"] == "RESEARCH-101")
        research["agent"]["generated_outputs"] = [
            {"pattern": "generated/**", "asset_ids": ["ASSET-EXECUTOR"]}
        ]
        plan_path = self.write_json("generated-output-plan.json", plan)
        create_project(
            root,
            plan_path,
            "planner",
            mode="brownfield",
            baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
            assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
        )
        take_task(root, "worker", nid="RESEARCH-101")
        result = load_json(self.result_for("RESEARCH-101", ["AC-101-01"]))
        result["changed_files"] = ["generated/package.js"]
        result["change_effect"] = "mixed"
        result["changes"] = [
            {"path": "generated/package.js", "class": "generated"}
        ]
        updated = update_task(
            root,
            "RESEARCH-101",
            "worker",
            "implemented",
            result_path=self.write_json("generated-output-result.json", result),
        )
        self.assertEqual([], updated["scope_drift"])
        self.assertEqual(["INSPECTION-001"], updated["stale_inspections"])

    def test_generated_output_requires_a_known_baseline_asset(self) -> None:
        root = Path(self.temp.name) / "unknown-generated-asset-project"
        plan = load_json(self.example)
        research = next(node for node in plan["nodes"] if node["id"] == "RESEARCH-101")
        research["agent"]["generated_outputs"] = [
            {"pattern": "generated/**", "asset_ids": ["ASSET-DOES-NOT-EXIST"]}
        ]
        with self.assertRaisesRegex(PyramidError, "unknown baseline assets"):
            create_project(
                root,
                self.write_json("unknown-generated-asset-plan.json", plan),
                "planner",
                mode="brownfield",
                baseline_path=PLUGIN_ROOT / "assets" / "example-baseline.json",
                assurance_path=PLUGIN_ROOT / "assets" / "example-assurance.json",
            )

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
        (root / ".pyramid" / "head.json").unlink()
        legacy_state = load_json(root / ".pyramid" / "state.json")
        legacy_state.pop("context_id", None)
        legacy_state["lifecycle"].pop("change_dossier", None)
        (root / ".pyramid" / "state.json").write_text(
            json.dumps(legacy_state, indent=2) + "\n",
            encoding="utf-8",
        )
        for event_path in (root / ".pyramid" / "events").glob("*.json"):
            event = load_json(event_path)
            for field in (
                "plan_id",
                "plan_revision",
                "context_id",
                "previous_event_id",
                "previous_event_sha256",
            ):
                event.pop(field, None)
            event_path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
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

    def test_new_intent_preview_and_apply_from_completed_v3(self) -> None:
        self.complete_graph()
        close_project(self.root, "owner")
        candidate = load_json(self.example)
        candidate["plan_id"] = "PLAN-NEXT-V3"
        candidate["title"] = "Next V3 intent"
        candidate_path = self.write_json("next-v3-plan.json", candidate)

        preview = new_intent_project(
            self.root,
            candidate_path,
            "planner",
            "Start the next verified intent",
        )
        self.assertEqual("preview", preview["status"])
        self.assertEqual(["archive", "reset"], preview["transition"])
        self.assertTrue(preview["approval_required"])
        jsonschema.validate(
            preview,
            load_json(PLUGIN_ROOT / "schemas" / "new-intent-preview.schema.json"),
        )
        with self.assertRaisesRegex(PyramidError, "approved-by"):
            new_intent_project(
                self.root,
                candidate_path,
                "planner",
                "Start the next verified intent",
                apply=True,
            )

        started = new_intent_project(
            self.root,
            candidate_path,
            "planner",
            "Start the next verified intent",
            apply=True,
            approved_by="owner",
            approval_reference="conversation-101",
            approved_new_intent_sha256=preview["new_intent_sha256"],
            expected_version=preview["current"]["graph_version"],
        )
        self.assertEqual("started", started["status"])
        self.assertEqual("PLAN-NEXT-V3", inspect_project(self.root, summary=True)["plan_id"])
        self.assertIsNone(started["upgrade"])
        event_files = sorted((self.root / ".pyramid" / "events").glob("*.json"))
        created_event = load_json(event_files[-1])
        self.assertEqual(
            preview["new_intent_sha256"],
            created_event["payload"]["transition_approval"]["new_intent_sha256"],
        )
        self.assertTrue(validate_project(self.root)["valid"])

    def test_new_intent_upgrades_completed_v2_before_reset(self) -> None:
        self.complete_graph()
        close_project(self.root, "owner")
        (self.root / "src").mkdir()
        (self.root / "src" / "legacy.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / ".pyramid" / "project.json").unlink()
        (self.root / ".pyramid" / "head.json").unlink()
        legacy_state = load_json(self.root / ".pyramid" / "state.json")
        legacy_state.pop("context_id", None)
        (self.root / ".pyramid" / "state.json").write_text(
            json.dumps(legacy_state, indent=2) + "\n",
            encoding="utf-8",
        )
        for event_path in (self.root / ".pyramid" / "events").glob("*.json"):
            event = load_json(event_path)
            for field in (
                "plan_id",
                "plan_revision",
                "context_id",
                "previous_event_id",
                "previous_event_sha256",
            ):
                event.pop(field, None)
            event_path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
        candidate = load_json(self.example)
        candidate["plan_id"] = "PLAN-AFTER-V2"
        candidate["title"] = "Intent after completed V2"
        candidate_path = self.write_json("after-v2-plan.json", candidate)

        preview = new_intent_project(
            self.root,
            candidate_path,
            "planner",
            "Continue from the completed legacy intent",
            source_version="2.1",
        )
        self.assertEqual(["upgrade", "archive", "reset"], preview["transition"])
        self.assertIn("upgrade_sha256", preview["components"])
        started = new_intent_project(
            self.root,
            candidate_path,
            "planner",
            "Continue from the completed legacy intent",
            source_version="2.1",
            apply=True,
            approved_by="owner",
            approval_reference="conversation-102",
            approved_new_intent_sha256=preview["new_intent_sha256"],
            expected_version=preview["current"]["graph_version"],
        )
        self.assertIsNotNone(started["upgrade"])
        self.assertEqual("PLAN-AFTER-V2", inspect_project(self.root, summary=True)["plan_id"])
        project = load_json(self.root / ".pyramid" / "project.json")
        self.assertEqual(3, project["format_version"])
        self.assertEqual("brownfield", project["mode"])
        self.assertTrue((self.root / ".pyramid" / "baseline.json").exists())
        self.assertGreaterEqual(len(inspect_lifecycle(self.root)["archives"]), 2)
        self.assertTrue(validate_project(self.root)["valid"])

    def test_new_intent_blocks_an_active_plan_and_reports_legacy_skill_conflict(self) -> None:
        codex_home = Path(self.temp.name) / "codex-home"
        legacy_skill = codex_home / "skills" / "pyramid-task-planner" / "SKILL.md"
        legacy_skill.parent.mkdir(parents=True)
        legacy_skill.write_text(
            "---\nname: pyramid-task-planner\ndescription: old\n---\n"
            "## Default Output Shape\nCreate docs/tasks/README.md directly.\n",
            encoding="utf-8",
        )
        with mock.patch.dict("os.environ", {"CODEX_HOME": str(codex_home)}):
            route = intent_transition_route(self.root)
            self.assertFalse(route["can_start_new_intent"])
            self.assertEqual("continue-current-intent", route["recommended_action"])
            self.assertEqual("standalone-v2-planner", route["legacy_skill_conflicts"][0]["kind"])
            candidate = load_json(self.example)
            candidate["plan_id"] = "PLAN-BLOCKED-NEXT"
            preview = new_intent_project(
                self.root,
                self.write_json("blocked-next-plan.json", candidate),
                "planner",
                "Do not replace active work",
            )
        self.assertEqual("blocked", preview["status"])
        self.assertIn("current intent is active", " ".join(preview["blockers"]).lower())

    def test_new_intent_routes_verified_but_unclosed_plan_to_close_first(self) -> None:
        self.complete_graph()
        route = intent_transition_route(self.root)
        self.assertTrue(route["closure_ready"])
        self.assertFalse(route["can_start_new_intent"])
        self.assertEqual("close-then-preview-new-intent", route["recommended_action"])
        self.assertIn("not formally closed", " ".join(route["blockers"]))

    def test_new_intent_creates_a_fresh_project_without_transition_approval(self) -> None:
        root = Path(self.temp.name) / "fresh-new-intent"
        preview = new_intent_project(root, self.example, "planner", "Start the first intent")
        self.assertEqual(["create"], preview["transition"])
        self.assertFalse(preview["approval_required"])
        started = new_intent_project(
            root,
            self.example,
            "planner",
            "Start the first intent",
            apply=True,
        )
        self.assertEqual("started", started["status"])
        self.assertEqual("PLAN-001", inspect_project(root, summary=True)["plan_id"])

    def test_v3_cli_exposes_brownfield_and_upgrade_interfaces(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "pyramid.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        for command in ("new-intent", "upgrade", "assess", "impact", "diff"):
            self.assertIn(command, completed.stdout)
        inspect = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "pyramid.py"), "inspect", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("--assurance-summary", inspect.stdout)
        take = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "pyramid.py"), "take", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("--expected-context", take.stdout)
        visualize = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "pyramid.py"), "visualize", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        for option in ("--live", "--port", "--poll-interval", "--open"):
            self.assertIn(option, visualize.stdout)
        self.assertNotIn("--host", visualize.stdout)


if __name__ == "__main__":
    unittest.main()
