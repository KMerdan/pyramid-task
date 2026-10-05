from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jsonschema

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))
import pyramid_core as core
from pyramid_amendment import prepare_amendment
from pyramid_output import compact_response
import pyramid_history
import pyramid_verification as verification


class EfficiencyTests(unittest.TestCase):
    def test_narrow_queries_reuse_validated_bundle_without_full_snapshot(self):
        options = [{'nid': 'RESEARCH-101'}, {'harness': 'RESEARCH-101'},
                   {'ready': True}, {'blocked': True}, {'paused': True},
                   {'pending_audits': True}, {'audit_readiness': 'RESEARCH-101'},
                   {'assurance_summary_view': True}, {'parallel_ready': True}]
        for query in options:
            with self.subTest(query=query), \
                 mock.patch.object(core, 'graph_snapshot', wraps=core.graph_snapshot) as graph, \
                 mock.patch.object(core, 'load_assurance_bundle', wraps=core.load_assurance_bundle) as bundle:
                core.inspect_project(self.root, **query)
                graph.assert_not_called()
                self.assertEqual(1, bundle.call_count)
        with mock.patch.object(core, 'graph_snapshot', wraps=core.graph_snapshot) as graph:
            core.inspect_project(self.root, summary=True)
            self.assertEqual(1, graph.call_count)

    def test_query_reuse_does_not_skip_changed_canonical_validation(self):
        core.inspect_project(self.root, nid='RESEARCH-101')
        paths = core.project_paths(self.root)
        original = paths['project'].read_bytes()
        manifest = core.load_json(paths['project'])
        manifest['format_version'] = 999
        paths['project'].write_text(json.dumps(manifest))
        with self.assertRaises(core.PyramidError):
            core.inspect_project(self.root, nid='RESEARCH-101')
        paths['project'].write_bytes(original)
        state = core.load_json(paths['state'])
        state['graph_version'] += 1
        paths['state'].write_text(json.dumps(state))
        with self.assertRaises(core.PyramidError):
            core.inspect_project(self.root, nid='RESEARCH-101')

    def test_selected_assurance_retains_cross_asset_blockers_and_full_recovery(self):
        baseline = core.load_json(PLUGIN / 'assets/example-baseline.json')
        unrelated = copy.deepcopy(baseline['assets'][0])
        unrelated.update(id='ASSET-OTHER', locators=['unused/**'])
        baseline['assets'].append(unrelated)
        baseline_path = Path(self.temp.name) / 'two-asset-baseline.json'
        baseline_path.write_text(json.dumps(baseline))
        self.brownfield(baseline_path)
        full = core.inspect_project(self.root, assurance_detail=True)
        before = self.snapshot()
        selected = core.inspect_project(self.root, assurance_detail=True,
                                        assurance_task='RESEARCH-101')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(['RESEARCH-101'], selected['selection']['task_ids'])
        self.assertEqual(core.inspect_project(self.root, nid='RESEARCH-101')['assurance'],
                         selected['coverage'])
        self.assertGreater(selected['omitted_record_counts']['baseline.assets'], 0)
        self.assertIn('inspect --assurance-detail', selected['recovery'])
        for inspection in selected['assurance']['inspections']:
            original = next(i for i in full['assurance']['inspections'] if i['id'] == inspection['id'])
            self.assertEqual(original, inspection)
        aid = selected['baseline']['assets'][0]['id']
        scoped_asset = core.inspect_project(self.root, assurance_detail=True, assurance_asset=aid)
        self.assertEqual([aid], [item['id'] for item in scoped_asset['baseline']['assets']])
        self.assertIn('RESEARCH-101', scoped_asset['coverage']['task_ids'])
        iid = selected['assurance']['inspections'][0]['id']
        scoped_inspection = core.inspect_project(self.root, assurance_detail=True, inspection=iid)
        self.assertEqual([iid], [i['id'] for i in scoped_inspection['assurance']['inspections']])
        self.assertIn('RESEARCH-101', scoped_inspection['coverage']['task_ids'])
        # The record view cannot conceal another asset's blocker or material finding.
        paths, plan, _ = core.load_project(self.root)
        baseline = core.load_json(paths['baseline'])
        assurance = core.load_json(paths['assurance'])
        other = next(a['id'] for a in baseline['assets'] if a['id'] != aid)
        assurance['impacts'].append({**assurance['impacts'][0], 'id': 'IMPACT-OTHER',
                                    'asset_id': other, 'task_ids': ['RESEARCH-101']})
        assurance['findings'].append({'id': 'FINDING-OTHER', 'asset_ids': [other],
            'inspection_id': None, 'severity': 'high', 'status': 'open',
            'title': 'View-test material failure', 'evidence': ['owned fixture'],
            'accepted_by': None, 'acceptance_reason': None})
        view = core.scoped_assurance_detail(baseline, assurance, asset_id=aid)
        self.assertIn('FINDING-OTHER', view['coverage']['finding_ids'])
        self.assertTrue(any('FINDING-OTHER' in b for b in view['coverage']['blockers']))
        self.assertEqual(['FINDING-OTHER'], [i['id'] for i in view['assurance']['findings']])

    def test_assurance_selectors_reject_malformed_unknown_and_wrong_modes(self):
        before = self.snapshot()
        for options in ({'assurance_task': 'RESEARCH-101'},
                        {'assurance_detail': True, 'assurance_task': '../RESEARCH-101'},
                        {'assurance_detail': True, 'assurance_task': 'UNKNOWN-001'},
                        {'assurance_detail': True, 'assurance_asset': 'ASSET-UNKNOWN'},
                        {'assurance_detail': True, 'inspection': 'INSPECTION-UNKNOWN'},
                        {'assurance_detail': True, 'assurance_task': 'RESEARCH-101',
                         'inspection': 'INSPECTION-001'}):
            with self.subTest(options=options), self.assertRaises(core.PyramidError):
                core.inspect_project(self.root, **options)
            self.assertEqual(before, self.snapshot())
        self.brownfield()
        for field in ('assurance_asset', 'inspection'):
            with self.assertRaisesRegex(core.PyramidError, 'Unknown'):
                core.inspect_project(self.root, assurance_detail=True, **{field: 'UNKNOWN-001'})

    def bound_identity_fixture(self):
        """Real subprocess artifact; assertions qualify the runtime, not a product."""
        root = Path(self.temp.name) / 'bound'
        plan = core.load_json(PLUGIN / 'assets/example-plan.json')
        plan['schema_version'] = 2
        for node in plan['nodes']:
            node['agent']['evidence_outputs'] = ['proof-output/**']
            for evidence in node['required_evidence']:
                evidence['verification'] = {
                    'criteria': [c['id'] for c in node['acceptance_criteria']],
                    'method': 'command', 'procedure': (
                        'Execute the owned identity fixture with the existing Python interpreter. '
                        'Capture its actual exit status and stdout as a bounded artifact; do not '
                        'replace process execution with a predetermined success value. Compare '
                        'the observed identity to the input and retain the exact input fingerprint. '
                        'The disposable fixture establishes runtime evidence validation, not '
                        'product behavior, visual quality or independent model review.'),
                    'inputs': ['inputs/probe.py'], 'observations': ['internal'],
                    'not_applicable': {'external': 'Runtime fixture has no product interface',
                                       'visual': 'No rendered surface in this procedure'},
                    'environment': 'Owned disposable identity fixture, not product acceptance'}
        path = Path(self.temp.name) / 'bound-plan.json'
        path.write_text(json.dumps(plan))
        core.create_project(root, path, 'fixture-planner', mode='greenfield')
        (root / 'inputs').mkdir()
        (root / 'inputs/probe.py').write_text("print('PASS owned fixture identity')\n")
        core.take_task(root, 'fixture-worker', nid='RESEARCH-101')
        proof = core.inspect_project(root, harness='RESEARCH-101')['proof_templates'][0]
        run = subprocess.run([sys.executable, '-B', 'inputs/probe.py'], cwd=root,
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(0, run.returncode, run.stdout + run.stderr)
        log = root / 'proof-output/probe.log'
        log.parent.mkdir()
        log.write_text(run.stdout + run.stderr)
        proof['run']['observations'][0].update(
            result='passed', summary='Actual subprocess returned PASS owned fixture identity',
            reviewer='executed-fixture; not product/model review',
            artifacts=[{'path': 'proof-output/probe.log',
                        'sha256': hashlib.sha256(log.read_bytes()).hexdigest()}])
        result = {'schema': 'agent-result-v1', 'task': 'RESEARCH-101', 'outcome': 'implemented',
                  'changed_files': [], 'discovered_risks': [], 'suggested_graph_changes': [],
                  'proofs': [proof]}
        result_path = Path(self.temp.name) / 'bound-result.json'
        result_path.write_text(json.dumps(result))
        update = core.update_task(root, 'RESEARCH-101', 'fixture-worker', 'implemented',
                                  result_path=result_path)
        audit_path = Path(self.temp.name) / 'bound-audit.json'
        audit_path.write_text(json.dumps({'schema': 'audit-result-v1', 'target': 'RESEARCH-101',
             'result': 'pass', 'checks': [{'id': 'CHECK-IDENTITY', 'result': 'passed',
                                         'evidence': ['proof-output/probe.log']}],
             'affected_claims': ['RESEARCH-101'], 'recommended_action': 'advance'}))
        core.audit_node(root, 'RESEARCH-101', 'fixture-auditor', 'pass', audit_path)
        return root, update

    def test_harness_hash_reuse_is_local_and_artifact_checks_still_run(self):
        root, update = self.bound_identity_fixture()
        paths, plan, state = core.load_project(root)
        # Two distinct records of the same performed observation; a view fixture
        # only, not a second claimed execution or canonical write.
        second = copy.deepcopy(state['nodes']['RESEARCH-101']['last_result'])
        second['proofs'][0]['run']['id'] = 'RUN-' + '1' * 32
        state['nodes']['RESEARCH-101']['last_audit'] = second
        with mock.patch.object(verification, 'input_snapshot', wraps=verification.input_snapshot) as hashes, \
             mock.patch.object(verification, '_artifact', wraps=verification._artifact) as artifacts:
            query = verification.query_harness(root, plan, state, 'RESEARCH-101')
            self.assertEqual(1, hashes.call_count)
            self.assertEqual(2, artifacts.call_count)
            self.assertEqual(2, len(query['reusable_proofs']))
        (root / 'inputs/probe.py').write_text("print('changed inputs')\n")
        self.assertFalse(verification.query_harness(root, plan, state, 'RESEARCH-101')['reusable_proofs'])
        self.assertFalse(core.inspect_project(root, audit_readiness='RESEARCH-101')['ready'])
        # Restoring input identity does not hide independently changed evidence.
        (root / 'inputs/probe.py').write_text("print('PASS owned fixture identity')\n")
        imported = update['event']['payload']['result']['proofs'][0]['run']['observations'][0]['artifacts'][0]['path']
        (root / imported).write_text('tampered acceptance artifact')
        self.assertFalse(verification.query_harness(root, plan, state, 'RESEARCH-101')['reusable_proofs'])
        with self.assertRaisesRegex(core.PyramidError, 'published head'):
            core.inspect_project(root, audit_readiness='RESEARCH-101')

    def test_compact_inspection_retains_obligations_and_capture_identity(self):
        root, _ = self.bound_identity_fixture()
        full = core.inspect_project(root, nid='RESEARCH-101')
        selected = compact_response(full, 'inspect')
        for key in ('owner', 'mutation_guards', 'dependencies', 'blocked_by', 'acceptance_criteria',
                    'required_evidence', 'allowed_write_scope', 'commands', 'non_goals'):
            self.assertEqual(full[key], selected[key])
        self.assertEqual('summary-only; not a run template', selected['harness']['detail'])
        self.assertIn('--full', selected['harness']['recovery'])
        self.assertIn('procedure', full['harness']['contracts'][0])
        harness = core.inspect_project(root, harness='RESEARCH-101')
        compact = compact_response(harness, 'inspect')
        self.assertEqual(harness['proof_templates'], compact['proof_templates'])
        for index, spec in enumerate(harness['contracts']):
            bounded = compact['contracts'][index]
            for key in ('procedure', 'inputs', 'observations', 'not_applicable', 'criteria'):
                self.assertEqual(spec[key], bounded[key])
            template = compact['proof_templates'][index]['run']
            self.assertEqual(spec['environment'], template['environment'])
            self.assertEqual(spec['contract_sha256'], template['contract_sha256'])

    def test_cli_scoped_assurance_and_rejected_selectors_are_read_only(self):
        self.brownfield()
        before = self.snapshot()
        def cli(*flags):
            return subprocess.run(
                [sys.executable, '-B', str(PLUGIN / 'scripts/pyramid.py'), 'inspect',
                 '--project', str(self.root), '--json', *flags],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, 'PYRAMID_USAGE': 'off'})
        result = cli('--assurance-detail', '--assurance-task', 'RESEARCH-101')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(['RESEARCH-101'], data['selection']['task_ids'])
        self.assertIn('coverage', data)
        for flags in (['--assurance-task', 'RESEARCH-101'],
                      ['--assurance-detail', '--inspection', '../INSPECTION-001'],
                      ['--assurance-detail', '--assurance-asset', 'UNKNOWN-001'],
                      ['--assurance-detail', '--inspection', 'UNKNOWN-001'],
                      ['--assurance-detail', '--assurance-task', 'UNKNOWN-001'],
                      ['--usage', '--assurance-task', 'RESEARCH-101'],
                      ['--assurance-detail', '--assurance-task', 'RESEARCH-101',
                       '--inspection', 'INSPECTION-001']):
            result = cli(*flags)
            self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(before, self.snapshot())

    def test_harness_reuse_does_not_convert_failed_observations_to_pass(self):
        root, _ = self.bound_identity_fixture()
        _, plan, state = core.load_project(root)
        for field in ('last_result', 'last_audit'):
            state['nodes']['RESEARCH-101'][field]['proofs'][0]['run']['observations'][0]['result'] = 'failed'
        # Explicit malformed view data, never written or accepted canonically.
        self.assertFalse(verification.query_harness(root, plan, state, 'RESEARCH-101')['reusable_proofs'])

    def test_event_chain_validation_remains_independent_of_query_reuse(self):
        paths = core.project_paths(self.root)
        self.assertTrue(core.validate_project(self.root)['valid'])
        events = [core.load_json(path) for path in paths['events'].glob('*.json')]
        earliest = min(events, key=lambda event: event['graph_version'])
        path = paths['events'] / (earliest['id'] + '.json')
        earliest['actor'] = 'tampered-old-event'
        path.write_text(json.dumps(earliest))
        validation = core.validate_project(self.root)
        self.assertFalse(validation['valid'])
        self.assertTrue(validation['errors'])

    def test_identical_projection_compile_keeps_bytes_and_mtimes(self):
        paths = core.project_paths(self.root)
        # graph.json carries an actual compilation timestamp, so it is not byte-identical.
        projection_paths = [paths['ready'], *paths['docs'].rglob('*.md')]
        fixed = 1_600_000_000_000_000_000
        before = {}
        for path in projection_paths:
            os.utime(path, ns=(fixed, fixed))
            before[path] = (path.read_bytes(), path.stat().st_mtime_ns)
        core.compile_project(self.root)
        self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns)
                                  for path in projection_paths})
        self.assertEqual(core.load_project(self.root)[2]['graph_version'],
                         core.load_json(paths['graph'])['graph_version'])

    def test_projection_compile_recomputes_and_repairs_changed_content(self):
        paths = core.project_paths(self.root)
        expected = paths['ready'].read_bytes()
        paths['ready'].write_text('{"tampered":true}\n')
        core.compile_project(self.root)
        self.assertEqual(expected, paths['ready'].read_bytes())
        self.assertTrue(core.validate_project(self.root)['valid'])

    def setUp(self):
        usage = mock.patch.dict(os.environ, {'PYRAMID_USAGE': 'off'})
        usage.start()
        self.addCleanup(usage.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        core.create_project(self.root, PLUGIN / "assets/example-plan.json", "planner", mode="greenfield")
        self.file = self.root / "src/executor/connection.py"
        self.file.parent.mkdir(parents=True)
        self.file.write_text("# test source\n")
        self.proposal = {
            "schema": "pyramid-amendment-v1", "task": "RESEARCH-101",
            "reason": "Include an existing connection owner discovered during investigation.",
            "boundary_review": "Existing outcome only; no changed acceptance, dependencies, authority or non-goals.",
            "add_write_paths": ["src/executor/connection.py"], "add_context_paths": [],
        }
        self.path = Path(self.temp.name) / "amendment.json"
        self.save()
        self.taken = core.take_task(self.root, "worker", nid="RESEARCH-101")

    def save(self):
        self.path.write_text(json.dumps(self.proposal))

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in (self.root / ".pyramid").rglob("*") if p.is_file() and p.name != "lock"}

    def apply(self):
        preview = core.amend_task(self.root, self.path, "worker")
        return core.amend_task(self.root, self.path, "worker", True, preview["amendment_id"])

    def test_preview_is_read_only_and_apply_preserves_contract_ownership_and_history(self):
        before = self.snapshot()
        _, old_plan, old_state = core.load_project(self.root)
        preview = core.amend_task(self.root, self.path, "worker")
        self.assertEqual(before, self.snapshot())
        self.assertEqual(preview, core.amend_task(self.root, self.path, "worker"))
        result = core.amend_task(self.root, self.path, "worker", True, preview["amendment_id"])
        _, plan, state = core.load_project(self.root)
        expected = copy.deepcopy(old_plan)
        expected["revision"] += 1
        next(n for n in expected["nodes"] if n["id"] == "RESEARCH-101")["agent"]["allowed_write_scope"].append(str(self.file.relative_to(self.root)))
        self.assertEqual(expected, plan)
        for nid, item in old_state["nodes"].items():
            self.assertEqual({k: v for k, v in item.items() if k != "updated_at"},
                             {k: v for k, v in state["nodes"][nid].items() if k != "updated_at"})
        self.assertEqual(old_state["graph_version"] + 1, state["graph_version"])
        event = core.load_json(self.root / ".pyramid/events" / f"{result['event']['id']}.json")
        self.assertEqual(self.proposal, event["payload"]["amendment"])
        self.assertEqual("task.amended", event["type"])
        self.assertNotEqual(self.taken["packet"]["mutation_guard"], result["mutation_guard"])
        validation = core.validate_project(self.root)
        self.assertTrue(validation["valid"], validation["errors"])
        # New guard continues the same claim; the old guard is now invalid.
        with self.assertRaises(core.PyramidError):
            core.update_task(self.root, "RESEARCH-101", "worker", "clear", expected_guard=self.taken["packet"]["mutation_guard"])
        core.update_task(self.root, "RESEARCH-101", "worker", "clear", expected_guard=result["mutation_guard"])

    def test_rejects_semantic_fields_and_malformed_paths_without_mutating(self):
        original = copy.deepcopy(self.proposal)
        candidates = []
        for field in ("acceptance_criteria", "commands", "edges", "non_goals", "effect"):
            candidates.append({**original, field: []})
        for value in ("../outside.py", "/tmp/out.py", "src/**", "src/../out.py", ".", "src//file.py",
                      ".git/config", ".pyramid/plan.json", "docs/tasks/task.md", "src\\file.py", "missing.py"):
            candidates.append({**original, "add_write_paths": [value]})
        candidates.extend([
            {**original, "add_write_paths": []},
            {**original, "add_write_paths": original["add_write_paths"] * 2},
            {**original, "boundary_review": " "},
            {**original, "task": "MISSING-001"},
        ])
        before = self.snapshot()
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.proposal = candidate
                self.save()
                with self.assertRaises(core.PyramidError):
                    core.amend_task(self.root, self.path, "worker")
                self.assertEqual(before, self.snapshot())

    def test_rejects_symlinks_and_directories(self):
        link = self.root / "alias.py"
        link.symlink_to(self.file)
        for value in ("alias.py", "src/executor"):
            self.proposal["add_write_paths"] = [value]
            self.save()
            with self.assertRaisesRegex(core.PyramidError, "non-symlink"):
                core.amend_task(self.root, self.path, "worker")

    def test_preview_token_binds_state_proposal_and_actor(self):
        preview = core.amend_task(self.root, self.path, "worker")
        before = self.snapshot()
        for token in (None, "AMEND-wrong"):
            with self.assertRaises(core.PyramidError):
                core.amend_task(self.root, self.path, "worker", True, token)
        with self.assertRaises(core.PyramidError):
            core.amend_task(self.root, self.path, "other", True, preview["amendment_id"])
        self.assertEqual(before, self.snapshot())
        self.proposal["reason"] += " Revised."
        self.save()
        with self.assertRaisesRegex(core.PyramidError, "Stale"):
            core.amend_task(self.root, self.path, "worker", True, preview["amendment_id"])
        preview = core.amend_task(self.root, self.path, "worker")
        core.update_task(self.root, "RESEARCH-101", "worker", "at-risk", reason="New evidence")
        with self.assertRaisesRegex(core.PyramidError, "Stale"):
            core.amend_task(self.root, self.path, "worker", True, preview["amendment_id"])

    def test_already_covered_scope_needs_no_amendment(self):
        paths, plan, state = core.load_project(self.root)
        next(n for n in plan["nodes"] if n["id"] == "RESEARCH-101")["agent"]["allowed_write_scope"].append("src/executor/**")
        with mock.patch.object(core, "load_project", return_value=(paths, plan, state)):
            with self.assertRaisesRegex(core.PyramidError, "already permitted"):
                core.amend_task(self.root, self.path, "worker")

    def test_amendment_remains_a_history_turning_point(self):
        result = self.apply()
        _, plan, state = core.load_project(self.root)
        events = pyramid_history._event_records(self.root / ".pyramid/events")
        journey = pyramid_history._journey(plan, state, events)
        self.assertIn(result["event"]["id"], [event["id"] for event in journey["turning_points"]])

    def test_completed_paused_unowned_and_expired_work_cannot_amend(self):
        # Inject states at the read boundary without corrupting a canonical fixture.
        paths, plan, state = core.load_project(self.root)
        for execution in ("paused", "implemented", "planned"):
            candidate = copy.deepcopy(state)
            candidate["nodes"]["RESEARCH-101"]["execution"] = execution
            with mock.patch.object(core, "load_project", return_value=(paths, plan, candidate)):
                with self.assertRaises(core.PyramidError):
                    core.amend_task(self.root, self.path, "worker")
        for status in ("completed", "archived"):
            candidate = copy.deepcopy(state)
            candidate["lifecycle"]["status"] = status
            with mock.patch.object(core, "load_project", return_value=(paths, plan, candidate)):
                with self.assertRaises(core.PyramidError):
                    core.amend_task(self.root, self.path, "worker")
        candidate = copy.deepcopy(state)
        candidate["nodes"]["RESEARCH-101"]["lease_expires_at"] = "2000-01-01T00:00:00Z"
        with mock.patch.object(core, "load_project", return_value=(paths, plan, candidate)):
            with self.assertRaisesRegex(core.PyramidError, "unexpired"):
                core.amend_task(self.root, self.path, "worker")

    def test_active_write_and_generated_output_conflicts_are_rejected(self):
        paths, plan, state = core.load_project(self.root)
        for execution in ("working", "paused"):
            for field in ("allowed_write_scope", "generated_outputs"):
                candidate, candidate_state = copy.deepcopy(plan), copy.deepcopy(state)
                other = next(n for n in candidate["nodes"] if n["id"] == "CONTRACT-102")
                other["agent"]["allowed_write_scope"] = []
                other["agent"][field] = (["src/executor/**"] if field == "allowed_write_scope"
                                          else [{"pattern": "src/executor/**", "asset_ids": []}])
                candidate_state["nodes"]["CONTRACT-102"]["execution"] = execution
                with mock.patch.object(core, "load_project", return_value=(paths, candidate, candidate_state)):
                    with self.assertRaisesRegex(core.PyramidError, "conflicts with active"):
                        core.amend_task(self.root, self.path, "worker")

    def brownfield(self, baseline_path=None):
        root = Path(self.temp.name) / "brownfield"
        core.create_project(root, PLUGIN / "assets/example-plan.json", "planner", mode="brownfield",
                            baseline_path=baseline_path or PLUGIN / "assets/example-baseline.json",
                            assurance_path=PLUGIN / "assets/example-assurance.json")
        target = root / "src/executor/connection.py"
        target.parent.mkdir(parents=True)
        target.write_text("# source\n")
        core.take_task(root, "worker", nid="RESEARCH-101")
        self.root = root

    def test_brownfield_preserves_mapping_but_stales_affected_inspections(self):
        self.brownfield()
        result = self.apply()
        self.assertEqual(["INSPECTION-001"], result["stale_inspections"])
        assurance = core.load_json(self.root / ".pyramid/assurance.json")
        self.assertEqual("stale", assurance["inspections"][0]["status"])
        self.assertTrue(core.validate_project(self.root)["valid"])

    def test_brownfield_rejects_unmapped_asset(self):
        self.brownfield()
        (self.root / "other.py").write_text("# unmapped\n")
        self.proposal["add_write_paths"] = ["other.py"]
        self.save()
        before = self.snapshot()
        with self.assertRaisesRegex(core.PyramidError, "impact mapping"):
            self.apply()
        self.assertEqual(before, self.snapshot())

    def test_context_only_addition_preserves_inspections(self):
        self.brownfield()
        self.proposal["add_context_paths"] = self.proposal["add_write_paths"]
        self.proposal["add_write_paths"] = []
        self.save()
        before = (self.root / ".pyramid/assurance.json").read_bytes()
        self.assertEqual([], self.apply()["stale_inspections"])
        self.assertEqual(before, (self.root / ".pyramid/assurance.json").read_bytes())

    def test_compact_update_retains_safety_and_full_results_stay_on_disk(self):
        full = core.update_task(self.root, "RESEARCH-101", "worker", "blocked", reason="Missing provider credentials")
        original = copy.deepcopy(full)
        compact = compact_response(full, "update")
        self.assertEqual(original, full)
        self.assertLess(len(json.dumps(compact)), 0.8 * len(json.dumps(full)))
        for key in ("blocker", "blocked_by", "health", "execution", "verification", "dependencies", "mutation_guards"):
            self.assertEqual(full["packet"][key], compact["packet"][key])
        self.assertEqual(full["event"]["payload"], compact["event"]["payload"])
        self.assertEqual(full["event"], core.load_json(self.root / compact["event"]["path"]))
        for schema, value in (("agent-status", compact["packet"]), ("event-reference", compact["event"]), ("amendment", self.proposal)):
            jsonschema.validate(value, core.load_json(PLUGIN / "schemas" / f"{schema}.schema.json"))

    def test_compact_take_keeps_entire_task_contract(self):
        self.assertEqual(self.taken["packet"], compact_response(self.taken, "take")["packet"])
        self.assertEqual(self.taken["packet"], compact_response(self.taken, "resume")["packet"])

    def test_compact_is_a_noop_when_projection_would_add_overhead(self):
        preview = core.amend_task(self.root, self.path, "worker")
        self.assertEqual(preview, compact_response(preview, "amend"))
        full = {"event": {"schema": "pyramid-event-v1", "id": "EV-1", "before": {}, "after": {}}}
        self.assertEqual(full, compact_response(full, "create"))

    def test_compact_keeps_full_packet_when_another_mutation_intervenes(self):
        full = core.update_task(self.root, "RESEARCH-101", "worker", "clear")
        path = self.root / "context.txt"
        path.write_text("new required context")
        self.proposal["add_write_paths"] = []
        self.proposal["add_context_paths"] = ["context.txt"]
        self.save()
        self.apply()
        # Reproduce a packet assembled after a concurrent contract change.
        full["packet"] = core.inspect_project(self.root, nid="RESEARCH-101")
        compact = compact_response(full, "update")
        self.assertEqual(full["packet"], compact["packet"])
        self.assertEqual("agent-task-v1", compact["packet"]["schema"])
        self.assertIn("context.txt", compact["packet"]["required_context"])

    def test_malformed_amendment_roots_are_rejected_cleanly(self):
        plan = core.load_project(self.root)[1]
        for proposal in (None, [], "proposal", 123):
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                prepare_amendment(plan, proposal)

    def test_compact_brownfield_keeps_assurance_and_unknown_warnings(self):
        self.brownfield()
        full = core.update_task(self.root, "RESEARCH-101", "worker", "at-risk", reason="Review needed")
        full["warnings"] = ["Unknown future safety field"]
        result = compact_response(full, "update")
        self.assertEqual(full["packet"]["assurance"], result["packet"]["assurance"])
        self.assertEqual(full["warnings"], result["warnings"])

    def test_cli_amend_and_compact_update(self):
        def cli(*args):
            result = subprocess.run([sys.executable, str(PLUGIN / "scripts/pyramid.py"), *args,
                                     "--project", str(self.root), "--json"],
                                    capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            return json.loads(result.stdout)
        preview = cli("amend", "--proposal", str(self.path), "--actor", "worker", "--preview")
        result = cli("amend", "--proposal", str(self.path), "--actor", "worker", "--apply", "--expected-amendment", preview["amendment_id"])
        self.assertEqual("applied", result["status"])
        updated = cli("update", "--node", "RESEARCH-101", "--actor", "worker", "--status", "clear", "--expected-guard", result["mutation_guard"])
        self.assertEqual("agent-status-v1", updated["packet"]["schema"])
        self.assertNotIn("before", updated["event"])
        self.assertEqual("pyramid-event-reference-v1", updated["event"]["schema"])
        full = cli("update", "--node", "RESEARCH-101", "--actor", "worker", "--status", "clear",
                   "--expected-guard", updated["packet"]["mutation_guard"], "--full")
        self.assertEqual("agent-task-v1", full["packet"]["schema"])
        self.assertEqual("pyramid-event-v1", full["event"]["schema"])
        self.assertIn("before", full["event"])
        self.assertNotIn("response_format", full)
        saved = core.load_json(self.root / ".pyramid/events" / f"{full['event']['id']}.json")
        self.assertEqual(saved, full["event"])
        explicit = cli("update", "--node", "RESEARCH-101", "--actor", "worker", "--status", "clear",
                       "--expected-guard", full["packet"]["mutation_guard"], "--compact")
        self.assertEqual("agent-status-v1", explicit["packet"]["schema"])
        packet = cli("inspect", "--node", "RESEARCH-101")
        self.assertEqual("agent-task-v1", packet["schema"])
        self.assertIn("acceptance_criteria", packet)

    def test_cli_conflicting_output_flags_do_not_mutate(self):
        before = self.snapshot()
        result = subprocess.run([sys.executable, str(PLUGIN / "scripts/pyramid.py"),
                                 "update", "--project", str(self.root), "--node", "RESEARCH-101",
                                 "--actor", "worker", "--status", "clear", "--json", "--compact", "--full"],
                                capture_output=True, text=True,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(2, result.returncode)
        self.assertIn("not allowed", result.stderr)
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
