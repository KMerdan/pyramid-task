"""Outcome-scoped proof contracts and deterministic evidence handling.

No command execution, browser control, model calls, scheduling, or mutable run
registry. Call publication only while holding the existing project lock.
"""
from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


CHANNELS = {"external", "internal", "visual"}
ARTIFACT_DIR = ".pyramid/reports/proof-artifacts"
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_RUN_BYTES = 32 * 1024 * 1024
SHA = re.compile(r"^[a-f0-9]{64}$")


class VerificationError(ValueError):
    pass


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _strings(value: Any, *, nonempty: bool = False) -> bool:
    return isinstance(value, list) and (bool(value) or not nonempty) and all(_text(x) for x in value)


def _relative(value: Any) -> bool:
    return (_text(value) and not PurePosixPath(value).is_absolute()
            and bool(PurePosixPath(value).parts)
            and ".." not in PurePosixPath(value).parts and "\\" not in value)


def _input_pattern(value: Any) -> bool:
    return _relative(value) and all('**' not in part or part == '**'
                                    for part in PurePosixPath(value).parts)


def _catalog(plan: dict) -> dict[str, tuple[dict, dict]]:
    return {f"{n['id']}/{e['id']}": (n, e) for n in plan['nodes']
            for e in n.get('required_evidence', []) if isinstance(e, dict) and 'id' in e}


def _resolve(catalog: dict, key: str, trail: tuple = ()) -> tuple[str, dict, dict]:
    if key in trail:
        raise VerificationError(f"Verification reuse cycle: {' -> '.join((*trail, key))}")
    if key not in catalog:
        raise VerificationError(f"Unknown proof requirement: {key}")
    node, evidence = catalog[key]
    spec = evidence.get('verification')
    if not isinstance(spec, dict):
        raise VerificationError(f"{key}: missing verification contract")
    if 'reuse' in spec:
        return _resolve(catalog, spec['reuse'], (*trail, key))
    return key, node, spec


def validate_contracts(plan: dict) -> list[str]:
    errors: list[str] = []
    if plan.get('schema_version') != 2:
        if any('verification' in e for n in plan.get('nodes', []) if isinstance(n, dict)
               for e in n.get('required_evidence', []) if isinstance(e, dict)):
            errors.append('Harness contracts require plan schema_version 2; older runtimes must reject them')
        return errors
    catalog = _catalog(plan)
    for node in plan['nodes']:
        if node.get('selection') != 'primary':
            continue
        criteria = {c['id'] for c in node.get('acceptance_criteria', [])}
        if not criteria:
            errors.append(f"{node['id']}: a primary claim needs acceptance criteria in a harness-enabled plan")
        covered: set[str] = set()
        seen: set[str] = set()
        for ev in node.get('required_evidence', []):
            key = f"{node['id']}/{ev['id']}"
            if ev['id'] in seen:
                errors.append(f'{key}: duplicate evidence requirement')
            seen.add(ev['id'])
            spec = ev.get('verification')
            if not isinstance(spec, dict):
                errors.append(f'{key}: missing verification contract')
                continue
            linked = spec.get('criteria')
            if not _strings(linked, nonempty=True) or not set(linked).issubset(criteria):
                errors.append(f'{key}: criteria must reference this node acceptance IDs')
            else:
                covered.update(linked)
            if 'reuse' in spec:
                if set(spec) != {'criteria', 'reuse'} or not _text(spec.get('reuse')):
                    errors.append(f'{key}: reuse requires only criteria and a NODE/EVIDENCE reference')
                    continue
                try:
                    _, owner, _ = _resolve(catalog, key)
                    if owner.get('selection') != 'primary':
                        errors.append(f'{key}: cannot reuse a non-primary proof')
                except VerificationError as exc:
                    errors.append(str(exc))
                continue
            required = {'criteria', 'method', 'procedure', 'inputs', 'observations', 'not_applicable', 'environment'}
            if set(spec) != required:
                errors.append(f'{key}: verification requires exactly {sorted(required)}')
            if spec.get('method') not in {'command', 'browser', 'review'}:
                errors.append(f'{key}: method must be command, browser, or review')
            if not _text(spec.get('procedure')) or not _text(spec.get('environment')):
                errors.append(f'{key}: procedure and environment must be explicit')
            inputs = spec.get('inputs')
            if not _strings(inputs) or any(not _input_pattern(x) for x in inputs):
                errors.append(f'{key}: inputs must be safe project-relative file patterns; ** must be a complete path component')
            elif not inputs and spec.get('method') != 'review':
                errors.append(f'{key}: executable proof needs source/fixture/environment inputs')
            obs = spec.get('observations')
            na = spec.get('not_applicable')
            if (not _strings(obs, nonempty=True) or len(set(obs)) != len(obs)
                    or not set(obs).issubset(CHANNELS)):
                errors.append(f'{key}: observations must name distinct external/internal/visual channels')
            elif (not isinstance(na, dict) or set(na) != CHANNELS - set(obs)
                  or not all(_text(v) for v in na.values())):
                errors.append(f'{key}: explain every non-applicable observation channel')
        if criteria - covered:
            errors.append(f"{node['id']}: uncovered verification criteria: {', '.join(sorted(criteria-covered))}")
    return errors


def contracts(plan: dict, nid: str) -> list[dict]:
    if plan.get('schema_version') != 2:
        return []
    catalog = _catalog(plan)
    result = []
    for key, (node, ev) in catalog.items():
        if node['id'] != nid or node.get('selection') != 'primary':
            continue
        owner_key, owner, spec = _resolve(catalog, key)
        # Observation identity follows its producer; consumer acceptance is separate.
        producer = _claim_descriptor(plan, owner_key, owner, catalog[owner_key][1])
        result.append({'requirement': ev['id'], 'owner': owner_key,
                       'criteria': ev['verification']['criteria'], **{k: copy.deepcopy(v) for k, v in spec.items() if k != 'criteria'},
                       'contract_sha256': digest({'version': 2, 'plan': plan['plan_id'], 'owner': owner_key,
                                                  'spec': spec, 'producer': producer})})
    return result


def _claim_descriptor(plan: dict, key: str, node: dict, evidence: dict) -> dict:
    ids = evidence['verification']['criteria']
    return {'requirement': key, 'description': evidence['description'], 'type': evidence['type'],
            'criteria': [c for c in node['acceptance_criteria'] if c['id'] in ids],
            'intent_claims': [c for c in plan['intent']['success_evidence']
                              if c['id'] in node['source_requirements']]}


def _legacy_contract_sha256(plan: dict, owner_key: str) -> str:
    """Exact 4.0 consumer-scoped digest; never guess equivalence from a hash."""
    catalog = _catalog(plan)
    _, _, spec = _resolve(catalog, owner_key)
    consumers = [_claim_descriptor(plan, key, node, evidence)
                 for key, (node, evidence) in catalog.items()
                 if node.get('selection') == 'primary' and _resolve(catalog, key)[0] == owner_key]
    return digest({'plan': plan['plan_id'], 'owner': owner_key, 'spec': spec,
                   'consumers': sorted(consumers, key=lambda c: c['requirement'])})


def validate_proof_bindings(plan: dict, state: dict) -> list[str]:
    bindings = state.get('proof_contract_bindings', {})
    if not isinstance(bindings, dict):
        return ['state.proof_contract_bindings must be an object']
    errors = []
    fields = {'version', 'owner', 'legacy_sha256', 'producer_sha256', 'from_revision', 'to_revision'}
    for rid, binding in bindings.items():
        if (not isinstance(rid, str) or not re.fullmatch(r'RUN-[A-F0-9]{32}', rid)
                or not isinstance(binding, dict) or set(binding) != fields
                or binding.get('version') != 2
                or not isinstance(binding.get('owner'), str)
                or not re.fullmatch(r'[A-Z][A-Z0-9-]*/[A-Z][A-Z0-9-]*', binding['owner'])
                or any(not isinstance(binding.get(k), str) or not SHA.fullmatch(binding[k])
                       for k in ('legacy_sha256', 'producer_sha256'))
                or any(type(binding.get(k)) is not int for k in ('from_revision', 'to_revision'))
                or not 1 <= binding['from_revision'] < binding['to_revision'] <= plan['revision']
                or binding['to_revision'] != binding['from_revision'] + 1):
            errors.append(f'{rid}: invalid guarded proof-contract binding')
    return errors


def replan_proof_bindings(root: Path, old: dict, new: dict, state: dict) -> dict:
    """Explicit compatibility at guarded replan, not install/read-time migration.

    Bind only existing valid 4.0 runs to an identical producer. Keep observation
    bytes and IDs untouched. Current inputs/artifacts must pass on both sides.
    """
    if old.get('schema_version') != 2 or new.get('schema_version') != 2:
        return {}
    bindings = copy.deepcopy(state.get('proof_contract_bindings', {}))
    new_specs = {spec['owner']: spec for node in new['nodes'] if node['selection'] == 'primary'
                 for spec in contracts(new, node['id'])}
    for node in old['nodes']:
        if node['selection'] != 'primary':
            continue
        old_specs = {spec['requirement']: spec for spec in contracts(old, node['id'])}
        for field in ('last_result', 'last_audit'):
            payload = state['nodes'][node['id']].get(field)
            if not isinstance(payload, dict) or not payload:
                continue
            try:
                normalized = normalize_proofs(root, old, state, node['id'], payload)
            except (VerificationError, OSError):
                continue
            for proof in normalized['proofs']:
                spec, run = old_specs[proof['requirement']], proof['run']
                target = new_specs.get(spec['owner'])
                if (target is None or target['contract_sha256'] != spec['contract_sha256']
                        or run['contract_sha256'] == spec['contract_sha256']
                        or run['contract_sha256'] != _legacy_contract_sha256(old, spec['owner'])
                        or run['contract_sha256'] == _legacy_contract_sha256(new, spec['owner'])):
                    continue
                try:
                    if run['inputs_sha256'] != input_snapshot(root, new, target)['sha256']:
                        continue
                except (VerificationError, OSError):
                    continue
                bindings[run['id']] = {'version': 2, 'owner': spec['owner'],
                    'legacy_sha256': run['contract_sha256'], 'producer_sha256': target['contract_sha256'],
                    'from_revision': old['revision'], 'to_revision': new['revision']}
    return bindings


def _input_paths(root: Path, plan: dict, contract: dict, *, require_matches: bool = True) -> set[str]:
    root = root.resolve()
    outputs = [p for n in plan['nodes'] for p in n.get('agent', {}).get('evidence_outputs', [])]
    files: set[str] = set()
    for pattern in contract['inputs']:
        # Python 3.13 accepts embedded ** where older pathlib rejects it.
        # Enforce one portable grammar before delegating matching to the host.
        if not _input_pattern(pattern):
            raise VerificationError(f'Invalid input pattern: {pattern}')
        matched = False
        # pathlib <=3.12 treats trailing ** as directories only; task-scope
        # globs conventionally mean all descendant files on every supported host.
        glob = pattern + '/*' if pattern == '**' or pattern.endswith('/**') else pattern
        if not any(char in glob for char in '*?[') and (root / glob).is_dir():
            glob = glob.rstrip('/') + '/**/*'
        try:
            candidates = list(root.glob(glob))
        except (ValueError, NotImplementedError) as exc:
            raise VerificationError(f'Invalid input pattern: {pattern}') from exc
        for path in candidates:
            rel = path.relative_to(root).as_posix()
            if rel == '.git' or rel.startswith(('.git/', '.pyramid/', 'docs/tasks/')):
                continue
            if not path.is_file():
                continue
            if any(fnmatch.fnmatchcase(rel, p) for p in outputs):
                # Whole-repository captures intentionally exclude dedicated staging.
                # A rooted/specific behavior input must not be silently excluded.
                if require_matches and (pattern not in {'**', '**/*', '*'} or any(p in {'**', '**/*', '*'} for p in outputs)):
                    raise VerificationError(f'Verification input {rel} overlaps declared evidence output; narrow the scopes')
                continue
            if not path.resolve().is_relative_to(root):
                raise VerificationError(f'Input escapes project: {rel}')
            files.add(rel)
            matched = True
        if require_matches and not matched:
            raise VerificationError(f"No verification inputs match {pattern!r}; establish the capability before collecting proof")
    return files


def input_snapshot(root: Path, plan: dict, contract: dict) -> dict:
    files = {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest()
             for rel in _input_paths(root, plan, contract)}
    return {'sha256': digest(files), 'file_count': len(files)}


def validate_amendment_inputs(root: Path, plan: dict, nid: str, writes: list[str]) -> None:
    """Do not extend bound implementation scope beyond its resolved proof inputs.

    Missing setup elsewhere is allowed here; collection still requires every
    pattern to match. Use the exact capture matcher, including output exclusions.
    This checks file coverage, not the semantic sufficiency of the procedure.
    """
    if plan.get('schema_version') != 2 or not writes:
        return
    covered: set[str] = set()
    for contract in contracts(plan, nid):
        covered.update(_input_paths(root, plan, contract, require_matches=False))
    missing = sorted(set(writes) - covered)
    if missing:
        raise VerificationError('Amendment write paths are outside this task\'s verification inputs: '
                                + ', '.join(missing) + '; replan the proof contract before extending scope')


def known_runs(state: dict) -> dict[str, dict]:
    runs = {}
    for item in state['nodes'].values():
        for field in ('last_result', 'last_audit'):
            payload = item.get(field) or {}
            if not isinstance(payload, dict):
                continue
            proofs = payload.get('proofs', [])
            if not isinstance(proofs, list):
                continue
            for proof in proofs:
                if not isinstance(proof, dict):
                    continue
                run = proof.get('run')
                if isinstance(run, dict) and _text(run.get('id')):
                    runs[run['id']] = run
    return runs


def query_harness(root: Path, plan: dict, state: dict, nid: str) -> dict:
    if nid not in {n['id'] for n in plan['nodes']}:
        raise VerificationError(f'Unknown node: {nid}')
    specs = contracts(plan, nid)
    templates, blockers = [], []
    snapshots = {}
    for spec in specs:
        try:
            key = tuple(spec['inputs'])
            if key not in snapshots:
                snapshots[key] = input_snapshot(root, plan, spec)
            snapshot = snapshots[key]
            templates.append({'requirement': spec['requirement'], 'run': {
                'contract_sha256': spec['contract_sha256'], 'inputs_sha256': snapshot['sha256'],
                'environment': spec['environment'], 'observations': [
                    {'kind': kind, 'result': 'not-run', 'summary': '', 'reviewer': '', 'artifacts': []}
                    for kind in spec['observations']]}})
        except (VerificationError, OSError) as exc:
            blockers.append(str(exc))
    reusable = []
    for rid, run in known_runs(state).items():
        for spec in specs:
            snapshot = snapshots.get(tuple(spec['inputs']))
            if snapshot is None:
                continue
            try:
                validate_run(root, plan, spec, run, state.get('proof_contract_bindings', {}),
                             _inputs_sha256=snapshot['sha256'])
            except (VerificationError, OSError):
                continue
            reusable.append({'requirement': spec['requirement'], 'reuse_run': rid})
    return {'schema': 'pyramid-harness-v1', 'target': nid,
            'mode': 'candidate-bound' if plan.get('schema_version') == 2 else 'legacy-unbound',
            'contracts': specs, 'proof_templates': templates, 'reusable_proofs': reusable,
            'setup_blockers': sorted(set(blockers)),
            'instruction': 'Capture this template BEFORE the checks. Execute or inspect the stated procedure; never invent observations. Source inputs must remain unchanged through submission.'}


def _artifact(root: Path, artifact: dict) -> tuple[Path, bytes]:
    if not isinstance(artifact, dict) or set(artifact) != {'path', 'sha256'}:
        raise VerificationError('Artifacts require exactly path and sha256')
    rel, sha = artifact['path'], artifact['sha256']
    if not _relative(rel) or not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise VerificationError('Artifact path or SHA-256 is invalid')
    if rel.startswith('.pyramid/') and not rel.startswith(ARTIFACT_DIR + '/'):
        raise VerificationError('Do not stage proof inside canonical .pyramid storage')
    path = root / rel
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise VerificationError(f'Missing or out-of-project artifact: {rel}')
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise VerificationError(f'Artifact exceeds 16 MiB; retain bounded acceptance evidence: {rel}')
    data = path.read_bytes()
    if not data or hashlib.sha256(data).hexdigest() != sha:
        raise VerificationError(f'Empty or changed artifact: {rel}')
    return path, data


def validate_run(root: Path, plan: dict, spec: dict, run: dict, bindings: dict | None = None,
                 *, _inputs_sha256: str | None = None) -> None:
    # Private read-query reuse only. Submission/readiness callers always take a
    # fresh snapshot; nothing from CLI/JSON can populate this value.
    if not isinstance(run, dict) or set(run) - {'id', 'contract_sha256', 'inputs_sha256', 'environment', 'observations'}:
        raise VerificationError('Malformed proof run')
    if run.get('contract_sha256') != spec['contract_sha256']:
        binding = (bindings or {}).get(run.get('id'))
        bound = (isinstance(binding, dict) and binding.get('version') == 2
                 and binding.get('owner') == spec['owner']
                 and binding.get('legacy_sha256') == run.get('contract_sha256')
                 and binding.get('producer_sha256') == spec['contract_sha256'])
        if not bound and run.get('contract_sha256') != _legacy_contract_sha256(plan, spec['owner']):
            raise VerificationError(f"{spec['requirement']}: proof contract changed")
    current_sha = _inputs_sha256 if _inputs_sha256 is not None else input_snapshot(root, plan, spec)['sha256']
    if run.get('inputs_sha256') != current_sha:
        raise VerificationError(f"{spec['requirement']}: candidate inputs changed; collect fresh proof")
    if run.get('environment') != spec['environment']:
        raise VerificationError(f"{spec['requirement']}: environment contract mismatch")
    obs = run.get('observations')
    if not isinstance(obs, list) or len(obs) != len(spec['observations']):
        raise VerificationError(f"{spec['requirement']}: missing or duplicate observations")
    seen = set()
    total = 0
    for item in obs:
        if not isinstance(item, dict) or set(item) != {'kind', 'result', 'summary', 'reviewer', 'artifacts'}:
            raise VerificationError('Observation requires kind, result, summary, reviewer and artifacts')
        kind = item['kind']
        if kind not in spec['observations'] or kind in seen:
            raise VerificationError('Unknown or duplicate observation channel')
        seen.add(kind)
        if item['result'] != 'passed' or not _text(item['summary']) or not _text(item['reviewer']):
            raise VerificationError('Every required observation must be performed, explained and reviewed')
        artifacts = item['artifacts']
        if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 16:
            raise VerificationError('An observation needs 1–16 bounded artifacts')
        visual = False
        for artifact in artifacts:
            _, data = _artifact(root, artifact)
            total += len(data)
            visual |= (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff')
                       or (data[:4] == b'RIFF' and data[8:12] == b'WEBP'))
        if kind == 'visual' and not visual:
            raise VerificationError('Visual observation needs a PNG, JPEG or WebP capture and its actual review')
    if total > MAX_RUN_BYTES:
        raise VerificationError('Run artifacts exceed 32 MiB; retain only necessary acceptance evidence')


def normalize_proofs(root: Path, plan: dict, state: dict, nid: str, payload: dict) -> dict:
    """Read/validate first; no canonical writes. Reuse carries no new execution."""
    if plan.get('schema_version') != 2:
        if payload.get('proofs'):
            raise VerificationError('Adopt plan schema_version 2 before submitting bound proofs')
        return copy.deepcopy(payload)
    result = copy.deepcopy(payload)
    entries = result.get('proofs')
    if 'proofs' not in result:
        entries = (state['nodes'][nid].get('last_result') or {}).get('proofs', [])
    if not isinstance(entries, list):
        raise VerificationError('proofs must be an array')
    by_id = {}
    runs = known_runs(state)
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) not in ({'requirement', 'run'}, {'requirement', 'reuse_run'}):
            raise VerificationError('Proof needs a requirement and exactly one run or reuse_run')
        if not _text(entry['requirement']) or entry['requirement'] in by_id:
            raise VerificationError('Duplicate or invalid proof requirement')
        if 'reuse_run' in entry and not _text(entry['reuse_run']):
            raise VerificationError('reuse_run must name a recorded run ID')
        by_id[entry['requirement']] = entry
    specs = contracts(plan, nid)
    if set(by_id) != {s['requirement'] for s in specs}:
        raise VerificationError(f'{nid}: proof entries must cover exactly the required evidence')
    normalized, acceptance, checks = [], [], []
    for spec in specs:
        entry = by_id[spec['requirement']]
        run = copy.deepcopy(entry.get('run') if 'run' in entry else runs.get(entry['reuse_run']))
        validate_run(root, plan, spec, run, state.get('proof_contract_bindings', {}))
        # Identity follows observed content; canonical storage paths are excluded.
        material = copy.deepcopy({k: v for k, v in run.items() if k != 'id'})
        for observation in material['observations']:
            observation['artifacts'] = [{'sha256': a['sha256']} for a in observation['artifacts']]
        rid = 'RUN-' + digest(material)[:32].upper()
        if run.get('id', rid) != rid:
            raise VerificationError('Proof run ID does not match its content')
        # Re-copy because the identity material is deliberately path-free.
        run = copy.deepcopy(entry.get('run') if 'run' in entry else runs[entry['reuse_run']])
        run['id'] = rid
        normalized.append({'requirement': spec['requirement'], 'run': run})
        checks.append(({'command': spec['procedure'], 'result': 'passed', 'evidence': [rid]}
                       if result.get('schema') == 'agent-result-v1' else
                       {'id': spec['requirement'], 'result': 'passed', 'evidence': [rid]}))
        acceptance.extend({'criterion': cid, 'result': 'passed', 'reference': rid} for cid in spec['criteria'])
    result['proofs'] = normalized
    if 'checks' not in result or result['checks'] == []:
        result['checks'] = checks
    elif not isinstance(result['checks'], list) or any(
            not isinstance(check, dict) or check.get('result') != 'passed' for check in result['checks']):
        raise VerificationError('Cannot replace failed, unperformed, or malformed checks with passing proofs')
    if result.get('schema') == 'agent-result-v1':
        if 'acceptance_evidence' not in result or result['acceptance_evidence'] == []:
            result['acceptance_evidence'] = acceptance
        elif not isinstance(result['acceptance_evidence'], list) or any(
                not isinstance(item, dict) or item.get('result') != 'passed'
                for item in result['acceptance_evidence']):
            raise VerificationError('Cannot replace failed or malformed acceptance evidence with passing proofs')
    return result


def publish_artifacts(root: Path, payload: dict) -> list[Path]:
    """Ingest verified artifacts into archive-aware storage under the caller lock.

    Returns newly created paths, so the caller can remove its own unpublished
    files if publication fails. Existing content-addressed artifacts are reused.
    """
    staged: dict[Path, bytes] = {}
    for proof in payload.get('proofs', []):
        for obs in proof['run']['observations']:
            for artifact in obs['artifacts']:
                _, data = _artifact(root, artifact)
                target = root / ARTIFACT_DIR / artifact['sha256']
                if not target.resolve().is_relative_to(root.resolve()):
                    raise VerificationError('Proof storage escapes project')
                staged[target] = data
                artifact['path'] = target.relative_to(root).as_posix()
    created = []
    try:
        for target, data in staged.items():
            if target.exists():
                if target.read_bytes() != data:
                    raise VerificationError(f'Existing proof artifact is corrupt: {target.name}')
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                created.append(target)
                stream.write(data)
        return created
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def proof_readiness(root: Path, plan: dict, state: dict, nid: str) -> dict:
    if plan.get('schema_version') != 2:
        return {'mode': 'legacy-unbound', 'ready': True, 'blockers': []}
    item = state['nodes'][nid]
    payload = item.get('last_audit') if item.get('verification') == 'passed' else item.get('last_result')
    try:
        normalize_proofs(root, plan, state, nid, payload or {})
        return {'mode': 'candidate-bound', 'ready': True, 'blockers': []}
    except (VerificationError, OSError) as exc:
        return {'mode': 'candidate-bound', 'ready': False, 'blockers': [str(exc)]}


def render_guide(plan: dict, nid: str | None = None) -> str:
    lines = ['<!-- Generated from canonical proof contracts. Do not edit. -->',
             '# Development harness', '',
             'Use existing project tools. Implement only missing observation capability before outcome acceptance.',
             'Capture inspect --harness <node> before executing checks. Inspect visual captures, not merely their existence.',
             'A missing/failed observation blocks its claim, not independent authorized work. Never weaken acceptance to pass.',
             'Keep result, evidence and limitations separate. A fresh guard is invocation authority, not reviewed source or host permission.', '']
    if plan.get('schema_version') != 2:
        return '\n'.join(lines + ['Legacy plan: source-bound harness contracts have not been adopted.', ''])
    for node in plan['nodes']:
        if node['selection'] != 'primary' or (nid and node['id'] != nid):
            continue
        specs = contracts(plan, node['id'])
        if not specs:
            continue
        lines += [f"## {node['id']}: {node['title']}", '']
        for spec in specs:
            if nid is None and spec['owner'] != f"{node['id']}/{spec['requirement']}":
                lines += [f"- `{spec['requirement']}` covers {', '.join(spec['criteria'])} by reusing `{spec['owner']}`; no duplicate execution.", '']
                continue
            lines += [f"### {spec['requirement']} → {', '.join(spec['criteria'])}", '',
                      f"- Shared definition: `{spec['owner']}`",
                      f"- Method: {spec['method']}; environment: {spec['environment']}",
                      f"- Procedure: {spec['procedure']}",
                      f"- Inputs: {', '.join(spec['inputs']) or 'Documentary review; no repository inputs'}",
                      f"- Required observations: {', '.join(spec['observations'])}"]
            lines += [f'- {channel} not applicable: {reason}' for channel, reason in spec['not_applicable'].items()]
            lines.append('')
    return '\n'.join(lines)
