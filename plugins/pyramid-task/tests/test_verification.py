from __future__ import annotations

import base64
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'scripts'))

from pyramid_core import (
    PyramidError, archive_project, audit_node, close_project, create_project,
    inspect_project, load_json, load_project, replan_project, reset_project,
    pause_task, resume_task, expand_project, expansion_parent_snapshot,
    restore_project, take_task, update_task, validate_plan, validate_project,
)
from pyramid_verification import (
    ARTIFACT_DIR, VerificationError, contracts, input_snapshot, normalize_proofs,
    proof_readiness, query_harness,
)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.plan = load_json(PLUGIN / 'assets/example-plan.json')
        self.plan['schema_version'] = 2
        for node in self.plan['nodes']:
            node['agent']['evidence_outputs'] = ['proof-output/**']
            for ev in node['required_evidence']:
                ev['verification'] = {
                    'criteria': [c['id'] for c in node['acceptance_criteria']],
                    'method': 'review', 'procedure': f"Inspect the {node['id']} fixture",
                    'inputs': [f"inputs/{node['id']}.txt"], 'observations': ['internal'],
                    'not_applicable': {'external': 'Unit fixture has no external interface',
                                       'visual': 'No rendered surface in this runtime fixture'},
                    'environment': 'isolated unit fixture',
                }
        for nid in ['GATE-290', 'OUTCOME-010', 'INTENT-001']:
            ev = self.node(nid)['required_evidence'][0]
            ev['verification'] = {'criteria': ev['verification']['criteria'], 'reuse': 'TASK-201/EVREQ-201-01'}
        create_project(self.root, self.write('plan.json', self.plan), 'planner', mode='greenfield')
        (self.root / 'inputs').mkdir()
        for node in self.plan['nodes']:
            (self.root / 'inputs' / f"{node['id']}.txt").write_text(node['id'])
        (self.root / 'proof-output').mkdir()
        self.artifact = self.root / 'proof-output/check.txt'
        self.artifact.write_text('Observed fixture matches acceptance claim')

    def node(self, nid):
        return next(n for n in self.plan['nodes'] if n['id'] == nid)

    def write(self, name, payload):
        path = Path(self.temp.name) / name
        path.write_text(json.dumps(payload))
        return path

    def proof(self, nid):
        packet = inspect_project(self.root, harness=nid)
        proof = packet['proof_templates'][0]
        for obs in proof['run']['observations']:
            obs.update(result='passed', summary='Checked fixture against the stated acceptance claim',
                       reviewer='unit-test-fixture', artifacts=[{
                           'path': self.artifact.relative_to(self.root).as_posix(),
                           'sha256': hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
                       }])
        return proof

    def result(self, nid, proof=None):
        return {'schema': 'agent-result-v1', 'task': nid, 'outcome': 'implemented',
                'changed_files': [], 'checks': [], 'acceptance_evidence': [],
                'discovered_risks': [], 'suggested_graph_changes': [],
                'proofs': [proof or self.proof(nid)]}

    def audit(self, nid, proof=None):
        value = {'schema': 'audit-result-v1', 'target': nid, 'result': 'pass',
                 'affected_claims': [nid], 'recommended_action': 'advance'}
        if proof:
            value['proofs'] = [proof]
        return audit_node(self.root, nid, 'reviewer', 'pass', self.write('audit.json', value))

    def implement(self, nid, proof=None):
        take_task(self.root, 'worker', nid=nid)
        result = update_task(self.root, nid, 'worker', 'implemented',
                             result_path=self.write('result.json', self.result(nid, proof)))
        self.audit(nid)
        return result

    def complete(self):
        self.implement('RESEARCH-101')
        self.implement('CONTRACT-102')
        self.implement('TASK-201')
        for nid in ['GATE-290', 'OUTCOME-010', 'INTENT-001']:
            reuse = inspect_project(self.root, harness=nid)['reusable_proofs'][0]
            if nid == 'GATE-290':
                self.implement(nid, reuse)
            else:
                self.audit(nid, reuse)

    def test_bound_plan_and_published_results_match_schemas(self):
        self.assertEqual([], validate_plan(self.plan))
        jsonschema.validate(self.plan, load_json(PLUGIN / 'schemas/plan.schema.json'))
        self.implement('RESEARCH-101')
        _, _, state = load_project(self.root)
        for field, schema in [('last_result', 'agent-result'), ('last_audit', 'audit-result')]:
            payload = state['nodes']['RESEARCH-101'][field]
            jsonschema.validate(payload, load_json(PLUGIN / f'schemas/{schema}.schema.json'))
            path = payload['proofs'][0]['run']['observations'][0]['artifacts'][0]['path']
            self.assertTrue(path.startswith(ARTIFACT_DIR))
            self.assertTrue((self.root / path).is_file())
        self.assertTrue(validate_project(self.root)['valid'])
        self.assertTrue((self.root / 'docs/tasks/DEVELOPMENT_HARNESS.md').is_file())
        packet = inspect_project(self.root, nid='RESEARCH-101')
        self.assertIn('harness', packet)
        self.assertNotIn('verification', packet['required_evidence'][0])

    def test_published_example_and_cli_query(self):
        example = load_json(PLUGIN / 'assets/example-harness-plan.json')
        self.assertEqual([], validate_plan(example))
        jsonschema.validate(example, load_json(PLUGIN / 'schemas/plan.schema.json'))
        completed = subprocess.run([sys.executable, '-B', str(PLUGIN / 'scripts/pyramid.py'),
                                    'inspect', '--project', str(self.root), '--harness', 'TASK-201', '--json'],
                                   capture_output=True, text=True, check=True)
        self.assertEqual('candidate-bound', json.loads(completed.stdout)['mode'])

    def test_missing_contract_coverage_na_and_reuse_cycle_rejected(self):
        for mutation in ['missing', 'criteria', 'na', 'cycle', 'legacy']:
            with self.subTest(mutation=mutation):
                plan = copy.deepcopy(self.plan)
                ev = plan['nodes'][2]['required_evidence'][0]
                if mutation == 'missing':
                    ev.pop('verification')
                elif mutation == 'criteria':
                    ev['verification']['criteria'] = ['NONEXISTENT']
                elif mutation == 'na':
                    ev['verification']['not_applicable'] = {}
                elif mutation == 'cycle':
                    ev['verification'] = {'criteria': ['AC-101-01'], 'reuse': 'RESEARCH-101/EVREQ-101-01'}
                else:
                    plan['schema_version'] = 1
                self.assertTrue(validate_plan(plan))

    def test_query_is_read_only_templates_cannot_pass(self):
        head = (self.root / '.pyramid/head.json').read_bytes()
        packet = inspect_project(self.root, harness='RESEARCH-101')
        self.assertEqual(head, (self.root / '.pyramid/head.json').read_bytes())
        take_task(self.root, 'worker', nid='RESEARCH-101')
        with self.assertRaisesRegex(PyramidError, 'performed'):
            update_task(self.root, 'RESEARCH-101', 'worker', 'implemented', result_path=self.write(
                'result.json', self.result('RESEARCH-101', packet['proof_templates'][0])))
        self.assertFalse((self.root / ARTIFACT_DIR).exists())
        self.assertTrue(validate_project(self.root)['valid'])

    def test_candidate_change_rejects_stale_helper_or_worker_proof(self):
        proof = self.proof('RESEARCH-101')
        (self.root / 'inputs/RESEARCH-101.txt').write_text('candidate changed')
        take_task(self.root, 'worker', nid='RESEARCH-101')
        with self.assertRaisesRegex(PyramidError, 'candidate inputs changed'):
            update_task(self.root, 'RESEARCH-101', 'worker', 'implemented',
                        result_path=self.write('result.json', self.result('RESEARCH-101', proof)))
        self.assertTrue(validate_project(self.root)['valid'])

    def test_reporting_and_unrelated_claims_do_not_change_fingerprint(self):
        spec = contracts(self.plan, 'RESEARCH-101')[0]
        before = input_snapshot(self.root, self.plan, spec)
        self.artifact.write_text('different report')
        (self.root / 'inputs/TASK-201.txt').write_text('another task')
        take_task(self.root, 'worker', nid='RESEARCH-101')
        self.assertEqual(before, input_snapshot(self.root, self.plan, spec))

    def test_dirty_and_untracked_inputs_and_deletions_change_fingerprint(self):
        spec = contracts(self.plan, 'RESEARCH-101')[0]
        spec['inputs'] = ['inputs/*.txt']
        a = input_snapshot(self.root, self.plan, spec)
        extra = self.root / 'inputs/untracked.txt'
        extra.write_text('new')
        b = input_snapshot(self.root, self.plan, spec)
        self.assertNotEqual(a, b)
        extra.unlink()
        self.assertEqual(a, input_snapshot(self.root, self.plan, spec))

    def test_directory_scope_globs_work_consistently_and_reject_escapes(self):
        spec = contracts(self.plan, 'RESEARCH-101')[0]
        spec['inputs'] = ['inputs/**']
        self.assertEqual(len(self.plan['nodes']), input_snapshot(self.root, self.plan, spec)['file_count'])
        spec['inputs'] = ['inputs']
        self.assertEqual(len(self.plan['nodes']), input_snapshot(self.root, self.plan, spec)['file_count'])
        spec['inputs'] = ['inputs/**bad']
        (self.root / 'inputs/actually-bad').write_text('would match on Python 3.13')
        with self.assertRaisesRegex(VerificationError, 'Invalid input pattern'):
            input_snapshot(self.root, self.plan, spec)
        invalid = copy.deepcopy(self.plan)
        invalid['nodes'][2]['required_evidence'][0]['verification']['inputs'] = spec['inputs']
        self.assertTrue(validate_plan(invalid))
        outside = Path(self.temp.name) / 'outside.txt'
        outside.write_text('outside project')
        (self.root / 'inputs/link.txt').symlink_to(outside)
        spec['inputs'] = ['inputs/*']
        with self.assertRaisesRegex(VerificationError, 'escapes'):
            input_snapshot(self.root, self.plan, spec)

    def test_artifacts_are_checked_and_visual_needs_image(self):
        _, plan, state = load_project(self.root)
        nid = 'RESEARCH-101'
        proof = self.proof(nid)
        proof['run']['observations'][0]['artifacts'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(VerificationError, 'changed artifact'):
            normalize_proofs(self.root, plan, state, nid, self.result(nid, proof))
        spec = next(n for n in plan['nodes'] if n['id'] == nid)['required_evidence'][0]['verification']
        spec['observations'] = ['visual']
        spec['not_applicable'] = {'internal': 'Screenshot fixture', 'external': 'Screenshot fixture'}
        proof = query_harness(self.root, plan, state, nid)['proof_templates'][0]
        proof['run']['observations'] = self.proof(nid)['run']['observations']
        proof['run']['observations'][0]['kind'] = 'visual'
        with self.assertRaisesRegex(VerificationError, 'PNG'):
            normalize_proofs(self.root, plan, state, nid, self.result(nid, proof))
        image = self.root / 'proof-output/capture.png'
        image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
        proof['run']['observations'][0]['artifacts'] = [{'path': 'proof-output/capture.png', 'sha256': hashlib.sha256(image.read_bytes()).hexdigest()}]
        self.assertTrue(normalize_proofs(self.root, plan, state, nid, self.result(nid, proof))['proofs'])

    def test_normalization_does_not_hide_failed_checks(self):
        _, plan, state = load_project(self.root)
        payload = self.result('RESEARCH-101')
        payload['checks'] = [{'command': 'actual test', 'result': 'failed'}]
        with self.assertRaisesRegex(VerificationError, 'Cannot replace'):
            normalize_proofs(self.root, plan, state, 'RESEARCH-101', payload)
        for bad in [None, '', 0, [None]]:
            payload['checks'] = bad
            with self.assertRaisesRegex(VerificationError, 'Cannot replace'):
                normalize_proofs(self.root, plan, state, 'RESEARCH-101', payload)

    def test_reuse_deduplicates_artifacts_and_detects_changed_sources(self):
        self.complete()
        _, plan, state = load_project(self.root)
        ids = {state['nodes'][nid]['last_audit']['proofs'][0]['run']['id']
               for nid in ['TASK-201', 'GATE-290', 'OUTCOME-010', 'INTENT-001']}
        self.assertEqual(1, len(ids))
        self.assertEqual(1, len(list((self.root / ARTIFACT_DIR).iterdir())))
        self.assertTrue(inspect_project(self.root)['closure_ready'])
        (self.root / 'inputs/TASK-201.txt').write_text('changed after acceptance')
        self.assertFalse(inspect_project(self.root)['closure_ready'])
        ready = inspect_project(self.root, audit_readiness='INTENT-001')
        self.assertFalse(ready['ready'])
        self.assertTrue(any('candidate inputs changed' in x for x in ready['blockers']))
        with self.assertRaisesRegex(PyramidError, 'candidate inputs changed'):
            close_project(self.root, 'owner')

    def test_contract_change_invalidates_parent_closure_but_preserves_work(self):
        self.complete()
        candidate = copy.deepcopy(self.plan)
        task = next(n for n in candidate['nodes'] if n['id'] == 'TASK-201')
        task['acceptance_criteria'][0]['description'] += ' with additional requirement'
        replan_project(self.root, self.write('candidate.json', candidate), 'planner', 'new evidence', True)
        _, plan, state = load_project(self.root)
        for nid in ['TASK-201', 'GATE-290', 'OUTCOME-010', 'INTENT-001']:
            self.assertNotEqual('passed', state['nodes'][nid]['verification'])
        self.assertEqual('implemented', state['nodes']['TASK-201']['execution'])
        self.assertEqual('passed', state['nodes']['RESEARCH-101']['verification'])
        self.assertFalse(proof_readiness(self.root, plan, state, 'TASK-201')['ready'])
        legacy = copy.deepcopy(candidate)
        legacy['schema_version'] = 1
        with self.assertRaisesRegex(PyramidError, 'downgrade'):
            replan_project(self.root, self.write('legacy.json', legacy), 'planner', 'downgrade', True)

    def test_archive_reset_restore_preserves_proof_blobs(self):
        self.complete()
        close_project(self.root, 'owner')
        archived = archive_project(self.root, 'owner', 'retain evidence')
        next_plan = copy.deepcopy(self.plan)
        next_plan['plan_id'] = 'PLAN-NEXT'
        reset_project(self.root, self.write('next.json', next_plan), 'owner', 'next intent')
        self.assertFalse((self.root / ARTIFACT_DIR).exists())
        restore_project(self.root, archived['archive_id'], 'owner', 'continue prior intent')
        self.assertTrue(validate_project(self.root)['valid'])
        self.assertTrue((self.root / ARTIFACT_DIR).is_dir())
        _, plan, state = load_project(self.root)
        self.assertTrue(proof_readiness(self.root, plan, state, 'INTENT-001')['ready'])

    def test_legacy_adoption_is_explicit(self):
        root = Path(self.temp.name) / 'legacy'
        create_project(root, PLUGIN / 'assets/example-plan.json', 'planner', mode='greenfield')
        self.assertEqual('legacy-unbound', inspect_project(root, harness='RESEARCH-101')['mode'])
        replan_project(root, self.write('adopt.json', self.plan), 'planner', 'adopt harness', True)
        self.assertEqual('candidate-bound', inspect_project(root, harness='RESEARCH-101')['mode'])
        self.assertTrue(validate_project(root)['valid'])

    def test_pause_resume_retains_harness_and_rechecks_candidate(self):
        take_task(self.root, 'worker', nid='RESEARCH-101')
        proof = self.proof('RESEARCH-101')
        pause_task(self.root, 'RESEARCH-101', 'worker', 'continue later',
                   PLUGIN / 'assets/example-handoff-draft.json', mode='handoff')
        (self.root / 'inputs/RESEARCH-101.txt').write_text('changed while paused')
        result = resume_task(self.root, 'RESEARCH-101', 'next-worker', accept_stale=True)
        self.assertIn('harness', result['packet'])
        with self.assertRaisesRegex(PyramidError, 'candidate inputs changed'):
            update_task(self.root, 'RESEARCH-101', 'next-worker', 'implemented',
                        result_path=self.write('result.json', self.result('RESEARCH-101', proof)))
        self.assertTrue(validate_project(self.root)['valid'])

    def test_expansion_requires_child_proof_and_preserves_parent_contract(self):
        proposal = load_json(PLUGIN / 'assets/example-expansion.json')
        proposal['preserved_parent'] = expansion_parent_snapshot(self.node('TASK-201'))
        path = self.write('expansion.json', proposal)
        with self.assertRaisesRegex(PyramidError, 'verification'):
            expand_project(self.root, path, 'planner', apply=False)
        for node in proposal['nodes']:
            for ev in node['required_evidence']:
                ev['verification'] = {'criteria': [c['id'] for c in node['acceptance_criteria']],
                                      'reuse': 'TASK-201/EVREQ-201-01'}
        path = self.write('expansion.json', proposal)
        preview = expand_project(self.root, path, 'planner', apply=False)
        expand_project(self.root, path, 'planner', apply=True, approved_by='test-user',
                       approval_reference='isolated test', approved_proposal_sha256=preview['proposal_sha256'])
        self.assertTrue(validate_project(self.root)['valid'])
        _, plan, _ = load_project(self.root)
        parent = next(n for n in plan['nodes'] if n['id'] == 'TASK-201')
        self.assertEqual(self.node('TASK-201')['required_evidence'], parent['required_evidence'])
        self.assertTrue(inspect_project(self.root, harness='TASK-211')['contracts'])

    def test_failure_is_recordable_without_passing_proof(self):
        result = {'schema': 'audit-result-v1', 'target': 'RESEARCH-101', 'result': 'fail',
                  'checks': [{'id': 'CHECK-FAIL', 'result': 'failed', 'evidence': ['proof-output/check.txt']}],
                  'affected_claims': ['RESEARCH-101'], 'recommended_action': 'repair'}
        audit_node(self.root, 'RESEARCH-101', 'reviewer', 'fail', self.write('failure.json', result))
        self.assertEqual('failed', load_project(self.root)[2]['nodes']['RESEARCH-101']['verification'])
        self.assertTrue(validate_project(self.root)['valid'])

    def test_legacy_null_audit_checks_cannot_pass(self):
        from pyramid_core import _validate_audit_result
        for checks in [[None], [{'id': 'C', 'result': 'passed', 'evidence': []}],
                       [{'id': 'C', 'result': 'passed', 'evidence': ['e']}] * 2]:
            self.assertTrue(_validate_audit_result({'schema': 'audit-result-v1', 'target': 'N',
                                                  'result': 'pass', 'checks': checks}, 'N', 'pass'))


if __name__ == '__main__':
    unittest.main()
