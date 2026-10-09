"""Read-only proof footprint and declared overlap; no parser, process or scheduler."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import fnmatch

from pyramid_verification import VerificationError, _input_paths, contracts, query_harness, proof_readiness


def analyze_proofs(root: Path, plan: dict, state: dict, nid: str, *, limit=1000):
    if not 1 <= limit <= 10000: raise ValueError('Analysis limit must be 1-10000')
    nodes = {node['id']: node for node in plan['nodes']}
    if nid not in nodes: raise ValueError('Unknown proof-analysis node')
    families = {}; failures = []
    for node in plan['nodes']:
        if node['selection'] != 'primary': continue
        for contract in contracts(plan, node['id']):
            key = contract['owner']
            if key not in families:
                try:
                    files = _input_paths(root, plan, contract)
                    families[key] = {'contract': contract, 'files': files, 'consumers': []}
                except (VerificationError, OSError) as exc:
                    failures.append({'owner': key, 'reason': str(exc)})
                    families[key] = {'contract': contract, 'files': set(), 'consumers': []}
            families[key]['consumers'].append({'node': node['id'], 'requirement': contract['requirement']})
    selected = contracts(plan, nid); owners = {spec['owner'] for spec in selected}
    counts = Counter(path for family in families.values() for path in family['files'])
    proofs = []
    for owner in sorted(owners):
        family = families[owner]; files = family['files']; overlap = []
        for node in plan['nodes']:
            if node['selection'] != 'primary': continue
            scopes = node.get('agent', {}).get('allowed_write_scope', [])
            matched = sorted(path for path in files if any(fnmatch.fnmatchcase(path, pattern) for pattern in scopes))
            if matched:
                overlap.append({'node': node['id'], 'files': matched[:limit], 'file_count': len(matched),
                                'truncated': len(matched) > limit})
        proofs.append({'owner': owner, 'inputs': family['contract']['inputs'], 'file_count': len(files),
                       'files': sorted(files)[:limit], 'truncated': len(files) > limit,
                       'consumers': family['consumers'], 'write_overlap': overlap,
                       'review_reason': 'Declared write overlap predicts fingerprint changes, not semantic necessity.'})
    shared = [{'path': path, 'proof_families': count} for path, count in counts.most_common()
              if count > 1 and any(path in families[owner]['files'] for owner in owners)]
    harness = query_harness(root, plan, state, nid)
    return {'schema': 'pyramid-proof-analysis-v1', 'target': nid,
            'mode': harness['mode'], 'proofs': proofs, 'shared_inputs': shared[:limit],
            'reusable_proofs': harness['reusable_proofs'],
            'current_proof': proof_readiness(root, plan, state, nid),
            'setup_blockers': harness['setup_blockers'], 'scope_failures': failures,
            'scan': {'complete': not failures and all(not p['truncated'] for p in proofs) and len(shared) <= limit,
                     'limit': limit, 'proof_families': len(families)},
            'scope_removal_authorized': False,
            'limitations': ['Existing matching files only; future paths and actual code dependency are not inferred.',
                            'This projection preserves all current audit and inspection obligations.']}


def attach_dependencies(report: dict, dependencies: dict):
    """Combine factual outputs without using them to change proof authority."""
    declared = {path for proof in report['proofs'] for path in proof['files']}
    report['dependencies'] = dependencies
    report['dependencies_outside_inputs'] = sorted({edge['target'] for edge in dependencies['edges']} - declared)
    if not dependencies['scan']['complete'] or dependencies['unresolved'] or dependencies['diagnostics']:
        report['limitations'].append('Dependency analysis is incomplete or uncertain; scope reduction needs review.')
    return report
