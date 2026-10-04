from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'scripts'))
import pyramid_core as core
from pyramid_verification import VerificationError, input_snapshot


class FootprintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        core.create_project(self.root, PLUGIN / 'assets/example-plan.json', 'planner', mode='greenfield')
        for rel, data in {'inputs/probe.py': 'print("probe")', 'proof-output/failed.txt': 'FAIL actual fixture',
                          'build/candidate.bin': 'generated', 'scratch/mystery.dat': 'unknown'}.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}

    def test_public_cli_summary_and_detail_do_not_mutate(self):
        before = self.snapshot()
        summaries = []
        for flags in [[], ['--footprint-detail']]:
            proc = subprocess.run([sys.executable, '-B', str(PLUGIN / 'scripts/pyramid.py'),
                                   'inspect', '--project', str(self.root), '--footprint', '--json', *flags],
                                  capture_output=True, text=True,
                                  env={**os.environ, 'PYRAMID_USAGE': 'off', 'PYTHONDONTWRITEBYTECODE': '1'})
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            value = json.loads(proc.stdout)
            self.assertFalse(value['deletion_authorized'])
            self.assertTrue(value['scan']['complete'])
            self.assertEqual(bool(flags), 'files' in value)
            self.assertLess(len(proc.stdout), 60000)
            self.assertEqual(before, self.snapshot())
            summaries.append(value)
        self.assertEqual(summaries[0]['totals'], summaries[1]['totals'])

    def test_contract_classes_current_failed_reference_and_unknown_retention(self):
        from pyramid_assurance import artifact_footprint
        _, plan, state = core.load_project(self.root)
        node = next(n for n in plan['nodes'] if n['id'] == 'RESEARCH-101')
        node['agent']['evidence_outputs'] = ['proof-output/**']
        node['agent']['generated_outputs'] = [{'pattern': 'build/**', 'asset_ids': ['ASSET-BUILD']}]
        node['required_evidence'][0]['verification'] = {'inputs': ['inputs/**']}
        failure = {'schema': 'audit-result-v1', 'target': 'RESEARCH-101', 'result': 'fail',
                   'checks': [{'id': 'CHECK-FAIL', 'result': 'failed', 'evidence': ['proof-output/failed.txt']}],
                   'affected_claims': ['RESEARCH-101'], 'recommended_action': 'repair'}
        path = Path(self.temp.name) / 'failed-audit.json'
        path.write_text(json.dumps(failure))
        core.audit_node(self.root, 'RESEARCH-101', 'reviewer', 'fail', path)
        state = core.load_project(self.root)[2]
        before = self.snapshot()
        report = artifact_footprint(self.root, plan, state, None, detail=True)
        files = {x['path']: x for x in report['files']}
        self.assertEqual('proof-input', files['inputs/probe.py']['class'])
        self.assertEqual('declared-generated', files['build/candidate.bin']['class'])
        self.assertEqual('declared-evidence', files['proof-output/failed.txt']['class'])
        self.assertTrue(files['proof-output/failed.txt']['currently_referenced'])
        self.assertEqual('unknown', files['scratch/mystery.dat']['class'])
        self.assertEqual(before, self.snapshot())
        self.assertEqual('failed', state['nodes']['RESEARCH-101']['verification'])

    def test_scan_is_bounded_and_symlinks_are_not_followed(self):
        from pyramid_assurance import artifact_footprint
        _, plan, state = core.load_project(self.root)
        link = self.root / 'external-link'
        link.symlink_to(Path(self.temp.name), target_is_directory=True)
        before = self.snapshot()
        full = artifact_footprint(self.root, plan, state, None, detail=True)
        self.assertEqual('symlink-not-followed', next(x for x in full['files'] if x['path'] == 'external-link')['class'])
        bounded = artifact_footprint(self.root, plan, state, None, limit=2, detail=True)
        self.assertFalse(bounded['scan']['complete'])
        self.assertLessEqual(bounded['scan']['entries'], 2)
        self.assertLessEqual(len(bounded['files']), 2)
        self.assertEqual(before, self.snapshot())

    def test_evidence_output_cannot_hide_an_actual_proof_input(self):
        _, plan, _ = core.load_project(self.root)
        plan['nodes'][0]['agent']['evidence_outputs'] = ['inputs/**']
        spec = {'inputs': ['inputs/**', 'scratch/**']}
        with self.assertRaisesRegex(VerificationError, 'overlaps declared evidence'):
            input_snapshot(self.root, plan, spec)

    def test_repository_capture_excludes_dedicated_staging_not_all_inputs(self):
        _, plan, _ = core.load_project(self.root)
        plan['nodes'][0]['agent']['evidence_outputs'] = ['proof-output/**']
        before = input_snapshot(self.root, plan, {'inputs': ['**/*']})
        (self.root / 'proof-output/failed.txt').write_text('new retained report')
        self.assertEqual(before, input_snapshot(self.root, plan, {'inputs': ['**/*']}))
        (self.root / 'inputs/probe.py').write_text('changed real source')
        self.assertNotEqual(before, input_snapshot(self.root, plan, {'inputs': ['**/*']}))

    def test_invalid_scan_options_refuse_without_mutating(self):
        before = self.snapshot()
        for kwargs in [{'footprint_detail': True}, {'footprint': True, 'footprint_limit': 0},
                       {'footprint': True, 'footprint_limit': 100001}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(core.PyramidError):
                core.inspect_project(self.root, **kwargs)
            self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
