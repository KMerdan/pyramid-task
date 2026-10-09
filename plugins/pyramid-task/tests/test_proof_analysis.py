from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import jsonschema

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'scripts'))
import pyramid
from pyramid_core import create_project, load_project, take_task, update_task
from pyramid_proof_analysis import analyze_proofs
from pyramid_verification import query_harness


class ProofAnalysisTests(unittest.TestCase):
    def setUp(self):
        usage = mock.patch.dict(os.environ, PYRAMID_USAGE='off')
        usage.start(); self.addCleanup(usage.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = (Path(self.temp.name) / 'project').resolve()
        self.plan = json.loads((PLUGIN / 'assets/example-plan.json').read_text())
        self.plan['schema_version'] = 2
        for node in self.plan['nodes']:
            node['agent']['allowed_write_scope'] = ['src/**']
            node['agent']['evidence_outputs'] = ['proof-output/**']
            for evidence in node['required_evidence']:
                evidence['verification'] = {'criteria': [c['id'] for c in node['acceptance_criteria']], 'method': 'command', 'procedure': 'Inspect unit fixture source', 'inputs': ['src/**'], 'observations': ['internal'], 'not_applicable': {'external': 'Unit contract fixture', 'visual': 'No rendered surface'}, 'environment': 'isolated test'}
        # Consumer reuse must not inflate the number of distinct families.
        for nid in ['GATE-290', 'OUTCOME-010', 'INTENT-001']:
            node = next(n for n in self.plan['nodes'] if n['id'] == nid)
            node['required_evidence'][0]['verification'] = {'criteria': [c['id'] for c in node['acceptance_criteria']], 'reuse': 'TASK-201/EVREQ-201-01'}
        plan = self.write('plan.json', self.plan)
        create_project(self.root, plan, 'planner', mode='greenfield')
        (self.root / 'src').mkdir()
        (self.root / 'src/main.ts').write_text('import "./dep"; import(variable);')
        (self.root / 'src/dep.ts').write_text('export {};')

    def write(self, name, value):
        path = Path(self.temp.name) / name
        path.write_text(json.dumps(value))
        return path

    def project_bytes(self):
        return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root / '.pyramid').rglob('*') if p.is_file()}

    def query(self, node='TASK-201', limit=1000):
        _, plan, state = load_project(self.root)
        return analyze_proofs(self.root, plan, state, node, limit=limit)

    def test_overlap_reuse_consumers_and_projection_leave_authority_unchanged(self):
        before = self.project_bytes()
        result = self.query()
        self.assertEqual(result['proofs'][0]['file_count'], 2)
        self.assertGreater(len(result['proofs'][0]['consumers']), 1)
        self.assertTrue(result['proofs'][0]['write_overlap'])
        self.assertFalse(result['current_proof']['ready'])
        self.assertEqual(before, self.project_bytes())
        schema = json.loads((PLUGIN / 'schemas/proof-analysis.schema.json').read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(result, schema)
        limited = self.query(limit=1)
        self.assertFalse(limited['scan']['complete'])

    def test_real_inspect_with_actual_tool_absence_preserves_canonical_and_reports_unknowns(self):
        empty_path = Path(self.temp.name) / 'empty-path'; empty_path.mkdir()
        env = dict(os.environ, PATH=str(empty_path), PYTHONDONTWRITEBYTECODE='1')
        before = self.project_bytes()
        command = [sys.executable, str(PLUGIN / 'scripts/pyramid.py'), 'inspect', '--project', str(self.root), '--proof-analysis', 'TASK-201', '--source-dependencies', '--analysis-provider', 'auto', '--json']
        process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result['dependencies']['provider'], 'python')
        self.assertTrue(result['dependencies']['unresolved'])
        self.assertFalse(result['scope_removal_authorized'])
        jsonschema.validate(result, json.loads((PLUGIN / 'schemas/proof-analysis.schema.json').read_text()))
        self.assertEqual(before, self.project_bytes())

    def test_inspect_default_does_not_launch_dependency_provider_and_bad_combinations_fail(self):
        with mock.patch('pyramid_dependencies._provider', side_effect=AssertionError('unexpected source scan')):
            args = pyramid.build_parser().parse_args(['inspect', '--project', str(self.root), '--summary', '--json'])
            _, status = pyramid.run(args)
            self.assertEqual(status, 0)
        with self.assertRaisesRegex(Exception, 'requires --proof-analysis'):
            pyramid.run(pyramid.build_parser().parse_args(['inspect', '--project', str(self.root), '--source-dependencies']))
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            self.query('MISSING')

    def test_real_inspect_default_ignores_available_ast_grep_and_explicit_auto_uses_it(self):
        tools = Path(self.temp.name) / 'tools'; tools.mkdir()
        marker = tools / 'invoked.txt'
        executable = tools / 'ast-grep'
        executable.write_text('#!' + sys.executable + '\nfrom pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("invoked")\nprint("ast-grep 0.45.3")\n')
        executable.chmod(0o755)
        env = dict(os.environ, PATH=str(tools), PYTHONDONTWRITEBYTECODE='1')
        before = self.project_bytes()
        command = [sys.executable, str(PLUGIN / 'scripts/pyramid.py'), 'inspect', '--project', str(self.root), '--proof-analysis', 'TASK-201', '--source-dependencies', '--json']
        process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result['dependencies']['provider'], 'python')
        self.assertEqual(result['dependencies']['requested_provider'], 'python')
        self.assertFalse(marker.exists())
        self.assertEqual(before, self.project_bytes())
        explicit = subprocess.run(command + ['--analysis-provider', 'auto'], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertTrue(marker.exists())
        self.assertEqual(json.loads(explicit.stdout)['dependencies']['requested_provider'], 'auto')
        self.assertEqual(before, self.project_bytes())

    def test_existing_proof_invalidates_after_source_edit_without_waiving_obligations(self):
        take_task(self.root, 'worker', nid='RESEARCH-101')
        _, plan, state = load_project(self.root)
        proof = query_harness(self.root, plan, state, 'RESEARCH-101')['proof_templates'][0]
        artifact = self.root / 'proof-output/unit-contract.txt'
        artifact.parent.mkdir(); artifact.write_text('Synthetic observation for proof invalidation regression only.')
        for obs in proof['run']['observations']:
            obs.update(result='passed', summary='Synthetic unit contract fixture', reviewer='unit-test-fixture', artifacts=[{'path': 'proof-output/unit-contract.txt', 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}])
        result = {'schema': 'agent-result-v1', 'task': 'RESEARCH-101', 'outcome': 'implemented', 'changed_files': [], 'discovered_risks': [], 'suggested_graph_changes': [], 'proofs': [proof]}
        update_task(self.root, 'RESEARCH-101', 'worker', 'implemented', result_path=self.write('result.json', result))
        current = self.query('RESEARCH-101')
        self.assertTrue(current['current_proof']['ready'])
        self.assertTrue(current['reusable_proofs'])
        (self.root / 'src/dep.ts').write_text('export const changed = true;')
        stale = self.query('RESEARCH-101')
        self.assertFalse(stale['current_proof']['ready'])
        self.assertIn('inputs changed', stale['current_proof']['blockers'][0])
        self.assertFalse(stale['reusable_proofs'])
        self.assertFalse(stale['scope_removal_authorized'])
