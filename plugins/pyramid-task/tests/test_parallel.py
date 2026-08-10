from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from pyramid import build_parser  # noqa: E402
from pyramid_core import (  # noqa: E402
    create_project,
    inspect_project,
    load_json,
    take_task,
    update_task,
)
from pyramid_parallel import build_parallel_frontier  # noqa: E402


def task(
    nid: str,
    scope: str,
    *,
    wave: int = 0,
    level: int = 2,
    effect: str = "source-change",
    generated: list[dict] | None = None,
) -> dict:
    agent = {
        "required_context": [],
        "allowed_write_scope": [scope] if scope else [],
        "effect": effect,
        "commands": [],
        "deliverables": [f"Deliver {nid}"],
        "non_goals": [],
    }
    if generated:
        agent["generated_outputs"] = generated
    return {
        "id": nid,
        "kind": "implementation",
        "title": f"Task {nid}",
        "summary": f"Implement {nid}.",
        "level": level,
        "wave": wave,
        "workstream": nid.lower(),
        "selection": "primary",
        "source_requirements": ["REQ-001"],
        "acceptance_criteria": [],
        "required_evidence": [],
        "agent": agent,
    }


def frontier(
    nodes: list[dict],
    *,
    edges: list[dict] | None = None,
    assurance: dict | None = None,
    max_agents: int = 4,
    candidate_ids: list[str] | None = None,
) -> dict:
    plan = {
        "plan_id": "PLAN-TEST",
        "revision": 1,
        "nodes": nodes,
        "edges": edges or [],
    }
    ids = candidate_ids or [node["id"] for node in nodes]
    return build_parallel_frontier(
        plan,
        ids,
        task_guards={nid: f"GUARD-TASK-{nid}" for nid in ids},
        context={
            "id": "CTX-TEST",
            "plan_id": "PLAN-TEST",
            "plan_revision": 1,
            "graph_version": 1,
        },
        graph_version=1,
        max_agents=max_agents,
        assurance=assurance,
    )


def assurance(
    task_ids: list[str],
    *,
    policy: str = "pre-audit",
    drift_task: str | None = None,
) -> dict:
    drift = []
    if drift_task:
        drift.append({"task": drift_task, "status": "open"})
    return {
        "impacts": [
            {
                "asset_id": "ASSET-SHARED",
                "task_ids": task_ids,
                "status": "confirmed",
            }
        ],
        "inspections": [
            {
                "id": "INSPECTION-SHARED",
                "asset_ids": ["ASSET-SHARED"],
                "task_ids": task_ids,
                "refresh_policy": policy,
            }
        ],
        "scope_drift": drift,
    }


class ParallelFrontierTests(unittest.TestCase):
    def test_disjoint_same_wave_tasks_group_deterministically(self) -> None:
        nodes = [task("TASK-B", "src/b/**"), task("TASK-A", "src/a/**")]
        first = frontier(nodes, candidate_ids=["TASK-B", "TASK-A"])
        second = frontier(nodes, candidate_ids=["TASK-A", "TASK-B"])
        self.assertEqual(first, second)
        self.assertEqual([["TASK-A", "TASK-B"]], [group["task_ids"] for group in first["groups"]])
        self.assertEqual("PARALLEL-W0-6DD642B133", first["groups"][0]["id"])
        self.assertEqual("separate-worktrees", first["groups"][0]["isolation"])

    def test_group_id_changes_with_wave_or_membership(self) -> None:
        wave_zero = frontier([task("TASK-A", "src/a/**"), task("TASK-B", "src/b/**")])
        wave_one = frontier(
            [task("TASK-A", "src/a/**", wave=1), task("TASK-B", "src/b/**", wave=1)]
        )
        different_member = frontier([task("TASK-A", "src/a/**"), task("TASK-C", "src/c/**")])

        ids = {
            wave_zero["groups"][0]["id"],
            wave_one["groups"][0]["id"],
            different_member["groups"][0]["id"],
        }
        self.assertEqual(3, len(ids))

    def test_write_and_generated_scope_overlap_conflict(self) -> None:
        exact = frontier([task("TASK-A", "src/shared/file.py"), task("TASK-B", "src/shared/file.py")])
        self.assertEqual([], exact["groups"])
        self.assertIn("write-scope-overlap:src/shared/file.py<->src/shared/file.py", exact["conflicts"][0]["reasons"])

        generated = frontier(
            [
                task(
                    "TASK-A",
                    "src/a/**",
                    generated=[{"pattern": "dist/**", "asset_ids": ["ASSET-DIST"]}],
                ),
                task("TASK-B", "dist/package/**"),
            ]
        )
        self.assertEqual([], generated["groups"])
        self.assertTrue(any(reason.startswith("write-scope-overlap:dist/**") for reason in generated["conflicts"][0]["reasons"]))

    def test_direct_dependency_and_different_waves_do_not_group(self) -> None:
        coupled = frontier(
            [task("TASK-A", "src/a/**"), task("TASK-B", "src/b/**")],
            edges=[{"from": "TASK-B", "to": "TASK-A", "type": "requires"}],
        )
        self.assertEqual([], coupled["groups"])
        self.assertIn("dependency-coupling:TASK-B->TASK-A:requires", coupled["conflicts"][0]["reasons"])

        waves = frontier([task("TASK-A", "src/a/**"), task("TASK-B", "src/b/**", wave=1)])
        self.assertEqual([], waves["groups"])
        self.assertEqual(2, len(waves["serial_tasks"]))

    def test_transitive_dependency_does_not_group(self) -> None:
        result = frontier(
            [task("TASK-A", "src/a/**"), task("TASK-B", "src/b/**")],
            edges=[
                {"from": "TASK-B", "to": "GATE-MIDDLE", "type": "validation-requires"},
                {"from": "GATE-MIDDLE", "to": "TASK-A", "type": "integration-requires"},
            ],
        )
        self.assertEqual([], result["groups"])
        self.assertIn("dependency-coupling:TASK-B~>TASK-A:transitive", result["conflicts"][0]["reasons"])

    def test_dotfile_scopes_retain_their_path_identity(self) -> None:
        result = frontier([task("TASK-A", ".github/**"), task("TASK-B", "github/**")])
        self.assertEqual([["TASK-A", "TASK-B"]], [group["task_ids"] for group in result["groups"]])

    def test_assurance_policy_controls_shared_asset_batching(self) -> None:
        nodes = [task("TASK-A", "src/a/**"), task("TASK-B", "src/b/**")]
        unsafe = frontier(nodes, assurance=assurance(["TASK-A", "TASK-B"], policy="per-change"))
        self.assertEqual([], unsafe["groups"])
        self.assertTrue(any(reason.startswith("shared-assets-without-batch-refresh") for reason in unsafe["conflicts"][0]["reasons"]))

        safe = frontier(nodes, assurance=assurance(["TASK-A", "TASK-B"], policy="pre-audit"))
        self.assertEqual([["TASK-A", "TASK-B"]], [group["task_ids"] for group in safe["groups"]])
        self.assertEqual("pre-audit", safe["groups"][0]["effective_refresh_boundary"])
        self.assertEqual(["INSPECTION-SHARED"], safe["groups"][0]["shared_inspection_ids"])
        self.assertEqual(
            [{"id": "INSPECTION-SHARED", "refresh_policy": "pre-audit"}],
            safe["groups"][0]["shared_inspections"],
        )

    def test_strictest_shared_refresh_boundary_wins(self) -> None:
        nodes = [task("TASK-A", "src/a/**"), task("TASK-B", "src/b/**")]
        bundle = assurance(["TASK-A", "TASK-B"], policy="pre-audit")
        bundle["inspections"].append(
            {
                "id": "INSPECTION-WAVE",
                "asset_ids": ["ASSET-SHARED"],
                "task_ids": ["TASK-A", "TASK-B"],
                "refresh_policy": "per-wave",
            }
        )
        result = frontier(nodes, assurance=bundle)
        self.assertEqual("per-wave", result["groups"][0]["effective_refresh_boundary"])

    def test_release_policy_refreshes_before_audit_when_freshness_requires_it(self) -> None:
        nodes = [task("TASK-A", "src/a/**"), task("TASK-B", "src/b/**")]
        result = frontier(
            nodes,
            assurance=assurance(
                ["TASK-A", "TASK-B"], policy="release"
            ),
        )
        group = result["groups"][0]
        self.assertEqual(
            [{"id": "INSPECTION-SHARED", "refresh_policy": "release"}],
            group["shared_inspections"],
        )
        self.assertEqual("pre-audit", group["effective_refresh_boundary"])

    def test_every_shared_asset_needs_batchable_inspection_coverage(self) -> None:
        nodes = [task("TASK-A", "src/a/**"), task("TASK-B", "src/b/**")]
        bundle = assurance(["TASK-A", "TASK-B"], policy="pre-audit")
        bundle["impacts"].append(
            {
                "asset_id": "ASSET-UNCOVERED",
                "task_ids": ["TASK-A", "TASK-B"],
                "status": "confirmed",
            }
        )
        result = frontier(nodes, assurance=bundle)
        self.assertEqual([], result["groups"])
        self.assertIn(
            "shared-assets-without-batch-refresh:ASSET-UNCOVERED",
            result["conflicts"][0]["reasons"],
        )

    def test_broad_scope_and_open_drift_stay_serial(self) -> None:
        result = frontier(
            [task("TASK-A", "**"), task("TASK-B", "src/b/**"), task("TASK-C", "src/c/**")],
            assurance=assurance(["TASK-B"], drift_task="TASK-B"),
        )
        serial = {item["task"]: item["reasons"] for item in result["serial_tasks"]}
        self.assertTrue(any(reason.startswith("broad-write-scope") for reason in serial["TASK-A"]))
        self.assertIn("open-scope-drift", serial["TASK-B"])

    def test_external_or_traversing_scopes_stay_serial(self) -> None:
        result = frontier(
            [
                task("TASK-A", "../outside/**"),
                task("TASK-B", "C:\\outside\\**"),
                task("TASK-C", "src/c/**"),
            ]
        )
        serial = {item["task"]: item["reasons"] for item in result["serial_tasks"]}
        self.assertTrue(any(reason.startswith("broad-write-scope") for reason in serial["TASK-A"]))
        self.assertTrue(any(reason.startswith("broad-write-scope") for reason in serial["TASK-B"]))

    def test_agent_budget_caps_balanced_groups(self) -> None:
        nodes = [task(f"TASK-{letter}", f"src/{letter.lower()}/**") for letter in "ABCDE"]
        result = frontier(nodes, max_agents=3)
        self.assertEqual([2, 3], sorted(len(group["task_ids"]) for group in result["groups"]))
        self.assertEqual([3, 2], [len(group["task_ids"]) for group in result["groups"]])
        self.assertEqual(5, result["parallel_task_count"])

    def test_missing_brownfield_impact_or_write_scope_stays_serial(self) -> None:
        no_impact = frontier(
            [task("TASK-A", "src/a/**"), task("TASK-B", "src/b/**")],
            assurance={"impacts": [], "inspections": [], "scope_drift": []},
        )
        self.assertEqual([], no_impact["groups"])
        self.assertTrue(
            all(
                "missing-impact-coverage" in item["reasons"]
                for item in no_impact["serial_tasks"]
            )
        )

        no_scope = frontier([task("TASK-A", ""), task("TASK-B", "")])
        self.assertEqual([], no_scope["groups"])
        self.assertTrue(
            all(
                "missing-write-scope-for-writing-effect" in item["reasons"]
                for item in no_scope["serial_tasks"]
            )
        )

        read_only = frontier(
            [
                task("TASK-A", "", effect="evidence-only"),
                task("TASK-B", "", effect="evidence-only"),
            ]
        )
        self.assertEqual("shared-read-only", read_only["groups"][0]["isolation"])

    def test_output_matches_published_schema(self) -> None:
        result = frontier([task("TASK-A", "src/a/**"), task("TASK-B", "src/b/**")])
        schema = load_json(PLUGIN_ROOT / "schemas" / "parallel-frontier.schema.json")
        jsonschema.validate(result, schema)

    def test_cli_exposes_parallel_frontier_options(self) -> None:
        args = build_parser().parse_args(
            ["inspect", "--project", "/tmp/project", "--parallel-ready", "--max-agents", "3"]
        )
        self.assertTrue(args.parallel_ready)
        self.assertEqual(3, args.max_agents)

    def test_pure_modules_do_not_depend_on_transaction_facade(self) -> None:
        for module in ("pyramid_graph.py", "pyramid_parallel.py"):
            source = (PLUGIN_ROOT / "scripts" / module).read_text(encoding="utf-8")
            self.assertNotIn("import pyramid_core", source)
            self.assertNotIn("from pyramid_core", source)


class ParallelRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        plan = load_json(PLUGIN_ROOT / "assets" / "example-plan.json")
        plan["edges"] = [
            edge
            for edge in plan["edges"]
            if not (edge["from"] == "CONTRACT-102" and edge["to"] == "RESEARCH-101")
        ]
        plan["edges"].append(
            {
                "from": "GATE-290",
                "to": "RESEARCH-101",
                "type": "validation-requires",
            }
        )
        for node in plan["nodes"]:
            if node["id"] == "CONTRACT-102":
                node["wave"] = 0
        plan_path = Path(self.temp.name) / "parallel-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        create_project(self.root, plan_path, "planner")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def canonical_snapshot(self) -> dict[str, bytes]:
        pyramid = self.root / ".pyramid"
        return {
            str(path.relative_to(pyramid)): path.read_bytes()
            for path in sorted(pyramid.rglob("*"))
            if path.is_file()
        }

    def test_parallel_inspection_is_read_only_and_schema_valid(self) -> None:
        before = self.canonical_snapshot()
        result = inspect_project(self.root, parallel_ready=True, max_agents=3)
        after = self.canonical_snapshot()
        self.assertEqual(before, after)
        self.assertEqual([["CONTRACT-102", "RESEARCH-101"]], [group["task_ids"] for group in result["groups"]])
        jsonschema.validate(result, load_json(PLUGIN_ROOT / "schemas" / "parallel-frontier.schema.json"))

    def test_parallel_task_guards_survive_unrelated_claims(self) -> None:
        result = inspect_project(self.root, parallel_ready=True, max_agents=3)
        guards = {
            item["task"]: item["claim_guard"]
            for item in result["groups"][0]["tasks"]
        }
        research = take_task(
            self.root,
            "researcher",
            nid="RESEARCH-101",
            expected_guard=guards["RESEARCH-101"],
        )
        taken = take_task(
            self.root,
            "contractor",
            nid="CONTRACT-102",
            expected_guard=guards["CONTRACT-102"],
        )
        self.assertEqual("CONTRACT-102", taken["packet"]["task"])
        update_task(
            self.root,
            "RESEARCH-101",
            "researcher",
            "at-risk",
            reason="Forward-test post-claim guard isolation.",
            expected_guard=research["packet"]["mutation_guards"]["task"],
        )
        update_task(
            self.root,
            "CONTRACT-102",
            "contractor",
            "at-risk",
            reason="Forward-test cross-worker guard isolation.",
            expected_guard=taken["packet"]["mutation_guards"]["task"],
        )


if __name__ == "__main__":
    unittest.main()
