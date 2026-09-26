from __future__ import annotations

import base64
import copy
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'scripts'))

from pyramid_core import (
    PyramidError, amend_task, archive_project, audit_node, close_project, create_project,
    inspect_project, load_json, load_project, replan_project, reset_project,
    pause_task, resume_task, expand_project, expansion_parent_snapshot,
    restore_project, take_task, update_task, validate_plan, validate_project,
)
from pyramid_verification import (
    ARTIFACT_DIR, VerificationError, contracts, input_snapshot, normalize_proofs,
    proof_readiness, query_harness,
)
from pyramid_output import compact_response


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
        """Synthetic observations for evidence-contract tests, not an executed probe."""
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

    def amendment(self, write_paths, context_paths=None):
        return self.write('amendment.json', {
            'schema': 'pyramid-amendment-v1', 'task': 'RESEARCH-101',
            'reason': 'Existing helper belongs to the same bounded investigation.',
            'boundary_review': 'Outcome, acceptance, authority and procedure remain unchanged.',
            'add_write_paths': write_paths, 'add_context_paths': context_paths or [],
        })

    def test_amendment_rejects_untracked_proof_scope_without_mutation(self):
        take_task(self.root, 'worker', nid='RESEARCH-101')
        outside = self.root / 'helper.txt'
        outside.write_text('not covered by the task proof')
        head = (self.root / '.pyramid/head.json').read_bytes()
        with self.assertRaisesRegex(PyramidError, 'outside.*verification inputs'):
            amend_task(self.root, self.amendment(['helper.txt']), 'worker')
        self.assertEqual(head, (self.root / '.pyramid/head.json').read_bytes())
        self.assertTrue(validate_project(self.root)['valid'])

    def test_covered_amendment_preserves_proof_until_source_changes(self):
        taken = take_task(self.root, 'worker', nid='RESEARCH-101')
        proof = self.proof('RESEARCH-101')
        path = self.amendment(['inputs/RESEARCH-101.txt'])
        preview = amend_task(self.root, path, 'worker')
        applied = amend_task(self.root, path, 'worker', True, preview['amendment_id'])
        self.assertEqual(taken['packet']['owner'], applied['owner'])
        self.assertNotEqual(taken['packet']['mutation_guard'], applied['mutation_guard'])
        self.assertEqual(proof['run']['inputs_sha256'], self.proof('RESEARCH-101')['run']['inputs_sha256'])
        self.assertEqual(proof['run']['contract_sha256'], self.proof('RESEARCH-101')['run']['contract_sha256'])
        self.assertEqual('working', load_project(self.root)[2]['nodes']['RESEARCH-101']['execution'])
        (self.root / 'inputs/RESEARCH-101.txt').write_text('candidate changed after amendment')
        with self.assertRaisesRegex(PyramidError, 'candidate inputs changed'):
            update_task(self.root, 'RESEARCH-101', 'worker', 'implemented',
                        result_path=self.write('result.json', self.result('RESEARCH-101', proof)),
                        expected_guard=applied['mutation_guard'])
        self.assertTrue(validate_project(self.root)['valid'])

        # A fresh actual observation can finish the same claim after the rejection.
        updated = update_task(self.root, 'RESEARCH-101', 'worker', 'implemented',
                              result_path=self.write('result.json', self.result('RESEARCH-101')),
                              expected_guard=applied['mutation_guard'])
        self.assertEqual('implemented', updated['status'])
        self.assertLess(len(json.dumps(compact_response(updated, 'update'))), 0.7 * len(json.dumps(updated)))
        self.audit('RESEARCH-101')
        self.assertTrue(validate_project(self.root)['valid'])

    def test_amendment_resolves_reused_inputs_and_preserves_context_only_proof(self):
        ev = self.node('RESEARCH-101')['required_evidence'][0]
        ev['verification'] = {'criteria': ['AC-101-01'], 'reuse': 'TASK-201/EVREQ-201-01'}
        replan_project(self.root, self.write('reuse-plan.json', self.plan), 'planner', 'share probe', True)
        take_task(self.root, 'worker', nid='RESEARCH-101')
        path = self.amendment(['inputs/TASK-201.txt'])
        preview = amend_task(self.root, path, 'worker')
        amend_task(self.root, path, 'worker', True, preview['amendment_id'])
        before = self.proof('RESEARCH-101')['run']['inputs_sha256']
        (self.root / 'notes.txt').write_text('non-binding read context')
        path = self.amendment([], ['notes.txt'])
        preview = amend_task(self.root, path, 'worker')
        amend_task(self.root, path, 'worker', True, preview['amendment_id'])
        self.assertEqual(before, self.proof('RESEARCH-101')['run']['inputs_sha256'])
        self.assertTrue(validate_project(self.root)['valid'])

    def test_amendment_uses_capture_globs_and_exclusions_without_requiring_unbuilt_setup(self):
        ev = self.node('RESEARCH-101')['required_evidence'][0]
        ev['verification']['inputs'] = ['inputs/**', 'proof-output/**', 'future-fixture.txt']
        replan_project(self.root, self.write('glob-plan.json', self.plan), 'planner', 'declare setup', True)
        take_task(self.root, 'worker', nid='RESEARCH-101')
        # Missing future setup does not prevent a covered amendment; it still blocks capture.
        preview = amend_task(self.root, self.amendment(['inputs/TASK-201.txt']), 'worker')
        self.assertEqual('preview', preview['status'])
        with self.assertRaisesRegex(PyramidError, 'outside.*verification inputs'):
            amend_task(self.root, self.amendment(['proof-output/check.txt']), 'worker')
        self.assertTrue(inspect_project(self.root, harness='RESEARCH-101')['setup_blockers'])

    def test_compact_bound_update_preserves_proof_failures_and_recovery_queries(self):
        take_task(self.root, 'worker', nid='RESEARCH-101')
        full = update_task(self.root, 'RESEARCH-101', 'worker', 'blocked', reason='Probe failed',
                           result_path=self.write('result.json', {**self.result('RESEARCH-101'),
                               'checks': [{'command': 'probe', 'result': 'failed'}]}))
        compact = compact_response(full, 'update')
        self.assertEqual('agent-status-v1', compact['packet']['schema'])
        self.assertNotIn('contracts', compact['packet']['harness'])
        self.assertEqual(['contracts'], compact['omitted_fields']['packet.harness'])
        self.assertEqual(full['packet']['harness']['capture'], compact['packet']['harness']['capture'])
        self.assertEqual(full['event']['payload'], compact['event']['payload'])
        self.assertEqual('Probe failed', compact['packet']['blocker'])
        self.assertEqual(full['packet']['harness'], inspect_project(self.root, nid='RESEARCH-101')['harness'])
        self.assertEqual(full['packet'], compact_response(full, 'resume')['packet'])
        self.assertLess(len(json.dumps(compact)), 0.8 * len(json.dumps(full)))

    def test_executed_probe_failure_repair_and_audit_through_cli(self):
        nid = 'RESEARCH-101'
        source = self.root / f'inputs/{nid}.txt'
        probe = self.root / 'inputs/probe.py'
        probe.write_text(
            "from pathlib import Path\n"
            "ok = Path('inputs/RESEARCH-101.txt').read_text() == 'RESEARCH-101'\n"
            "print('PASS identity' if ok else 'FAIL identity')\n"
            "raise SystemExit(0 if ok else 1)\n"
        )
        command = [sys.executable, '-B', 'inputs/probe.py']
        spec = self.node(nid)['required_evidence'][0]['verification']
        spec.update(method='command', procedure=shlex.join(command),
                    inputs=[f'inputs/{nid}.txt', 'inputs/probe.py'])
        self.node(nid)['agent']['allowed_write_scope'].append(f'inputs/{nid}.txt')
        replan_project(self.root, self.write('probe-plan.json', self.plan),
                       'planner', 'Exercise a real subprocess observation', True)

        def cli(*args, expected_code=0):
            completed = subprocess.run(
                [sys.executable, '-B', str(PLUGIN / 'scripts/pyramid.py'), *args,
                 '--project', str(self.root), '--json'],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(expected_code, completed.returncode, completed.stdout + completed.stderr)
            return json.loads(completed.stdout)

        def observe(expected_code, name):
            # Capture BEFORE execution; derive observations from the real exit/output.
            proof = cli('inspect', '--harness', nid)['proof_templates'][0]
            completed = subprocess.run(command, cwd=self.root, capture_output=True,
                                       text=True, timeout=10)
            self.assertEqual(expected_code, completed.returncode, completed.stderr)
            status = 'passed' if completed.returncode == 0 else 'failed'
            artifact = self.root / 'proof-output' / name
            artifact.write_text(completed.stdout + completed.stderr)
            for observation in proof['run']['observations']:
                observation.update(result=status, summary=completed.stdout.strip(),
                                   reviewer='subprocess-fixture', artifacts=[{
                                       'path': artifact.relative_to(self.root).as_posix(),
                                       'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                                   }])
            result = self.result(nid, proof)
            result['changed_files'] = [f'inputs/{nid}.txt']
            result['checks'] = [{'command': shlex.join(command), 'result': status,
                                 'evidence': [artifact.relative_to(self.root).as_posix()]}]
            return result, artifact

        taken = cli('take', '--node', nid, '--actor', 'worker')
        guard = taken['packet']['mutation_guard']
        source.write_text('broken identity')
        failed, failure_log = observe(1, 'failure.txt')
        self.assertEqual('FAIL identity\n', failure_log.read_text())
        failed_path = self.write('failed-probe.json', failed)
        head = (self.root / '.pyramid/head.json').read_bytes()
        rejected = cli('update', '--node', nid, '--actor', 'worker', '--status', 'implemented',
                       '--expected-guard', guard, '--result', str(failed_path), expected_code=2)
        self.assertIn('Every required observation must be performed', rejected['error'])
        self.assertEqual(head, (self.root / '.pyramid/head.json').read_bytes())
        self.assertFalse((self.root / ARTIFACT_DIR).exists())
        failed.pop('proofs')  # Failed observations belong in checks, not passing proof runs.
        blocked = cli('update', '--node', nid, '--actor', 'worker', '--status', 'blocked',
                      '--reason', 'Identity probe failed', '--expected-guard', guard,
                      '--result', str(self.write('failed-probe.json', failed)))
        self.assertEqual(failed['checks'], blocked['event']['payload']['result']['checks'])
        failure_event = load_json(self.root / blocked['event']['path'])

        source.write_text(nid)
        passed, success_log = observe(0, 'success.txt')
        self.assertEqual('PASS identity\n', success_log.read_text())
        updated = cli('update', '--node', nid, '--actor', 'worker', '--status', 'implemented',
                      '--expected-guard', blocked['packet']['mutation_guard'],
                      '--result', str(self.write('passed-probe.json', passed)))
        self.assertEqual('pending', updated['packet']['verification'])
        stored = load_project(self.root)[2]['nodes'][nid]['last_result']
        artifact = stored['proofs'][0]['run']['observations'][0]['artifacts'][0]
        self.assertEqual(success_log.read_bytes(), (self.root / artifact['path']).read_bytes())
        evidence = self.write('probe-audit.json', {
            'schema': 'audit-result-v1', 'target': nid, 'result': 'pass',
            'affected_claims': [nid], 'recommended_action': 'advance',
        })
        cli('audit', '--node', nid, '--actor', 'reviewer', '--result', 'pass',
            '--evidence', str(evidence))
        self.assertEqual('passed', cli('inspect', '--node', nid)['verification'])
        self.assertEqual(failure_event, load_json(self.root / blocked['event']['path']))
        self.assertTrue(cli('validate')['valid'])

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
