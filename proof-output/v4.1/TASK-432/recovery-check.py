"""Owned real 4.0 -> 4.1 binding -> matching-snapshot recovery, not live downgrade."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

staging = Path('/tmp/pyramid41-hosts.7vw6LI')
old = staging / 'baseline/scripts/pyramid.py'
new = staging / 'claude-candidate-final/package/scripts/pyramid.py'
env = dict(os.environ, PYRAMID_USAGE='off', PYTHONDONTWRITEBYTECODE='1')
records = []
file_actions = []

with tempfile.TemporaryDirectory(prefix='pyramid41-recovery-') as temp:
    scratch = Path(temp)
    root = scratch / 'project'
    root.mkdir()
    (root / 'inputs').mkdir()
    (root / 'proof-output').mkdir()
    probe = root / 'inputs/probe.py'
    probe.write_text("from pathlib import Path\n"
                     "ok = Path('inputs/producer.txt').read_text() == 'producer'\n"
                     "print('PASS producer' if ok else 'FAIL producer')\n"
                     "raise SystemExit(0 if ok else 1)\n")
    (root / 'inputs/producer.txt').write_text('producer')
    plan = json.loads((staging / 'baseline/assets/example-plan.json').read_text())
    plan['schema_version'] = 2
    for node in plan['nodes']:
        node['agent']['evidence_outputs'] = ['proof-output/**']
        for evidence in node['required_evidence']:
            evidence['verification'] = {
                'criteria': [c['id'] for c in node['acceptance_criteria']],
                'method': 'command', 'procedure': 'python -B inputs/probe.py',
                'inputs': ['inputs/probe.py', 'inputs/producer.txt'],
                'observations': ['internal'],
                'not_applicable': {'external': 'This fixture probes local file behavior.',
                                   'visual': 'No rendered interface.'},
                'environment': 'Owned disposable process/file fixture.'}
    # Only RESEARCH-101 is executed and accepted; other nodes remain unverified.
    def save(name, payload):
        path = scratch / name
        path.write_text(json.dumps(payload))
        return str(path)

    def cli(runtime, *args, expected_code=0):
        done = subprocess.run([sys.executable, '-B', str(runtime), *args,
                               '--project', str(root), '--json'],
                              env=env, capture_output=True, text=True, timeout=30)
        assert done.returncode == expected_code, done.stdout + done.stderr
        data = json.loads(done.stdout)
        records.append({'runtime': '4.0.0' if runtime == old else '4.1.0-candidate',
                        'operation': args[0], 'exit_code': done.returncode,
                        'args': list(args), 'stdout': done.stdout, 'stderr': done.stderr,
                        'status': data.get('status'), 'ready': data.get('ready'),
                        'blockers': data.get('blockers', [])})
        return data

    cli(old, 'create', '--plan', save('plan.json', plan), '--actor', 'recovery-check',
        '--mode', 'greenfield')
    claim = cli(old, 'take', '--node', 'RESEARCH-101', '--actor', 'recovery-check')
    proof = cli(old, 'inspect', '--harness', 'RESEARCH-101')['proof_templates'][0]
    observed = subprocess.run([sys.executable, '-B', 'inputs/probe.py'], cwd=root,
                              env=env, capture_output=True, text=True, timeout=10)
    assert observed.returncode == 0 and observed.stdout == 'PASS producer\n'
    artifact = root / 'proof-output/probe.txt'
    artifact.write_text(observed.stdout)
    for observation in proof['run']['observations']:
        observation.update(result='passed', summary=observed.stdout.strip(),
                           reviewer='real-owned-subprocess', artifacts=[{
                               'path': 'proof-output/probe.txt',
                               'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}])
    result = {'schema': 'agent-result-v1', 'task': 'RESEARCH-101', 'outcome': 'implemented',
              'changed_files': [], 'discovered_risks': [], 'suggested_graph_changes': [],
              'proofs': [proof]}
    cli(old, 'update', '--node', 'RESEARCH-101', '--actor', 'recovery-check',
        '--status', 'implemented', '--expected-guard', claim['packet']['mutation_guard'],
        '--result', save('result.json', result))
    cli(old, 'audit', '--node', 'RESEARCH-101', '--actor', 'recovery-review',
        '--result', 'pass', '--evidence', save('audit.json', {
            'schema': 'audit-result-v1', 'target': 'RESEARCH-101', 'result': 'pass',
            'affected_claims': ['RESEARCH-101'], 'recommended_action': 'advance'}))
    original = json.loads((root / '.pyramid/state.json').read_text())['nodes']['RESEARCH-101']
    archive = cli(new, 'archive', '--actor', 'recovery-check', '--reason',
                  'Owned matching pre-change recovery snapshot')
    archive_id = archive.get('archive_id') or archive['archive']['id']
    snapshot_root = root / '.pyramid/archives' / archive_id
    snapshot_hashes = {str(p.relative_to(snapshot_root)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in snapshot_root.rglob('*') if p.is_file()}
    cli(new, 'restore', '--archive', archive_id, '--actor', 'recovery-check',
        '--reason', 'Continue owned fixture from retained pre-change snapshot')
    candidate = json.loads((root / '.pyramid/plan.json').read_text())
    consumer = copy.deepcopy(next(n for n in candidate['nodes'] if n['id'] == 'TASK-201'))
    consumer.update(id='TASK-202', title='New consumer')
    consumer['acceptance_criteria'] = [{'id': 'AC-202-01', 'description': 'Consumer checked separately.'}]
    consumer['required_evidence'] = [{'id': 'EVREQ-202-01', 'type': 'test',
        'description': 'Reuse provider observation; consumer acceptance remains separate.',
        'verification': {'criteria': ['AC-202-01'], 'reuse': 'RESEARCH-101/EVREQ-101-01'}}]
    candidate['nodes'].append(consumer)
    candidate['edges'].extend([
        {'from': 'TASK-202', 'to': 'RESEARCH-101', 'type': 'requires'},
        {'from': 'TASK-202', 'to': 'OUTCOME-010', 'type': 'contributes-to'},
        {'from': 'GATE-290', 'to': 'TASK-202', 'type': 'integration-requires'}])
    path = save('candidate.json', candidate)
    preview = cli(new, 'replan', '--actor', 'recovery-check', '--reason', 'Owned consumer growth',
                  '--plan', path, '--preview')
    cli(new, 'replan', '--actor', 'recovery-check', '--reason', 'Owned consumer growth',
        '--plan', path, '--apply', '--expected-version', str(preview['graph_version']),
        '--expected-context', preview['context']['id'])
    state = json.loads((root / '.pyramid/state.json').read_text())
    assert state['proof_contract_bindings']
    assert cli(new, 'inspect', '--audit-readiness', 'RESEARCH-101')['ready']
    assert not cli(old, 'inspect', '--audit-readiness', 'RESEARCH-101')['ready']
    live_old_validation = cli(old, 'validate')
    input_path = root / 'inputs/producer.txt'
    input_before = hashlib.sha256(input_path.read_bytes()).hexdigest()
    input_path.write_text('changed')
    file_actions.append({'action':'change-producer-input','path':'inputs/producer.txt',
        'before':input_before,'after':hashlib.sha256(input_path.read_bytes()).hexdigest()})
    stale_readiness = cli(new, 'inspect', '--audit-readiness', 'RESEARCH-101')
    assert not stale_readiness['ready']
    state_before_rejection = (root / '.pyramid/state.json').read_bytes()
    rejected = cli(new, 'audit', '--node', 'RESEARCH-101', '--actor', 'recovery-review',
        '--result', 'pass', '--evidence', save('stale-audit.json', {
            'schema': 'audit-result-v1', 'target': 'RESEARCH-101', 'result': 'pass',
            'affected_claims': ['RESEARCH-101'], 'recommended_action': 'advance'}),
        '--expected-guard', stale_readiness['audit_guard'], expected_code=2)
    assert (root / '.pyramid/state.json').read_bytes() == state_before_rejection
    refusal_state_hashes = {'before':hashlib.sha256(state_before_rejection).hexdigest(),
        'after':hashlib.sha256((root / '.pyramid/state.json').read_bytes()).hexdigest()}
    input_changed = hashlib.sha256(input_path.read_bytes()).hexdigest()
    input_path.write_text('producer')
    file_actions.append({'action':'restore-producer-input','path':'inputs/producer.txt',
        'before':input_changed,'after':hashlib.sha256(input_path.read_bytes()).hexdigest()})
    assert cli(new, 'inspect', '--audit-readiness', 'RESEARCH-101')['ready']
    cli(new, 'archive', '--actor', 'recovery-check', '--reason',
        'Retain post-change canonical evidence before matching-snapshot recovery')
    retained = {p.name: p.read_bytes() for p in (root / '.pyramid/history/records').glob('*.json')}
    cli(new, 'restore', '--archive', archive_id, '--actor', 'recovery-check',
        '--reason', 'Recover matching 4.0 canonical state; retain newer history')
    assert all((root / '.pyramid/history/records' / name).read_bytes() == data
               for name, data in retained.items())
    history_hashes = {name: {'before': hashlib.sha256(data).hexdigest(),
        'after': hashlib.sha256((root / '.pyramid/history/records' / name).read_bytes()).hexdigest()}
        for name, data in retained.items()}
    restored = json.loads((root / '.pyramid/state.json').read_text())['nodes']['RESEARCH-101']
    archive_plan_hash = hashlib.sha256((snapshot_root / '.pyramid/plan.json').read_bytes()).hexdigest()
    restored_plan_hash = hashlib.sha256((root / '.pyramid/plan.json').read_bytes()).hexdigest()
    assert archive_plan_hash == restored_plan_hash
    assert original['last_result'] == restored['last_result']
    assert original['last_audit'] == restored['last_audit']
    assert cli(old, 'validate')['valid']
    assert cli(old, 'inspect', '--audit-readiness', 'RESEARCH-101')['ready']
    history = cli(new, 'history', '--doctor')
    assert history.get('status') == 'valid' and history.get('errors') == [], history
    print(json.dumps({'fixture_only': True, 'live_downgrade_was_ineligible': True,
        'matching_snapshot_recovery_ready': True, 'original_proof_bytes_unchanged': True,
        'archive_id_restored': archive_id, 'snapshot_file_hashes': snapshot_hashes,
        'history_record_hashes': history_hashes, 'live_40_validation': live_old_validation,
        'stale_audit_error': rejected.get('error'),
        'original_40_proofs': original['last_result']['proofs'],
        'restored_40_proofs': restored['last_result']['proofs'],
        'file_actions':file_actions, 'refusal_state_hashes':refusal_state_hashes,
        'restored_plan_hashes':{'snapshot':archive_plan_hash,'live':restored_plan_hash},
        'restore_limit':'Restore appends a new event/context and clears leases; whole state bytes intentionally differ. Original provider result/audit values and later history bytes are compared directly.',
        'newer_history_records_unchanged': len(retained), 'probe_exit_code': observed.returncode,
        'probe_stdout': observed.stdout, 'cli': records}, indent=2))
