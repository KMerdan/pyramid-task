"""Reproducible runtime/display cases; fixture evidence is not product acceptance.

Writes only the explicitly selected output directory. Run with the shared Python
environment and --plugin pointing to the installed controller or frozen candidate.
Never point --output at a live project, canonical state or a personal directory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--completed-archive', type=Path, required=True)
    args = parser.parse_args()
    plugin, output = args.plugin.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit('Choose a fresh, exact development-owned output directory')
    output.mkdir(parents=True)
    os.environ['PYRAMID_USAGE'] = 'off'
    sys.path.insert(0, str(plugin / 'scripts'))
    import pyramid_core as core
    import pyramid_visualizer as visual

    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + '\n')
        return path

    base = core.load_json(plugin / 'assets/example-plan.json')
    base['schema_version'] = 2
    for node in base['nodes']:
        node['agent']['evidence_outputs'] = ['proof-output/**']
        for ev in node['required_evidence']:
            ev['verification'] = {
                'criteria': [c['id'] for c in node['acceptance_criteria']],
                'method': 'command',
                'procedure': 'Run the owned identity probe; this establishes only fixture identity.',
                'inputs': [f"inputs/{node['id']}.txt", 'inputs/probe.py'],
                'observations': ['internal'],
                'not_applicable': {'external': 'No product external interface in this fixture',
                                   'visual': 'No rendered claim in this identity probe'},
                'environment': 'Owned disposable runtime/Observer fixture, not product acceptance',
            }

    def create(name, plan=None):
        root = output / 'fixtures' / name
        plan = copy.deepcopy(plan or base)
        plan['plan_id'] = 'MEASURE-' + name.upper()
        core.create_project(root, save(output / f'{name}-plan.json', plan),
                            'fixture-planner', mode='greenfield')
        (root / 'inputs').mkdir()
        for node in plan['nodes']:
            (root / 'inputs' / f"{node['id']}.txt").write_text(node['id'])
        (root / 'inputs/probe.py').write_text(
            "from pathlib import Path\n"
            "ok = Path('inputs/RESEARCH-101.txt').read_text() == 'RESEARCH-101'\n"
            "print('PASS fixture identity' if ok else 'FAIL fixture identity')\n"
            "raise SystemExit(0 if ok else 1)\n")
        return root

    working = create('working')
    core.take_task(working, 'fixture-worker', nid='RESEARCH-101')
    blocked = create('blocked')
    core.take_task(blocked, 'fixture-worker', nid='RESEARCH-101')
    core.update_task(blocked, 'RESEARCH-101', 'fixture-worker', 'blocked',
                     reason='Owned test fixture lacks required capability; not a host approval request')

    visual_plan = copy.deepcopy(base)
    spec = next(n for n in visual_plan['nodes'] if n['id'] == 'TASK-201')['required_evidence'][0]['verification']
    spec['method'] = 'browser'
    spec['observations'].append('visual')
    del spec['not_applicable']['visual']
    spec['procedure'] = 'Capture and actually inspect the owned fixture; no capture is supplied in this negative case.'
    missing = create('missing-visual', visual_plan)

    stale = create('stale-proof')
    core.take_task(stale, 'fixture-worker', nid='RESEARCH-101')
    proof = core.inspect_project(stale, harness='RESEARCH-101')['proof_templates'][0]
    result = subprocess.run([sys.executable, '-B', 'inputs/probe.py'], cwd=stale,
                            capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
    log = stale / 'proof-output/identity.txt'
    log.parent.mkdir()
    log.write_text(result.stdout + result.stderr)
    for observation in proof['run']['observations']:
        observation.update(result='passed', summary='Real subprocess returned PASS fixture identity',
                           reviewer='executed-identity-probe', artifacts=[{
                               'path': 'proof-output/identity.txt',
                               'sha256': hashlib.sha256(log.read_bytes()).hexdigest()}])
    core.update_task(stale, 'RESEARCH-101', 'fixture-worker', 'implemented',
                     result_path=save(output / 'identity-result.json', {
                         'schema': 'agent-result-v1', 'task': 'RESEARCH-101', 'outcome': 'implemented',
                         'changed_files': [], 'checks': [], 'acceptance_evidence': [],
                         'discovered_risks': [], 'suggested_graph_changes': [], 'proofs': [proof]}))
    core.audit_node(stale, 'RESEARCH-101', 'fixture-auditor', 'pass',
                    save(output / 'identity-audit.json', {'schema': 'audit-result-v1',
                         'target': 'RESEARCH-101', 'result': 'pass',
                         'affected_claims': ['RESEARCH-101'], 'recommended_action': 'advance'}))
    (stale / 'inputs/RESEARCH-101.txt').write_text('changed after actual acceptance')

    branched_plan = copy.deepcopy(base)
    mapping = {'OUTCOME-010': 'OUTCOME-020', 'TASK-201': 'TASK-202', 'GATE-290': 'GATE-291'}
    for nid in mapping:
        node = copy.deepcopy(next(n for n in base['nodes'] if n['id'] == nid))
        node['id'] = mapping[nid]
        remap = {c['id']: c['id'] + '-BRANCH' for c in node['acceptance_criteria']}
        for criterion in node['acceptance_criteria']:
            criterion['id'] = remap[criterion['id']]
        for ev in node['required_evidence']:
            ev['verification']['criteria'] = [remap[c] for c in ev['verification']['criteria']]
        if node['kind'] == 'implementation':
            node['required_evidence'][0]['verification']['inputs'][0] = 'inputs/TASK-202.txt'
        branched_plan['nodes'].append(node)
    for edge in base['edges']:
        if edge['from'] in mapping:
            branched_plan['edges'].append({**edge, 'from': mapping[edge['from']],
                                          'to': mapping.get(edge['to'], edge['to'])})
    joint = copy.deepcopy(next(n for n in base['nodes'] if n['id'] == 'GATE-290'))
    joint.update(id='GATE-299', title='Independent branches compose', level=1, wave=4)
    remap = {c['id']: c['id'] + '-JOINT' for c in joint['acceptance_criteria']}
    for criterion in joint['acceptance_criteria']:
        criterion['id'] = remap[criterion['id']]
    for ev in joint['required_evidence']:
        ev['verification']['criteria'] = [remap[c] for c in ev['verification']['criteria']]
    joint['required_evidence'][0]['verification']['inputs'][0] = 'inputs/GATE-299.txt'
    branched_plan['nodes'].append(joint)
    next(n for n in branched_plan['nodes'] if n['id'] == 'INTENT-001')['wave'] = 5
    branched_plan['edges'].extend([
        {'from': 'INTENT-001', 'to': 'GATE-299', 'type': 'validated-by'},
        {'from': 'GATE-299', 'to': 'INTENT-001', 'type': 'contributes-to'},
        {'from': 'GATE-299', 'to': 'OUTCOME-010', 'type': 'integration-requires'},
        {'from': 'GATE-299', 'to': 'OUTCOME-020', 'type': 'integration-requires'},
    ])
    branched = create('branched', branched_plan)

    cases = {'completed': args.completed_archive.resolve(), 'working': working,
             'blocked': blocked, 'missing-visual': missing, 'stale-proof': stale,
             'branched': branched}
    measurements = []
    for name, root in cases.items():
        paths, plan, state = core.load_project(root)
        manifest, baseline, assurance = core.load_assurance_bundle(paths, plan)
        graph = core.graph_snapshot(plan, state, baseline, assurance, manifest,
                                    core.implementation_frontier(paths))
        snapshot = visual.visualization_snapshot(graph)
        save(output / 'snapshots' / f'{name}.json', snapshot)
        (output / 'snapshots' / f'{name}.html').write_text(visual.build_visualization_html(snapshot))
        selected = 'TASK-411' if name == 'completed' else ('TASK-201' if name == 'missing-visual' else 'RESEARCH-101')
        queries = {'node': ['--node', selected], 'harness': ['--harness', selected],
                   'readiness': ['--audit-readiness', selected], 'ready': ['--ready'],
                   'summary': ['--summary'], 'assurance-detail': ['--assurance-detail']}
        for query, flags in queries.items():
            durations, sizes = [], []
            for iteration in range(3):
                started = time.perf_counter()
                completed = subprocess.run([sys.executable, '-B', str(plugin / 'scripts/pyramid.py'),
                                            'inspect', '--project', str(root), *flags, '--json'],
                                           capture_output=True, timeout=30)
                durations.append(time.perf_counter() - started)
                sizes.append(len(completed.stdout))
                if completed.returncode:
                    raise SystemExit(completed.stdout.decode() + completed.stderr.decode())
                if iteration == 0:
                    (output / 'snapshots' / f'{name}-{query}.json').write_bytes(completed.stdout)
            measurements.append({'case': name, 'query': query, 'stdout_bytes': sizes,
                                 'median_cli_seconds': statistics.median(durations)})
    save(output / 'measurements.json', {'plugin': str(plugin), 'runtime_version': core.RUNTIME_VERSION,
         'case_scope': 'Real runtime/CLI fixtures and recorded closed-plan display; not product, native model or human comprehension',
         'native_tokens': None, 'human_comprehension': None, 'measurements': measurements})
    print(json.dumps({'ok': True, 'output': str(output), 'cases': list(cases),
                      'cli_calls': len(measurements) * 3, 'runtime_version': core.RUNTIME_VERSION}))


if __name__ == '__main__':
    main()
