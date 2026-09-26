from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

import pyramid
import pyramid_core
from pyramid_core import (
    PyramidError, archive_project, create_project, inspect_project, new_intent_project,
    reset_project, restore_project, take_task, validate_project,
)


class LegacyRemovalTests(unittest.TestCase):
    def setUp(self):
        # Disable measurement only; all project operations and CLI processes are real.
        usage = mock.patch.dict(os.environ, {"PYRAMID_USAGE": "off"})
        usage.start()
        self.addCleanup(usage.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.example = PLUGIN / "assets/example-plan.json"
        create_project(self.root, self.example, "planner", mode="greenfield")
        candidate = json.loads(self.example.read_text())
        candidate["plan_id"] = "PLAN-NEXT"
        self.candidate = Path(self.temp.name) / "next.json"
        self.candidate.write_text(json.dumps(candidate))

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() if p.is_file() else None
                for p in self.root.rglob("*")}

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(PLUGIN / "scripts/pyramid.py"), *args],
            capture_output=True, text=True, timeout=30,
        )

    def test_migration_command_and_new_intent_option_are_removed(self):
        self.assertNotIn("upgrade", pyramid.build_parser().get_default("command_catalog"))
        self.assertFalse(hasattr(pyramid_core, "upgrade_project"))
        before = self.snapshot()
        removed = self.cli("upgrade", "--project", str(self.root), "--actor", "owner", "--preview")
        self.assertEqual(2, removed.returncode)
        self.assertIn("invalid choice", removed.stderr)
        removed_option = self.cli(
            "new-intent", "--project", str(self.root), "--plan", str(self.candidate),
            "--actor", "owner", "--reason", "next", "--preview", "--from-version", "2.1",
        )
        self.assertEqual(2, removed_option.returncode)
        self.assertIn("unrecognized arguments", removed_option.stderr)
        self.assertEqual(before, self.snapshot())

    def test_legacy_operations_reject_all_lifecycle_states_without_writes(self):
        (self.root / ".pyramid/project.json").unlink()
        (self.root / ".pyramid/head.json").unlink()
        (self.root / ".pyramid/lock").unlink()
        state_path = self.root / ".pyramid/state.json"
        state = json.loads(state_path.read_text())
        # Serialized legacy fixtures; no mocked runtime results or fabricated passing checks.
        for status in ("active", "completed", "archived"):
            with self.subTest(status=status):
                state["lifecycle"]["status"] = status
                state_path.write_text(json.dumps(state))
                before = self.snapshot()
                validation = validate_project(self.root)
                self.assertFalse(validation["valid"])
                self.assertTrue(any("Unsupported legacy" in e for e in validation["errors"]))
                for operation in (
                    lambda: take_task(self.root, "worker", nid="RESEARCH-101"),
                    lambda: reset_project(self.root, self.candidate, "owner", "next"),
                    lambda: new_intent_project(self.root, self.candidate, "owner", "next"),
                    lambda: new_intent_project(self.root, self.candidate, "owner", "next", apply=True),
                ):
                    with self.assertRaisesRegex(PyramidError, "Unsupported legacy"):
                        operation()
                for command in ("doctor", "compile", "clean", "inspect"):
                    result = self.cli(command, "--project", str(self.root), "--json")
                    self.assertNotEqual(0, result.returncode, result.stdout)
                    self.assertIn("Unsupported legacy", result.stdout)
                self.assertEqual(before, self.snapshot())

    def test_legacy_archive_is_rejected_before_archiving_current_v3_project(self):
        archived = archive_project(self.root, "owner", "snapshot")
        reset_project(self.root, self.candidate, "owner", "next")
        source = Path(archived["archive"])
        (source / ".pyramid/project.json").unlink()
        (source / ".pyramid/head.json").unlink()
        before = self.snapshot()
        with self.assertRaisesRegex(PyramidError, "Unsupported legacy"):
            restore_project(self.root, archived["archive_id"], "owner", "restore")
        self.assertEqual(before, self.snapshot())
        self.assertTrue(validate_project(self.root)["valid"])

    def test_existing_v3_migration_provenance_remains_valid(self):
        path = self.root / ".pyramid/project.json"
        manifest = json.loads(path.read_text())
        manifest.update(last_upgraded_at=manifest["created_at"], last_upgraded_by="former-owner",
                        upgraded_from="2.1", migrations=[{
                            "id": "HISTORICAL-MIGRATION", "from": "2.1", "to": 3,
                            "at": manifest["created_at"], "actor": "former-owner",
                            "preview_sha256": "a" * 64, "archive_id": "HISTORICAL-ARCHIVE",
                        }])
        path.write_text(json.dumps(manifest))
        head_path = self.root / ".pyramid/head.json"
        head = json.loads(head_path.read_text())
        head["files"]["project"] = hashlib.sha256(path.read_bytes()).hexdigest()
        head_path.write_text(json.dumps(head))
        before = path.read_bytes()
        validation = validate_project(self.root)
        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual(3, inspect_project(self.root, summary=True)["project"]["format_version"])
        take_task(self.root, "worker", nid="RESEARCH-101")
        self.assertEqual(before, path.read_bytes())
