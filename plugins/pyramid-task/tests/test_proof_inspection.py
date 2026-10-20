"""Opt-in diagnostics preserve proof eligibility and complete readiness truth."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import jsonschema
import test_verification as fixtures

from pyramid_core import PyramidError, audit_node, create_project, load_json, load_project, replan_project
from pyramid_output import compact_response, readiness_summary
from pyramid_queries import inspect_project
import pyramid_queries
import pyramid_verification


PLUGIN = Path(__file__).resolve().parents[1]


class ProofInspectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.HarnessTests('test_query_is_read_only_templates_cannot_pass')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.schema = load_json(PLUGIN / 'schemas/proof-inspection.schema.json')

    def canonical_bytes(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in (self.root / '.pyramid').rglob('*') if p.is_file()}

    def command(self, *args, code=0):
        result = subprocess.run(
            [sys.executable, '-B', str(PLUGIN / 'scripts/pyramid.py'), args[0],
             '--project', str(self.root), *args[1:], '--json'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(code, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def cli(self, *args, code=0):
        return self.command('inspect', *args, code=code)

    def test_p2_legal_health_result_shapes_are_diagnosed_without_policy_changes(self):
        self.command('take', '--node', 'RESEARCH-101', '--actor', 'worker')
        cases = [
            ({'checks': None}, 0, True),
            ({'checks': {'probe': 'failed'}}, 0, True),
            ({'result': {'code': 'fail'}, 'checks': []}, 0, True),
            ({'checks': [None, 'failed', {'command': 'probe', 'result': {'code': 'failed'}}]}, 0, True),
            ({'checks': [{'command': 'probe', 'result': None, 'status': 'failed'}]}, 1, False),
            ({'checks': [{'command': 'probe', 'result': '', 'status': 'fail'}]}, 1, False),
            ({'checks': [{'command': 'probe', 'result': 'passed', 'status': 'failed'}]}, 1, True),
            ({'checks': [{'command': 'probe', 'result': 'passed', 'status': 'pass'}]}, 0, False),
        ]
        for value, signals, unknown in cases:
            with self.subTest(payload=value):
                path = self.fixture.write('health-result.json', value)
                self.command('update', '--node', 'RESEARCH-101', '--actor', 'worker', '--status', 'blocked',
                             '--reason', 'Controlled failed or incomplete check', '--result', str(path))
                self.command('update', '--node', 'RESEARCH-101', '--actor', 'worker', '--status', 'clear',
                             '--reason', 'Separate health from retained check evidence')
                self.assertTrue(self.command('validate')['valid'])
                before = self.canonical_bytes()
                default = self.cli('--harness', 'RESEARCH-101')
                readiness = self.cli('--audit-readiness', 'RESEARCH-101')
                explained = self.cli('--harness', 'RESEARCH-101', '--explain')
                jsonschema.validate(explained, self.schema)
                failure = explained['explanation']['failure_context']
                self.assertEqual(signals, failure['signal_count'])
                self.assertEqual(unknown, failure['unknown_count'] > 0)
                self.assertEqual(bool(signals or unknown), failure['requires_disposition_review'])
                self.assertEqual(default, self.cli('--harness', 'RESEARCH-101'))
                self.assertEqual(readiness, self.cli('--audit-readiness', 'RESEARCH-101'))
                self.assertEqual(before, self.canonical_bytes())

    def test_p2_assessment_source_recovers_omitted_checks_evidence_and_detects_drift(self):
        import hashlib
        self.fixture.implement('RESEARCH-101')
        checks = []
        for i in range(7):
            path = self.root / f'proof-output/failure-{i}.log'
            path.write_text(f'Controlled reported failure {i}; not a production execution\n')
            checks.append({'id': f'CHECK-{i}' + ('-长检查名' * 80 if i == 0 else ''),
                           'result': 'failed', 'evidence': [path.relative_to(self.root).as_posix()]})
        audit = {'schema': 'audit-result-v1', 'target': 'RESEARCH-101', 'result': 'fail',
                 'affected_claims': ['RESEARCH-101'], 'recommended_action': 'repair', 'checks': checks}
        path = self.fixture.write('failure-details.json', audit)
        self.command('audit', '--node', 'RESEARCH-101', '--actor', 'reviewer', '--result', 'fail', '--evidence', str(path))
        before = self.canonical_bytes()
        explained = self.cli('--harness', 'RESEARCH-101', '--explain')
        jsonschema.validate(explained, self.schema)
        e = explained['explanation']
        self.assertGreater(e['failure_context']['omitted_signals'], 0)
        self.assertNotIn('assessment', e['detail_queries'])
        locator = e['detail_sources']['assessment']
        def read_source():
            selected = json.loads(Path(locator['path']).read_text())
            for token in locator['json_pointer'].lstrip('/').split('/'):
                selected = selected[token.replace('~1', '/').replace('~0', '~')]
            fields = {key: selected.get(key) for key in locator['fields']}
            digest = hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False,
                                               separators=(',', ':')).encode()).hexdigest()
            return fields, digest
        recovered, digest = read_source()
        self.assertEqual(locator['assessment_sha256'], digest)
        self.assertEqual(checks, recovered['last_audit']['checks'])
        for check in recovered['last_audit']['checks']:
            self.assertTrue((self.root / check['evidence'][0]).is_file())
        self.assertEqual(before, self.canonical_bytes())
        audit['checks'] = [{'id': 'NEW-FAILURE', 'result': 'failed', 'evidence': ['new controlled assessment']}]
        path = self.fixture.write('new-failure-details.json', audit)
        self.command('audit', '--node', 'RESEARCH-101', '--actor', 'reviewer', '--result', 'fail', '--evidence', str(path))
        self.assertNotEqual(locator['assessment_sha256'], read_source()[1])
        current = self.cli('--harness', 'RESEARCH-101', '--explain')['explanation']
        self.assertEqual(read_source()[1], current['detail_sources']['assessment']['assessment_sha256'])
        self.assertNotEqual(e['scan_sha256'], current['scan_sha256'])

    def test_explain_uses_same_validator_and_does_not_change_default_or_state(self):
        self.fixture.implement('RESEARCH-101')
        before = self.canonical_bytes()
        original = pyramid_verification.validate_run
        with mock.patch.object(pyramid_verification, 'validate_run', wraps=original) as validate:
            default = inspect_project(self.root, harness='RESEARCH-101')
            default_calls = validate.call_count
            validate.reset_mock()
            explained = inspect_project(self.root, harness='RESEARCH-101', harness_explain=True)
            self.assertEqual(default_calls, validate.call_count)
        jsonschema.validate(explained, self.schema)
        self.assertEqual(len(default['reusable_proofs']), explained['explanation']['passed_pair_count'])
        self.assertEqual([], explained['explanation']['diagnostics'])
        self.assertEqual(default, self.cli('--harness', 'RESEARCH-101'))
        self.assertEqual(explained, self.cli('--harness', 'RESEARCH-101', '--explain'))
        self.assertEqual(before, self.canonical_bytes())

    def test_explain_reports_input_and_artifact_rejections_without_inventing_history(self):
        self.fixture.implement('RESEARCH-101')
        source = self.root / 'inputs/RESEARCH-101.txt'
        original = source.read_bytes()
        source.write_text('a changed current candidate')
        explained = inspect_project(self.root, harness='RESEARCH-101', harness_explain=True, harness_explain_page=1)
        self.assertEqual(0, explained['explanation']['passed_pair_count'])
        self.assertTrue(any('candidate inputs changed' in d['reason']
                            for d in explained['explanation']['diagnostics']))
        source.write_bytes(original)
        _, plan, state = load_project(self.root)
        artifact = state['nodes']['RESEARCH-101']['last_result']['proofs'][0]['run']['observations'][0]['artifacts'][0]
        (self.root / artifact['path']).unlink()
        # Storage integrity rejects a missing canonical blob before any query.
        error = self.cli('--harness', 'RESEARCH-101', '--explain', code=2)
        self.assertIn('atomically published head', error['error'])
        explained = pyramid_verification.query_harness(
            self.root, plan, state, 'RESEARCH-101', explain=True, explain_page=1)
        self.assertEqual(0, explained['explanation']['passed_pair_count'])
        self.assertTrue(any('Missing or out-of-project artifact' in d['reason']
                            for d in explained['explanation']['diagnostics']))
        self.assertEqual('current-state-last-result-and-audit', explained['explanation']['scope'])
        jsonschema.validate(explained, self.schema)

    def test_valid_local_run_does_not_waive_stale_passed_dependency(self):
        self.fixture.implement('RESEARCH-101')
        self.fixture.implement('CONTRACT-102')
        (self.root / 'inputs/RESEARCH-101.txt').write_text('stale upstream proof')
        explained = inspect_project(self.root, harness='CONTRACT-102', harness_explain=True)
        self.assertGreater(explained['explanation']['passed_pair_count'], 0)
        full = inspect_project(self.root, audit_readiness='CONTRACT-102')
        summary = inspect_project(self.root, audit_readiness='CONTRACT-102', readiness_summary=True)
        self.assertFalse(full['ready'])
        self.assertEqual(full['ready'], summary['ready'])
        self.assertTrue(any('candidate inputs changed' in value for value in full['blockers']))
        before = self.canonical_bytes()
        with self.assertRaisesRegex(PyramidError, 'candidate inputs changed'):
            self.fixture.audit('CONTRACT-102')
        self.assertEqual(before, self.canonical_bytes())

    def test_run_explanation_does_not_hide_a_reported_audit_failure(self):
        self.fixture.implement('RESEARCH-101')
        evidence = self.fixture.write('failed-audit.json', {
            'schema': 'audit-result-v1', 'target': 'RESEARCH-101', 'result': 'fail',
            'affected_claims': ['RESEARCH-101'], 'recommended_action': 'repair',
            'checks': [{'id': 'REPORTED-FAILURE', 'result': 'failed', 'evidence': ['actual failure report']}],
        })
        audit_node(self.root, 'RESEARCH-101', 'reviewer', 'fail', evidence)
        explained = inspect_project(self.root, harness='RESEARCH-101', harness_explain=True)
        self.assertGreater(explained['explanation']['passed_pair_count'], 0)
        self.assertTrue(explained['explanation']['failure_context']['requires_disposition_review'])
        summary = inspect_project(self.root, audit_readiness='RESEARCH-101', readiness_summary=True)
        self.assertFalse(summary['ready'])
        self.assertTrue(summary['blockers'])
        self.assertEqual('failed', load_project(self.root)[2]['nodes']['RESEARCH-101']['verification'])

    def test_failed_audit_retake_old_run_recovery_characterizes_unchanged_v3(self):
        """A diagnostic is not a new historical veto; retain the unsafe boundary explicitly."""
        import os
        cli = PLUGIN / 'scripts/pyramid.py'
        transcript = []
        def command(*args):
            p = subprocess.run([sys.executable, '-B', str(cli), args[0], '--project', str(self.root),
                                *args[1:], '--json'], capture_output=True, text=True, timeout=30)
            self.assertEqual(0, p.returncode, p.stdout + p.stderr)
            data = json.loads(p.stdout)
            transcript.append({'arguments': args, 'exit_code': p.returncode,
                               'response': fixtures.evidence_response(data)})
            return data
        self.fixture.implement('RESEARCH-101')
        old = load_project(self.root)[2]['nodes']['RESEARCH-101']['last_result']['proofs'][0]['run']['id']
        evidence = self.fixture.write('failed-audit.json', {
            'schema': 'audit-result-v1', 'target': 'RESEARCH-101', 'result': 'fail',
            'affected_claims': ['RESEARCH-101'], 'recommended_action': 'repair',
            'checks': [{'id': 'REPORTED-FAILURE', 'result': 'failed', 'evidence': ['controlled audit failure']}],
        })
        command('audit', '--node', 'RESEARCH-101', '--actor', 'reviewer', '--result', 'fail', '--evidence', str(evidence))
        failed_bytes = self.canonical_bytes()
        self.assertFalse(self.cli('--audit-readiness', 'RESEARCH-101')['ready'])
        command('take', '--node', 'RESEARCH-101', '--actor', 'worker')
        # No new observation, no disposition: V3 still accepts this payload.
        value = self.fixture.result('RESEARCH-101', {'requirement': 'EVREQ-101-01', 'reuse_run': old})
        command('update', '--node', 'RESEARCH-101', '--actor', 'worker', '--status', 'implemented',
                '--result', str(self.fixture.write('old-reuse.json', value)))
        self.assertTrue(self.cli('--audit-readiness', 'RESEARCH-101')['ready'])
        warning = self.cli('--harness', 'RESEARCH-101', '--explain')['explanation']['failure_context']
        self.assertTrue(warning['requires_disposition_review'])
        self.assertEqual('last_audit', warning['signals'][0]['source'])
        self.assertTrue(any(row['check'] == 'REPORTED-FAILURE' for row in warning['signals']))
        evidence = self.fixture.write('passing-audit.json', {'schema': 'audit-result-v1', 'target': 'RESEARCH-101',
                'result': 'pass', 'affected_claims': ['RESEARCH-101'], 'recommended_action': 'advance'})
        command('audit', '--node', 'RESEARCH-101', '--actor', 'reviewer', '--result', 'pass', '--evidence', str(evidence))
        item = load_project(self.root)[2]['nodes']['RESEARCH-101']
        self.assertEqual('passed', item['verification'])
        self.assertEqual(old, item['last_audit']['proofs'][0]['run']['id'])
        after = self.canonical_bytes()
        for path, data in failed_bytes.items():
            if path.startswith('.pyramid/events/'):
                self.assertEqual(data, after[path])
        # The projection cannot pretend it scans history after last_audit is replaced.
        current = self.cli('--harness', 'RESEARCH-101', '--explain')['explanation']['failure_context']
        self.assertFalse(current['requires_disposition_review'])
        self.assertIn('later audit replaces', current['warning'])
        self.assertEqual('REPORTED-FAILURE', transcript[0]['response']['failed_audit']['checks'][0]['id'])
        if os.environ.get('PYRAMID_TEST_EVIDENCE_DIR'):
            path = Path(os.environ['PYRAMID_TEST_EVIDENCE_DIR']) / 'failed-old-run-cycle.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'old_run': old, 'warning_before_pass': warning,
                                       'after_pass': current, 'transcript': transcript}, indent=2) + '\n')

    def test_many_runs_aggregate_bound_and_page_all_pairs_read_only(self):
        import hashlib
        for nid, count in [('RESEARCH-101', 5), ('CONTRACT-102', 100)]:
            node = self.fixture.node(nid)
            first = copy.deepcopy(node['required_evidence'][0])
            node['required_evidence'] = [{**copy.deepcopy(first), 'id': f'EV-{nid}-{i:03}'} for i in range(count)]
        replan_project(self.root, self.fixture.write('many-plan.json', self.fixture.plan), 'planner', 'Many independent contracts', True)
        from pyramid_core import take_task, update_task
        for nid in ['RESEARCH-101', 'CONTRACT-102']:
            take_task(self.root, 'worker', nid=nid)
            proofs = inspect_project(self.root, harness=nid)['proof_templates']
            for p in proofs:
                p['run']['observations'][0].update(result='passed', summary='Synthetic contract observation, not a physical test',
                    reviewer='unit-fixture', artifacts=[{'path': self.fixture.artifact.relative_to(self.root).as_posix(),
                    'sha256': hashlib.sha256(self.fixture.artifact.read_bytes()).hexdigest()}])
            result = self.fixture.result(nid); result['proofs'] = proofs
            update_task(self.root, nid, 'worker', 'implemented', result_path=self.fixture.write('many-result.json', result))
            self.fixture.audit(nid)
        before = self.canonical_bytes()
        summary = self.cli('--harness', 'RESEARCH-101', '--explain')
        e = summary['explanation']
        self.assertEqual((105, 525, 5, 520), tuple(e[k] for k in ['known_run_count', 'pair_count', 'passed_pair_count', 'rejected_pair_count']))
        self.assertEqual(520, sum(g['count'] for g in e['rejection_groups']))
        self.assertEqual([], e['diagnostics'])
        self.assertLessEqual(len((json.dumps(summary, indent=2) + '\n').encode()), 8192)
        jsonschema.validate(summary, self.schema)
        # The emitted entry is executable; adjacent pages have stable identity and no duplicate pairs.
        pages = []
        for page in [1, 2, e['page']['total_pages']]:
            result = self.cli('--harness', 'RESEARCH-101', '--explain', '--explain-page', str(page), '--full')
            self.assertEqual(e['scan_sha256'], result['explanation']['scan_sha256'])
            self.assertLessEqual(len(result['explanation']['diagnostics']), 10)
            jsonschema.validate(result, self.schema)
            pages += [(d['requirement'], d['run']) for d in result['explanation']['diagnostics']]
        self.assertEqual(len(pages), len(set(pages)))
        entry = e['detail_queries']['pairs']
        followed = subprocess.run([sys.executable, '-B', str(PLUGIN / 'scripts/pyramid.py'), entry['command'],
                                  *entry['arguments']], capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(10, json.loads(followed.stdout)['explanation']['page']['returned'])
        self.cli('--harness', 'RESEARCH-101', '--explain', '--explain-page', '54', code=2)
        self.assertEqual(before, self.canonical_bytes())
        import os
        if os.environ.get('PYRAMID_TEST_EVIDENCE_DIR'):
            path = Path(os.environ['PYRAMID_TEST_EVIDENCE_DIR']) / 'explain-many-runs.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'summary_bytes': len((json.dumps(summary, indent=2) + '\n').encode()),
                                       'summary': summary, 'detail_page_bytes': len(followed.stdout.encode()),
                                       'canonical_changed': False}, indent=2) + '\n')
        (self.root / 'inputs/RESEARCH-101.txt').write_text('changed candidate between pages')
        self.assertNotEqual(e['scan_sha256'], self.cli('--harness', 'RESEARCH-101', '--explain')['explanation']['scan_sha256'])

    def test_long_ready_and_blocked_presentations_preserve_truth_and_loss_counts(self):
        self.fixture.implement('RESEARCH-101')
        full = inspect_project(self.root, audit_readiness='RESEARCH-101')
        self.assertTrue(full['ready'])
        for ready in (True, False):
            with self.subTest(ready=ready):
                data = copy.deepcopy(full)
                data['ready'] = ready
                data['covered_task_ids'] = [f'TASK-{i:04}' for i in range(100)]
                data['blockers'] = [] if ready else [f'Inspection {i}: ' + '边界' * 600 for i in range(52)]
                data['assurance'] = {'status': 'covered' if ready else 'blocked',
                                     'task_ids': data['covered_task_ids'], 'inspection_ids': ['INSPECTION-1'],
                                     'blockers': data['blockers']}
                original = copy.deepcopy(data)
                summary = readiness_summary(data, str(self.root))
                self.assertEqual(ready, summary['ready'])
                self.assertEqual(len(data['blockers']), summary['counts']['blockers'])
                self.assertLessEqual(len((json.dumps(summary, indent=2, ensure_ascii=False) + '\n').encode()), 8192)
                self.assertFalse(summary['details_complete'])
                self.assertEqual(sum(summary['omitted_fields'].values()), summary['omitted_count'])
                self.assertEqual(summary, compact_response(summary, 'inspect'))
                self.assertEqual(original, data)
                jsonschema.validate(summary, self.schema)

    def test_explain_caps_distinct_reasons_and_page_text_with_full_detail_escape(self):
        _, plan, state = load_project(self.root)
        runs = {f'RUN-{i:04}': {'id': f'RUN-{i:04}'} for i in range(12)}
        def rejected(root, plan, spec, run, bindings):
            raise pyramid_verification.VerificationError(run['id'] + ': ' + '长原因' * 1000)
        before = self.canonical_bytes()
        with mock.patch.object(pyramid_verification, 'known_runs', return_value=runs), \
                mock.patch.object(pyramid_verification, 'validate_run', side_effect=rejected) as validator:
            summary = pyramid_verification.query_harness(self.root, plan, state, 'RESEARCH-101', explain=True)
            self.assertEqual(12, validator.call_count)
            partial = pyramid_verification.query_harness(self.root, plan, state, 'RESEARCH-101', explain=True, explain_page=1)
            full = pyramid_verification.query_harness(self.root, plan, state, 'RESEARCH-101', explain=True, explain_page=1, explain_full=True)
        e = summary['explanation']
        self.assertEqual((12, 8, 4), (e['rejection_group_count'], len(e['rejection_groups']), e['omitted_rejection_groups']))
        self.assertLessEqual(len((json.dumps(summary, indent=2, ensure_ascii=False) + '\n').encode()), 8192)
        self.assertEqual(10, partial['explanation']['page']['abbreviated_values'])
        self.assertEqual(0, full['explanation']['page']['abbreviated_values'])
        self.assertGreater(len(full['explanation']['diagnostics'][0]['reason']), 3000)
        self.assertEqual(e['scan_sha256'], partial['explanation']['scan_sha256'])
        for value in [summary, partial, full]:
            jsonschema.validate(value, self.schema)
        self.assertEqual(before, self.canonical_bytes())

    def test_summary_details_recompute_and_default_queries_are_unchanged(self):
        self.fixture.implement('RESEARCH-101')
        full = self.cli('--audit-readiness', 'RESEARCH-101', '--full')
        before = self.canonical_bytes()
        summary = self.cli('--audit-readiness', 'RESEARCH-101', '--readiness-summary')
        self.assertEqual(full['ready'], summary['ready'])
        self.assertEqual(full['context'], summary['details_query']['observed_context'])
        args = summary['details_query']['arguments']
        command = [sys.executable, '-B', str(PLUGIN / 'scripts/pyramid.py'),
                   summary['details_query']['command'], *args]
        detail = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(full, json.loads(detail.stdout))
        self.assertEqual(before, self.canonical_bytes())
        self.assertEqual(full, self.cli('--audit-readiness', 'RESEARCH-101'))
        self.fixture.implement('CONTRACT-102')
        current = self.cli('--audit-readiness', 'RESEARCH-101', '--full')
        self.assertNotEqual(summary['context'], current['context'])

    def test_invalid_cli_combinations_reject_without_mutation(self):
        before = self.canonical_bytes()
        for args in [('--explain',), ('--summary', '--explain'),
                     ('--explain-page', '1'), ('--harness', 'RESEARCH-101', '--explain-page', '1'),
                     ('--harness', 'RESEARCH-101', '--explain', '--explain-page', '0'),
                     ('--readiness-summary',), ('--harness', 'RESEARCH-101', '--readiness-summary'),
                     ('--audit-readiness', 'RESEARCH-101', '--explain'),
                     ('--audit-readiness', 'RESEARCH-101', '--readiness-summary', '--full')]:
            with self.subTest(args=args):
                self.assertIn('error', self.cli(*args, code=2))
        self.assertEqual('pyramid-summary-v1', self.cli('--summary')['schema'])
        self.assertEqual(before, self.canonical_bytes())

    def test_incomplete_computation_is_an_error_not_ready(self):
        with mock.patch.object(pyramid_queries, '_audit_prerequisite_errors',
                               side_effect=PyramidError('required computation unavailable')):
            with self.assertRaisesRegex(PyramidError, 'computation unavailable'):
                inspect_project(self.root, audit_readiness='RESEARCH-101', readiness_summary=True)

    def test_global_stale_count_uses_structured_reasons_not_joined_error_text(self):
        root = Path(self.fixture.temp.name) / 'brownfield'
        assurance = load_json(PLUGIN / 'assets/example-assurance.json')
        assurance['status'] = 'stale'
        assurance['stale_reasons'] = ['First reason; with separators; inside it', 'Second reason']
        create_project(root, PLUGIN / 'assets/example-plan.json', 'planner', mode='brownfield',
                       baseline_path=PLUGIN / 'assets/example-baseline.json',
                       assurance_path=self.fixture.write('stale-bundle.json', assurance))
        full = inspect_project(root, audit_readiness='RESEARCH-101')
        summary = inspect_project(root, audit_readiness='RESEARCH-101', readiness_summary=True)
        self.assertEqual(2, summary['counts']['global_stale_reasons'])
        self.assertEqual(len(full['blockers']), summary['counts']['blockers'])
        self.assertEqual(full['ready'], summary['ready'])
        self.assertFalse(summary['ready'])
        jsonschema.validate(summary, self.schema)

    def test_legacy_plan_remains_unbound_and_empty_scope_is_explicit(self):
        root = Path(self.fixture.temp.name) / 'legacy'
        create_project(root, PLUGIN / 'assets/example-plan.json', 'planner', mode='greenfield')
        before = (root / '.pyramid/state.json').read_bytes()
        explained = inspect_project(root, harness='RESEARCH-101', harness_explain=True)
        self.assertEqual('legacy-unbound', explained['mode'])
        self.assertEqual(0, explained['explanation']['pair_count'])
        self.assertEqual(0, explained['explanation']['passed_pair_count'])
        self.assertEqual(before, (root / '.pyramid/state.json').read_bytes())
        jsonschema.validate(explained, self.schema)
