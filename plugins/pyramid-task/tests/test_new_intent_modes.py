"""Native lifecycle mode changes retain history and enforce new assurance."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest import mock

import jsonschema

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'scripts'))
import pyramid_core as core
import pyramid_plan_lifecycle as lifecycle
import test_runtime as fixtures


class NewIntentModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patch = mock.patch.dict(os.environ, PYRAMID_USAGE='off')
        patch.start()
        self.addCleanup(patch.stop)
        self.root = Path(self.temp.name) / 'project'
        self.helper = fixtures.PyramidRuntimeTests('runTest')
        self.helper.temp = self.temp
        self.helper.root = self.root
        self.helper.example = PLUGIN / 'assets/example-plan.json'
        core.create_project(self.root, self.helper.example, 'planner', mode='greenfield')
        self.helper.complete_graph()
        core.close_project(self.root, 'owner')
        self.candidate = core.load_json(self.helper.example)
        self.candidate['plan_id'] = 'PLAN-NEXT-MODE'
        self.plan = self.write('next.json', self.candidate)

    def write(self, name, value):
        path = Path(self.temp.name) / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def bytes(self, root=None):
        root = root or self.root / '.pyramid'
        return {p.relative_to(root).as_posix(): p.read_bytes()
                for p in root.rglob('*') if p.is_file()}

    def preview(self, mode='brownfield'):
        return core.new_intent_project(self.root, self.plan, 'planner', 'Next change', mode=mode)

    def apply(self, preview, mode='brownfield'):
        return core.new_intent_project(
            self.root, self.plan, 'planner', 'Next change', mode=mode, apply=True,
            approved_by='test-owner', approval_reference='owned-fixture',
            approved_new_intent_sha256=preview['new_intent_sha256'],
            expected_version={'graph_version': preview['current']['graph_version'],
                              'context_id': preview['current']['context']['id']})

    def test_explicit_brownfield_preview_and_apply_preserve_old_authority(self):
        before = self.bytes()
        preview = self.preview()
        self.assertEqual('brownfield', preview['mode'])
        self.assertEqual({'from': 'greenfield', 'to': 'brownfield'}, preview['mode_transition'])
        self.assertEqual(before, self.bytes(), 'Preview must preserve canonical bytes')
        jsonschema.validate(preview, core.load_json(PLUGIN / 'schemas/new-intent-preview.schema.json'))
        result = self.apply(preview)
        self.assertEqual(preview['mode'], result['mode'])
        self.assertEqual(preview['new_intent_sha256'], result['new_intent_sha256'])
        manifest = core.load_json(self.root / '.pyramid/project.json')
        self.assertEqual('brownfield', manifest['mode'])
        baseline = core.load_json(self.root / '.pyramid/baseline.json')
        assurance = core.load_json(self.root / '.pyramid/assurance.json')
        self.assertEqual('incomplete', baseline['status'])
        self.assertEqual('incomplete', assurance['status'])
        self.assertEqual(self.candidate['plan_id'], assurance['plan_id'])
        self.assertEqual('brownfield', assurance['policy'])
        archived = Path(core.list_archives(self.root)[-1]['path']) / '.pyramid'
        self.assertEqual(before['project.json'], (archived / 'project.json').read_bytes())
        self.assertEqual('greenfield', json.loads((archived / 'project.json').read_text())['mode'])
        self.assertEqual(before['plan.json'], (archived / 'plan.json').read_bytes())
        for rel, data in before.items():
            if rel.startswith(('events/', 'reports/', 'history/records/')):
                self.assertEqual(data, (archived / rel).read_bytes(), rel)
            if rel.startswith('history/records/'):
                self.assertEqual(data, (self.root / '.pyramid' / rel).read_bytes(), rel)
        event = result['reset']['event']
        self.assertEqual(preview['mode_transition'], event['payload']['transition_approval']['mode_transition'])
        self.assertEqual('brownfield', event['payload']['mode'])
        self.assertTrue(core.validate_project(self.root)['valid'])
        self.assertTrue(core.validate_project(archived.parent)['valid'])
        self.assertEqual('valid', core.inspect_history_health(self.root)['status'])

    def test_reusing_an_existing_archive_keeps_every_archive_byte(self):
        archived = core.archive_project(self.root, 'owner', 'Owned archive')
        archive_root = Path(archived['archive'])
        before = self.bytes(archive_root)
        preview = self.preview()
        self.apply(preview)
        self.assertEqual(before, self.bytes(archive_root))

    def test_mode_and_candidate_changes_refuse_stale_approval_without_writes(self):
        auto = self.preview('auto')
        brown = self.preview()
        self.assertNotEqual(auto['new_intent_sha256'], brown['new_intent_sha256'])
        before = self.bytes()
        for approved, requested in [(auto, 'brownfield'), (brown, 'auto')]:
            with self.assertRaisesRegex(core.PyramidError, 'hash does not match'):
                self.apply(approved, requested)
            self.assertEqual(before, self.bytes())
        candidate = copy.deepcopy(self.candidate)
        candidate['title'] = 'Changed after approval'
        self.write('next.json', candidate)
        with self.assertRaisesRegex(core.PyramidError, 'hash does not match'):
            self.apply(brown)
        self.assertEqual(before, self.bytes())

    def test_auto_still_inherits_existing_greenfield_mode(self):
        # Existing source files do not turn an existing manifest brownfield in auto mode.
        (self.root / 'existing-source.py').write_text('value = 1\n')
        preview = self.preview('auto')
        self.assertEqual('greenfield', preview['mode'])
        self.assertNotIn('mode_transition', preview)
        self.apply(preview, 'auto')
        self.assertEqual('greenfield', core.load_json(self.root / '.pyramid/project.json')['mode'])
        self.assertFalse((self.root / '.pyramid/baseline.json').exists())
        self.assertFalse((self.root / '.pyramid/assurance.json').exists())

    def test_brownfield_downgrade_is_refused_before_preview_or_apply_writes(self):
        self.apply(self.preview())
        core.archive_project(self.root, 'owner', 'Owned brownfield archive')
        candidate = copy.deepcopy(self.candidate)
        candidate['plan_id'] = 'PLAN-THIRD-MODE'
        self.write('next.json', candidate)
        before = self.bytes()
        for apply in [False, True]:
            with self.assertRaisesRegex(core.PyramidError, 'brownfield.*greenfield'):
                core.new_intent_project(self.root, self.plan, 'planner', 'No downgrade',
                                        mode='greenfield', apply=apply)
            self.assertEqual(before, self.bytes())

    def test_direct_reset_cannot_convert_mode_without_bound_transition(self):
        before = self.bytes()
        with self.assertRaisesRegex(core.PyramidError, 'new-intent'):
            lifecycle.reset_project(self.root, self.plan, 'planner', 'No unapproved conversion', mode='brownfield')
        self.assertEqual(before, self.bytes())

    def test_auto_retains_brownfield_baseline_and_replaces_only_current_assurance(self):
        self.apply(self.preview())
        core.assess_project(self.root, PLUGIN / 'assets/example-baseline.json', 'assessor', apply=True)
        baseline = (self.root / '.pyramid/baseline.json').read_bytes()
        assurance = (self.root / '.pyramid/assurance.json').read_bytes()
        core.archive_project(self.root, 'owner', 'Owned archive before next cycle')
        candidate = copy.deepcopy(self.candidate)
        candidate['plan_id'] = 'PLAN-THIRD-BROWNFIELD'
        self.write('next.json', candidate)
        preview = self.preview('auto')
        self.assertEqual('brownfield', preview['mode'])
        self.assertNotIn('mode_transition', preview)
        result = self.apply(preview, 'auto')
        self.assertEqual(baseline, (self.root / '.pyramid/baseline.json').read_bytes())
        current = core.load_json(self.root / '.pyramid/assurance.json')
        self.assertEqual('incomplete', current['status'])
        self.assertEqual(candidate['plan_id'], current['plan_id'])
        archive = next(item for item in core.list_archives(self.root)
                       if item['archive_id'] == result['previous_archive'])
        self.assertEqual(assurance, (Path(archive['path']) / '.pyramid/assurance.json').read_bytes())
        before = self.bytes()
        with self.assertRaisesRegex(core.PyramidError, 'brownfield.*greenfield'):
            lifecycle.reset_project(self.root, self.plan, 'planner', 'No downgrade', mode='greenfield')
        self.assertEqual(before, self.bytes())

    def test_internal_reset_revalidates_bound_mode_approval_before_archiving(self):
        preview = self.preview()
        approval = {'approved_by': 'test-owner', 'reference': 'owned-fixture',
                    'new_intent_sha256': '0' * 64, 'mode_transition': preview['mode_transition']}
        before = self.bytes()
        with self.assertRaisesRegex(core.PyramidError, 'does not match'):
            lifecycle.reset_project(self.root, self.plan, 'planner', 'Next change',
                                    mode='brownfield', transition_approval=approval)
        self.assertEqual(before, self.bytes())

    def test_real_cli_promotes_schema2_successor_with_the_exact_preview(self):
        candidate = core.load_json(PLUGIN / 'assets/example-harness-plan.json')
        candidate['plan_id'] = 'PLAN-NEXT-SCHEMA2'
        self.write('next.json', candidate)
        command = [sys.executable, '-B', str(PLUGIN / 'scripts/pyramid.py')]
        transition = ['new-intent', '--project', str(self.root), '--plan', str(self.plan),
                      '--actor', 'planner', '--reason', 'Owned CLI transition', '--mode', 'brownfield']
        def run(args):
            p = subprocess.run(command + args + ['--json'], cwd=self.temp.name,
                               text=True, capture_output=True, timeout=20)
            self.assertEqual(0, p.returncode, p.stderr + p.stdout)
            return json.loads(p.stdout)
        preview = run(transition + ['--preview'])
        self.assertEqual('brownfield', preview['mode'])
        result = run(transition + ['--apply', '--approved-by', 'test-owner',
                     '--approval-reference', 'owned-cli-fixture',
                     '--approved-new-intent-sha256', preview['new_intent_sha256'],
                     '--expected-version', str(preview['current']['graph_version']),
                     '--expected-context', preview['current']['context']['id']])
        self.assertEqual(preview['mode'], result['mode'])
        self.assertEqual(preview['new_intent_sha256'], result['new_intent_sha256'])
        self.assertEqual(2, core.load_project(self.root)[1]['schema_version'])
        self.assertTrue(run(['validate', '--project', str(self.root)])['valid'])
        self.assertEqual('brownfield', core.load_json(self.root / '.pyramid/project.json')['mode'])

    def test_promoted_project_uses_normal_assessment_and_impact_enforcement(self):
        self.apply(self.preview())
        core.take_task(self.root, 'worker', nid='RESEARCH-101')
        result = core.load_json(self.helper.result_for('RESEARCH-101', ['AC-101-01']))
        result['changed_files'] = []  # Synthetic research fixture; no product execution claim.
        core.update_task(self.root, 'RESEARCH-101', 'worker', 'implemented',
                         result_path=self.write('result.json', result))
        with self.assertRaisesRegex(core.PyramidError, 'assurance|baseline|Baseline'):
            core.audit_node(self.root, 'RESEARCH-101', 'auditor', 'pass', self.helper.audit_for('RESEARCH-101'))
        baseline = core.load_json(PLUGIN / 'assets/example-baseline.json')
        path = self.write('baseline.json', baseline)
        core.assess_project(self.root, path, 'assessor', apply=True)
        self.assertEqual('current', core.load_json(self.root / '.pyramid/baseline.json')['status'])
        with self.assertRaisesRegex(core.PyramidError, 'assurance|inspection|impact'):
            core.audit_node(self.root, 'RESEARCH-101', 'auditor', 'pass', self.helper.assurance_audit_for('RESEARCH-101'))
        assurance = core.load_json(PLUGIN / 'assets/example-assurance.json')
        assurance['plan_id'] = self.candidate['plan_id']
        assurance['inspections'][0]['performed_at'] = core.utc_now()
        core.impact_project(self.root, self.write('assurance.json', assurance), 'assessor', apply=True)
        core.audit_node(self.root, 'RESEARCH-101', 'auditor', 'pass', self.helper.assurance_audit_for('RESEARCH-101'))
        self.assertEqual('passed', core.load_project(self.root)[2]['nodes']['RESEARCH-101']['verification'])
        self.assertTrue(core.validate_project(self.root)['valid'])


if __name__ == '__main__':
    unittest.main()
