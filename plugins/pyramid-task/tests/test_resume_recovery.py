"""Recovery claims must break paused/blocked deadlocks without clearing safety state."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import jsonschema

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from pyramid_core import (  # noqa: E402
    PyramidError, audit_node, create_project, inspect_project, load_json,
    pause_task, reopen_node, resume_task, take_task, update_task, validate_project,
)


class RecoveryResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        create_project(self.root, PLUGIN_ROOT / "assets/example-plan.json", "planner")

    def pause_blocked(self, nid: str = "RESEARCH-101", mode: str = "handoff") -> dict:
        take_task(self.root, "worker", nid=nid)
        update_task(self.root, nid, "worker", "blocked", reason="Producer requires repair")
        return pause_task(
            self.root, nid, "worker", "Transfer the blocker investigation",
            PLUGIN_ROOT / "assets/example-handoff-draft.json", mode=mode,
        )

    def canonical_snapshot(self) -> dict[str, bytes]:
        return {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in (self.root / ".pyramid").rglob("*")
            if path.is_file() and path.suffix in {".json", ".md", ".jsonl"}
        }

    def test_default_refusal_is_read_only_and_points_to_recovery(self) -> None:
        self.pause_blocked()
        before = self.canonical_snapshot()
        with self.assertRaisesRegex(PyramidError, "--for-recovery"):
            resume_task(self.root, "RESEARCH-101", "next-worker")
        with self.assertRaisesRegex(PyramidError, "paused"):
            update_task(self.root, "RESEARCH-101", "worker", "clear")
        self.assertEqual(before, self.canonical_snapshot())

    def test_paused_query_includes_blocked_handoffs(self) -> None:
        self.pause_blocked()
        paused = inspect_project(self.root, paused=True)["nodes"]
        self.assertEqual(["RESEARCH-101"], [node["id"] for node in paused])
        self.assertEqual("blocked", paused[0]["health"])

    def test_recovery_preserves_blocker_and_handoff_until_owned_resolution(self) -> None:
        paused = self.pause_blocked()
        handoff_path = Path(paused["handoff"]["json"])
        handoff_before = handoff_path.read_bytes()
        before_state = load_json(self.root / ".pyramid/state.json")["nodes"]["RESEARCH-101"]
        recovered = resume_task(
            self.root, "RESEARCH-101", "next-worker", for_recovery=True,
            handoff_id=paused["handoff"]["id"],
        )
        event = recovered["event"]
        self.assertEqual("task.resumed", event["type"])
        self.assertTrue(event["payload"]["for_recovery"])
        self.assertEqual("working", recovered["packet"]["execution"])
        self.assertEqual("next-worker", recovered["packet"]["owner"])
        self.assertEqual(paused["handoff"]["id"], recovered["packet"]["handoff"]["id"])
        for field in ("health", "blocker", "verification", "last_result"):
            self.assertEqual(before_state[field], event["after"][field])
        self.assertEqual(handoff_before, handoff_path.read_bytes())
        jsonschema.validate(event, load_json(PLUGIN_ROOT / "schemas/event.schema.json"))
        with self.assertRaisesRegex(PyramidError, "does not own"):
            update_task(self.root, "RESEARCH-101", "worker", "clear")
        result = Path(self.temp.name) / "resolution.json"
        result.write_text(json.dumps({"checks": [{"command": "producer test", "result": "passed"}]}))
        risk = update_task(
            self.root, "RESEARCH-101", "next-worker", "at-risk",
            reason="Producer repaired; independent qualification remains", result_path=result,
        )
        self.assertEqual("at-risk", risk["event"]["after"]["health"])
        self.assertEqual(load_json(result), risk["event"]["payload"]["result"])
        update_task(self.root, "RESEARCH-101", "next-worker", "clear", reason="Qualification verified")
        self.assertTrue(validate_project(self.root)["valid"])

    def test_recovery_does_not_bypass_context_or_version_guard(self) -> None:
        self.pause_blocked()
        current = inspect_project(self.root, summary=True)["context"]
        for guard, message in (
            ({"graph_version": current["graph_version"] - 1, "context_id": current["id"]}, "Stale graph"),
            ({"graph_version": current["graph_version"], "context_id": "CTX-wrong"}, "Stale context"),
        ):
            with self.subTest(guard=guard):
                before = self.canonical_snapshot()
                with self.assertRaisesRegex(PyramidError, message):
                    resume_task(self.root, "RESEARCH-101", "next-worker", for_recovery=True, expected_version=guard)
                self.assertEqual(before, self.canonical_snapshot())

    def test_recovery_requires_explicit_stale_handoff_acceptance(self) -> None:
        self.pause_blocked()
        # An independent event changes the graph version; the original handoff stays immutable.
        reopen_node(self.root, "CONTRACT-102", "reviewer", "Contract needs rework")
        before = self.canonical_snapshot()
        stale = resume_task(self.root, "RESEARCH-101", "next-worker", for_recovery=True)
        self.assertEqual("stale-handoff", stale["status"])
        self.assertTrue(stale["drift"])
        self.assertEqual(before, self.canonical_snapshot())
        resumed = resume_task(self.root, "RESEARCH-101", "next-worker", for_recovery=True, accept_stale=True)
        self.assertEqual(stale["drift"], resumed["event"]["payload"]["accepted_stale_drift"])

    def test_recovery_preserves_hold_and_expired_takeover_rules(self) -> None:
        self.pause_blocked(mode="hold")
        before = self.canonical_snapshot()
        with self.assertRaisesRegex(PyramidError, "held by worker"):
            resume_task(self.root, "RESEARCH-101", "next-worker", for_recovery=True, takeover=True)
        self.assertEqual(before, self.canonical_snapshot())
        later = datetime.now(timezone.utc) + timedelta(hours=2)
        with mock.patch("pyramid_core.datetime", wraps=datetime) as clock:
            clock.now.return_value = later
            with self.assertRaisesRegex(PyramidError, "held by worker"):
                resume_task(self.root, "RESEARCH-101", "next-worker", for_recovery=True)
            resumed = resume_task(self.root, "RESEARCH-101", "next-worker", for_recovery=True, takeover=True)
        self.assertEqual("next-worker", resumed["packet"]["owner"])
        self.assertTrue(resumed["event"]["payload"]["takeover"])

    def test_recovery_rejects_wrong_or_tampered_handoff(self) -> None:
        paused = self.pause_blocked()
        before = self.canonical_snapshot()
        with self.assertRaisesRegex(PyramidError, "not the active handoff"):
            resume_task(self.root, "RESEARCH-101", "next-worker", for_recovery=True, handoff_id="wrong")
        self.assertEqual(before, self.canonical_snapshot())
        handoff_path = Path(paused["handoff"]["json"])
        record = load_json(handoff_path)
        record["summary"] = "Tampered continuation"
        handoff_path.write_text(json.dumps(record))
        before = self.canonical_snapshot()
        with self.assertRaisesRegex(PyramidError, "content hash"):
            resume_task(self.root, "RESEARCH-101", "next-worker", for_recovery=True, accept_stale=True)
        self.assertEqual(before, self.canonical_snapshot())

    def test_recovery_does_not_bypass_unverified_dependencies(self) -> None:
        take_task(self.root, "worker", nid="RESEARCH-101")
        result = Path(self.temp.name) / "research.json"
        result.write_text(json.dumps({
            "schema": "agent-result-v1", "task": "RESEARCH-101", "outcome": "implemented",
            "changed_files": [], "checks": [{"command": "test", "result": "passed"}],
            "acceptance_evidence": [{"criterion": "AC-101-01", "result": "passed", "reference": "test"}],
            "discovered_risks": [], "suggested_graph_changes": [],
        }))
        update_task(self.root, "RESEARCH-101", "worker", "implemented", result_path=result)
        audit = Path(self.temp.name) / "audit.json"
        audit.write_text(json.dumps({
            "schema": "audit-result-v1", "target": "RESEARCH-101", "result": "pass",
            "checks": [{"id": "check", "result": "passed", "evidence": ["test"]}],
            "affected_claims": ["RESEARCH-101"], "recommended_action": "advance",
        }))
        audit_node(self.root, "RESEARCH-101", "reviewer", "pass", audit)
        self.pause_blocked("CONTRACT-102")
        reopen_node(self.root, "RESEARCH-101", "reviewer", "Dependency regressed")
        before = self.canonical_snapshot()
        with self.assertRaisesRegex(PyramidError, "dependencies are not verified: RESEARCH-101"):
            resume_task(self.root, "CONTRACT-102", "next-worker", for_recovery=True, accept_stale=True)
        self.assertEqual(before, self.canonical_snapshot())

    def test_cli_recovery_round_trip(self) -> None:
        self.pause_blocked()
        context = inspect_project(self.root, summary=True)["context"]
        completed = subprocess.run([
            sys.executable, "-B", str(PLUGIN_ROOT / "scripts/pyramid.py"), "resume",
            "--project", str(self.root), "--node", "RESEARCH-101", "--actor", "next-worker",
            "--for-recovery", "--expected-version", str(context["graph_version"]),
            "--expected-context", context["id"], "--json",
        ], capture_output=True, text=True)
        self.assertEqual(0, completed.returncode, completed.stderr)
        response = json.loads(completed.stdout)
        self.assertEqual("resumed", response["status"])
        self.assertTrue(response["event"]["payload"]["for_recovery"])
        self.assertEqual("agent-task-v1", response["packet"]["schema"])
        self.assertEqual("working", response["packet"]["execution"])
        self.assertEqual("next-worker", response["packet"]["owner"])
        self.assertEqual("blocked", response["packet"]["health"])
        self.assertEqual("pyramid-event-reference-v1", response["event"]["schema"])
        event = load_json(self.root / response["event"]["path"])
        self.assertEqual(response["event"]["id"], event["id"])
        self.assertEqual("blocked", event["after"]["health"])
        self.assertEqual(event["after"]["blocker"], response["packet"]["blocker"])
        state = load_json(self.root / ".pyramid/state.json")["nodes"]["RESEARCH-101"]
        self.assertEqual(event["after"], state)


if __name__ == "__main__":
    unittest.main()
