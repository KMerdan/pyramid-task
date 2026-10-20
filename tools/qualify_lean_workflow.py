#!/usr/bin/env python3
"""Owned disposable S3/A8 experiment, not a second acceptance authority.

Run from a candidate worktree. Supply a read-only pre-3.8 plugin checkout for
the historical recovery control. Results disclose the modeled workflow choices;
they do not estimate real agent time or impersonate an independent reviewer.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/pyramid-task'
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYRAMID_USAGE='off')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def footprint(root):
    groups = {k: {'files': 0, 'logical': 0, 'allocated': 0} for k in
              ['events', 'artifacts', 'canonical-other', 'proof-output', 'external', 'backups']}
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        group = ('events' if '/.pyramid/events/' in '/' + rel else
                 'artifacts' if '/.pyramid/reports/proof-artifacts/' in '/' + rel else
                 'canonical-other' if '/.pyramid/' in '/' + rel else
                 'proof-output' if '/proof-output/' in '/' + rel else 'external')
        stat = p.stat(); g = groups[group]
        g['files'] += 1; g['logical'] += stat.st_size
        g['allocated'] += stat.st_blocks * 512
    return groups


class Commands:
    def __init__(self, plugin, root):
        self.plugin, self.root, self.calls = plugin, root, []

    def __call__(self, *args, code=0):
        command = [sys.executable, '-B', str(self.plugin / 'scripts/pyramid.py'),
                   args[0], '--project', str(self.root), *args[1:], '--json']
        started = time.monotonic()
        p = subprocess.run(command, env=ENV, capture_output=True, text=True, timeout=30)
        self.calls.append({'arguments': list(args), 'exit': p.returncode,
                           'wall_seconds': time.monotonic() - started,
                           'stdout_bytes': len(p.stdout.encode()),
                           'stdout_sha256': sha(p.stdout.encode())})
        if p.returncode != code:
            raise AssertionError((command, p.returncode, p.stdout, p.stderr))
        return json.loads(p.stdout)


def paired(plugin, lean):
    with tempfile.TemporaryDirectory(prefix='pyramid-s3-') as tmp:
        parent = Path(tmp); project = parent / 'project'; project.mkdir()
        plan = json.loads((PLUGIN / 'assets/example-plan.json').read_text())
        plan['schema_version'] = 2
        for node in plan['nodes']:
            node['agent']['evidence_outputs'] = ['proof-output/**']
            node['required_evidence'][0]['verification'] = {
                'criteria': [c['id'] for c in node['acceptance_criteria']],
                'method': 'command', 'procedure': 'Execute probe.py; independently inspect its frozen assertion and output',
                'inputs': ['candidate.txt', 'probe.py'], 'observations': ['internal'],
                'not_applicable': {'external': 'Headless local fixture', 'visual': 'No rendered surface'},
                'environment': 'Owned local subprocess fixture'}
        consumer = next(n for n in plan['nodes'] if n['id'] == 'CONTRACT-102')
        consumer['required_evidence'][0]['verification'] = {
            'criteria': [c['id'] for c in consumer['acceptance_criteria']],
            'reuse': 'RESEARCH-101/EVREQ-101-01'}
        write(parent / 'plan.json', plan)
        (project / 'candidate.txt').write_text('frozen candidate\n')
        probe = "from pathlib import Path\nassert Path('candidate.txt').read_text() == 'frozen candidate\\n'\nprint('frozen assertion passed')\n"
        (project / 'probe.py').write_text(probe)
        before = footprint(parent); cli = Commands(plugin, project)
        cli('create', '--plan', str(parent / 'plan.json'), '--actor', 'experiment', '--mode', 'greenfield')
        counts = {'test_starts': 0, 'environment_starts': 0, 'review_inspections': 0,
                  'trigger_free_reviews': 0, 'label_only_repeats': 0}
        reviews, queries, runs = [], [], []
        source_identity = sha((project / 'candidate.txt').read_bytes() + (project / 'probe.py').read_bytes())
        start = time.monotonic()
        for index, nid in enumerate(['RESEARCH-101', 'CONTRACT-102']):
            cli('take', '--node', nid, '--actor', 'worker')
            harness = cli('inspect', '--harness', nid)
            if lean and index:
                proof = harness['reusable_proofs'][0]
            else:
                template = copy.deepcopy(harness['proof_templates'][0])
                p = subprocess.run([sys.executable, '-B', 'probe.py'], cwd=project,
                                   capture_output=True, env=ENV, timeout=10, check=True)
                counts['test_starts'] += 1
                artifact = project / f'proof-output/run-{index}.txt'; artifact.parent.mkdir(exist_ok=True)
                artifact.write_bytes(p.stdout)
                template['run']['observations'][0].update(
                    result='passed', summary=p.stdout.decode().strip(), reviewer='controlled-subprocess',
                    artifacts=[{'path': artifact.relative_to(project).as_posix(), 'sha256': sha(p.stdout)}])
                proof = template
                counts['review_inspections'] += 1
                # An actual bounded source/output inspection; not an LLM review.
                assert 'assert ' in (project / 'probe.py').read_text() and p.stdout == b'frozen assertion passed\n'
                trigger = 'initial assertion/output coverage' if not index else 'consumer label only'
                reviews.append({'trigger': trigger, 'kind': 'deterministic source/output inspection'})
                if index:
                    counts['label_only_repeats'] += 1; counts['trigger_free_reviews'] += 1
            result = {'schema': 'agent-result-v1', 'task': nid, 'outcome': 'implemented',
                      'changed_files': [], 'checks': [], 'acceptance_evidence': [],
                      'discovered_risks': [], 'suggested_graph_changes': [], 'proofs': [proof]}
            write(parent / 'result.json', result)
            cli('update', '--node', nid, '--actor', 'worker', '--status', 'implemented', '--result', str(parent / 'result.json'))
            readiness = cli('inspect', '--audit-readiness', nid, *(['--readiness-summary'] if lean else []))
            queries.append(len((json.dumps(readiness, indent=2) + '\n').encode()))
            assert readiness['ready']
            audit = {'schema': 'audit-result-v1', 'target': nid, 'result': 'pass',
                     'affected_claims': [nid], 'recommended_action': 'advance'}
            write(parent / 'audit.json', audit)
            cli('audit', '--node', nid, '--actor', 'reviewer', '--result', 'pass', '--evidence', str(parent / 'audit.json'))
            state = json.loads((project / '.pyramid/state.json').read_text())
            runs.append(state['nodes'][nid]['last_audit']['proofs'][0]['run']['id'])
            # Explicit model of lesson's copied auxiliary records, never a CLI requirement.
            if not lean:
                for label in ['README', 'claims-replay', 'carried-review']:
                    write(project / f'proof-output/{label}-{index}.json', {'redundant_copy': readiness})
        auxiliary = [p for p in (project / 'proof-output').glob('*.json')]
        after = footprint(parent)
        delta = {k: {m: after[k][m] - before[k][m] for m in after[k]} for k in after}
        result = {'cli_sha256': sha((plugin / 'scripts/pyramid.py').read_bytes()),
                  'fixture_sha256': source_identity, 'plan_sha256': sha((parent / 'plan.json').read_bytes()),
                  'calls': cli.calls, 'cli_calls': len(cli.calls), 'counts': counts, 'reviews': reviews,
                  'wall_seconds': time.monotonic() - start, 'agent_seconds': None,
                  'summary_bytes': queries, 'producer_run': runs[0], 'consumer_run': runs[1],
                  'shared_run': runs[0] == runs[1], 'auxiliary_logical': sum(p.stat().st_size for p in auxiliary),
                  'material_delta': delta, 'temporary_cleanup': 'TemporaryDirectory removed after measurement'}
        assert sha((project / 'candidate.txt').read_bytes() + (project / 'probe.py').read_bytes()) == source_identity
        return result


RECOVERY = r'''
import json,sys,tempfile
from pathlib import Path
plugin=Path(sys.argv[1]);sys.path.insert(0,str(plugin/'scripts'))
import pyramid_core as core
with tempfile.TemporaryDirectory(prefix='pyramid-a8-') as tmp:
 root=Path(tmp)/'project'
 core.create_project(root,plugin/'assets/example-plan.json','planner')
 core.take_task(root,'worker',nid='RESEARCH-101')
 core.update_task(root,'RESEARCH-101','worker','blocked',reason='Producer requires repair')
 paused=core.pause_task(root,'RESEARCH-101','worker','Transfer blocker investigation',plugin/'assets/example-handoff-draft.json',mode='handoff')
 handoff=Path(paused['handoff']['json']); original=handoff.read_bytes()
 out={'default_errors':[]}
 for action in [lambda:core.resume_task(root,'RESEARCH-101','next-worker'),lambda:core.update_task(root,'RESEARCH-101','worker','clear')]:
  try:action();raise AssertionError('unsafe default allowed')
  except core.PyramidError as e:out['default_errors'].append(str(e))
 out['paused_visible']=bool(core.inspect_project(root,paused=True)['nodes'])
 if sys.argv[2]=='current':
  result=core.resume_task(root,'RESEARCH-101','next-worker',for_recovery=True,handoff_id=paused['handoff']['id'])
  assert result['packet']['owner']=='next-worker' and result['packet']['health']=='blocked'
  assert handoff.read_bytes()==original
  try:core.update_task(root,'RESEARCH-101','worker','clear');raise AssertionError('former owner allowed')
  except core.PyramidError as e:out['wrong_owner_error']=str(e)
  core.update_task(root,'RESEARCH-101','next-worker','clear',reason='Owned repair disposition in this fixture')
  assert core.validate_project(root)['valid'];out['recovered_with_guards']=True
 print(json.dumps(out))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-plugin', type=Path, required=True)
    parser.add_argument('--historical-plugin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'schema': 'lean-workflow-experiment-v1',
              'qualification': 'controlled-feasibility-only',
              'not_established': ['real agent workflow convergence', 'global productivity or net storage savings'],
              'scope': 'Controlled lesson-style policy comparison; repeated test/review/material choices are agent choices, not CLI or old Skill requirements',
              'limits': ['Two tasks, no long history, no service startup/cache model, no real host agent time or independent human/LLM review',
                         'Local filesystem end-of-run bytes before cleanup; temporary peak not sampled; no backups created',
                         'A8 is historical standalone recovery, not ai-gateway billing acceptance'],
              'baseline': paired(args.baseline_plugin.resolve(), False), 'lean': paired(PLUGIN, True)}
    assert report['baseline']['fixture_sha256'] == report['lean']['fixture_sha256']
    assert report['baseline']['plan_sha256'] == report['lean']['plan_sha256']
    a8 = {}
    for label, plugin in [('historical', args.historical_plugin.resolve()), ('current', PLUGIN)]:
        p = subprocess.run([sys.executable, '-B', '-c', RECOVERY, str(plugin), label],
                           capture_output=True, text=True, env=ENV, timeout=30, check=True)
        a8[label] = json.loads(p.stdout)
        a8[label]['core_sha256'] = sha((plugin / 'scripts/pyramid_core.py').read_bytes())
    assert not a8['historical']['paused_visible'] and a8['current']['paused_visible']
    assert 'resolve or clear' in a8['historical']['default_errors'][0]
    assert a8['current']['recovered_with_guards']
    report['A8'] = {'defect': 'Blocked paused task deadlocked and disappeared from paused query',
                    'fixed_by': 'ffeb3fc (3.8.0), parent source supplied explicitly', 'results': a8}
    write(args.output, report)
    print(json.dumps({'status': 'passed', 'report': str(args.output),
                      'starts': [report[k]['counts']['test_starts'] for k in ['baseline', 'lean']]}))


if __name__ == '__main__':
    main()
