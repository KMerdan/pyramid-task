#!/usr/bin/env python3
"""Score actual dependency output against an independent, hash-bound corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from pyramid_dependencies import LANGUAGES, analyze_dependencies, safe_file


def score(expected: set, predicted: set):
    tp = len(expected & predicted); fp = len(predicted - expected); fn = len(expected - predicted)
    return {'tp': tp, 'fp': fp, 'fn': fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'false_positives': [list(item) for item in sorted(predicted - expected)],
            'false_negatives': [list(item) for item in sorted(expected - predicted)]}


def benchmark(manifest_path: Path, *, provider='python'):
    manifest_path = manifest_path.resolve(); root = manifest_path.parent
    raw = manifest_path.read_bytes(); manifest = json.loads(raw)
    if manifest.get('schema') != 'pyramid-dependency-corpus-v1': raise ValueError('Unsupported corpus manifest')
    files = manifest.get('files')
    if not isinstance(files, list) or not files: raise ValueError('Corpus needs files')
    if len(files) > 1000: raise ValueError('Corpus exceeds analysis file limit')
    seen = set()
    for record in files:
        if not isinstance(record, dict) or not isinstance(record.get('path'), str) or record['path'] in seen:
            raise ValueError('Invalid or duplicate corpus member')
        seen.add(record['path'])
        if not isinstance(record.get('family'), str) or not record['family']: raise ValueError('Missing syntax family')
        for field, target in [('expected_references', 'specifier'), ('expected_edges', 'target')]:
            if not isinstance(record.get(field), list): raise ValueError('Missing reference annotations')
            for item in record[field]:
                if not isinstance(item, dict) or item.get('source') != record['path'] or not isinstance(item.get('kind'), str) or not isinstance(item.get(target), str) or type(item.get('line')) is not int or item['line'] < 1:
                    raise ValueError('Invalid reference annotation')
        for item in record.get('expected_unresolved', []):
            if not isinstance(item, dict) or not isinstance(item.get('reason'), str) or type(item.get('line')) is not int or item['line'] < 1:
                raise ValueError('Invalid unknown annotation')
        path = safe_file(root, record['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']: raise ValueError('Corpus source hash mismatch')
        if LANGUAGES.get(path.suffix) != record['language']: raise ValueError('Corpus language mismatch')
    started = time.monotonic()
    actual = analyze_dependencies(root, [record['path'] for record in files], provider=provider)
    duration = time.monotonic() - started
    def key(item, stage): return (item['source'], item['kind'], item['specifier'] if stage == 'extraction' else item['target'], item['line'])
    groups = {}
    for language in sorted({record['language'] for record in files}):
        selected = [record for record in files if record['language'] == language]
        result = {'files': len(selected), 'syntax_families': sorted({record['family'] for record in selected}),
                  'unresolved': sum(item['language'] == language for item in actual['unresolved'])}
        for stage, field, gold in [('extraction', 'references', 'expected_references'), ('resolution', 'edges', 'expected_edges')]:
            expected = {key(item, stage) for record in selected for item in record[gold]}
            predicted = {key(item, stage) for item in actual[field] if item['language'] == language}
            result[stage] = score(expected, predicted)
        result['families'] = {}
        for family in result['syntax_families']:
            members = [record for record in selected if record['family'] == family]; paths = {r['path'] for r in members}
            result['families'][family] = {}
            for stage, field, gold in [('extraction', 'references', 'expected_references'), ('resolution', 'edges', 'expected_edges')]:
                result['families'][family][stage] = score({key(item, stage) for record in members for item in record[gold]}, {key(item, stage) for item in actual[field] if item['source'] in paths})
        expected_signals = {(record['path'], signal['reason'], signal['line']) for record in selected for signal in record.get('expected_unresolved', [])}
        observed_signals = {(item['source'], item['reason'], item['line']) for item in actual['unresolved'] if item['language'] == language}
        result['unknown_detection'] = {'expected': len(expected_signals), 'detected': len(expected_signals & observed_signals),
                                       'missing': [list(item) for item in sorted(expected_signals - observed_signals)]}
        groups[language] = result
    return {'schema': 'pyramid-dependency-metrics-v1', 'corpus': manifest.get('name'),
            'corpus_kind': manifest.get('kind'), 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
            'provenance': manifest.get('provenance'), 'provider': actual['provider'],
            'provider_version': actual['provider_version'], 'cache': actual['cache'],
            'duration_seconds': duration, 'languages': groups, 'analysis': actual,
            'limitations': ['Accuracy describes this frozen corpus; unsupported and unresolved targets remain visible.',
                            'No arbitrary real-corpus release threshold or automatic scope-removal authority.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--provider', choices=['auto', 'python', 'ast-grep'], default='python')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try: result = benchmark(args.manifest, provider=args.provider)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, 'Benchmark failed: ' + str(exc) + '\n')
    text = json.dumps(result, indent=2) + '\n'
    if args.output: args.output.write_text(text)
    else: print(text, end='')


if __name__ == '__main__': main()
