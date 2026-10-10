"""Explicit repository-mode probes and bounded opt-in footprint walking."""
from __future__ import annotations
import fnmatch,os
from pathlib import Path
from typing import Any

def artifact_footprint(root: Path, plan: dict, state: dict, baseline: dict | None,
                       *, detail: bool = False, limit: int = 10000) -> dict:
    """Bounded metadata-only preview. References are current, not retention authority."""
    if type(limit) is not int or not 1 <= limit <= 100000:
        raise ValueError('footprint limit must be between 1 and 100000')
    root = root.resolve()
    evidence, generated, inputs, references = [], [], [], set()
    for node in plan['nodes']:
        agent = node.get('agent', {})
        evidence.extend(agent.get('evidence_outputs', []))
        generated.extend(g.get('pattern', '') for g in agent.get('generated_outputs', []))
        inputs.extend(p for e in node.get('required_evidence', [])
                      for p in e.get('verification', {}).get('inputs', []))

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == 'path' and isinstance(item, str):
                    references.add(item)
                elif key == 'evidence' and isinstance(item, list):
                    references.update(x for x in item if isinstance(x, str))
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    for item in state['nodes'].values():
        collect(item.get('last_result', {}))
        collect(item.get('last_audit', {}))
    matches = lambda rel, patterns: any(fnmatch.fnmatchcase(rel, p) for p in patterns)
    counts, files, excluded, errors = {}, [], set(), []
    entries = total_files = total_bytes = 0
    ignored = {'.git', '.venv', 'node_modules', '__pycache__'}
    stack = [os.scandir(root)]
    complete = True
    try:
        while stack:
            if entries >= limit:
                complete = False
                break
            try:
                entry = next(stack[-1])
            except StopIteration:
                stack.pop().close()
                continue
            except OSError as exc:
                errors.append(type(exc).__name__)
                complete = False
                stack.pop().close()
                continue
            entries += 1
            rel = Path(entry.path).relative_to(root).as_posix()
            try:
                if entry.is_symlink():
                    kind, size = 'symlink-not-followed', 0
                elif entry.is_dir(follow_symlinks=False):
                    if entry.name in ignored:
                        excluded.add(rel)
                    else:
                        stack.append(os.scandir(entry.path))
                    continue
                elif not entry.is_file(follow_symlinks=False):
                    kind, size = 'unknown-special', 0
                else:
                    size = entry.stat(follow_symlinks=False).st_size
                    is_input, is_evidence = matches(rel, inputs), matches(rel, evidence)
                    if is_input and is_evidence:
                        kind = 'input-evidence-conflict'
                    elif is_input:
                        kind = 'proof-input'
                    elif rel.startswith('.pyramid/reports/'):
                        kind = 'retained-evidence'
                    elif rel.startswith('.pyramid/') or rel.startswith('docs/tasks/'):
                        kind = 'canonical-or-projection'
                    elif is_evidence:
                        kind = 'declared-evidence'
                    elif matches(rel, generated):
                        kind = 'declared-generated'
                    else:
                        kind = 'unknown'
                total_files += 1
                total_bytes += size
                record = counts.setdefault(kind, {'files': 0, 'bytes': 0, 'currently_referenced': 0})
                record['files'] += 1
                record['bytes'] += size
                record['currently_referenced'] += int(rel in references)
                if detail and len(files) < 100:
                    files.append({'path': rel, 'class': kind, 'bytes': size,
                                  'currently_referenced': rel in references})
            except OSError as exc:
                errors.append(type(exc).__name__)
                complete = False
    finally:
        for iterator in stack:
            iterator.close()
    result = {'schema': 'pyramid-artifact-footprint-v1', 'deletion_authorized': False,
              'scan': {'entries': entries, 'limit': limit, 'complete': complete,
                       'excluded_directories': sorted(excluded)[:100], 'errors': errors[:20]},
              'totals': {'files': total_files, 'bytes': total_bytes},
              'classes': dict(sorted(counts.items())),
              'current_reference_count': len(references),
              'limitations': ['Logical file bytes, not allocated disk or Git size.',
                              'Current result/audit references only; archive, handoff and historical reference ownership is unknown.',
                              'Declared classes are not executed proof or deletion eligibility. Symlinks are not followed.',
                              'Scan excludes Git metadata, .venv, node_modules and Python caches; incomplete scans are partial totals.']}
    if detail:
        result.update(files=sorted(files, key=lambda f: f['path']), detail_limit=100,
                      detail_truncated=total_files > len(files))
    return result


def detect_repository_mode(root: Path) -> str:
    if not root.exists():
        return "greenfield"
    ignored = {".git", ".pyramid", ".DS_Store"}
    for child in root.iterdir():
        if child.name in ignored:
            continue
        if child.name == "docs" and (child / "tasks").exists() and len(list(child.iterdir())) == 1:
            continue
        return "brownfield"
    return "greenfield"
