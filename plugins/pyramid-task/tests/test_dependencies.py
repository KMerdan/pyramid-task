from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import jsonschema

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'scripts'))
import pyramid_dependencies as deps
from pyramid_benchmark import benchmark, score

CORPUS = PLUGIN / 'tests/fixtures/dependencies'


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def validate_report(self, report):
        schema = json.loads((PLUGIN / 'schemas/dependency-analysis.schema.json').read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(report['analysis'])
        metrics = dict(schema['$defs']['metrics'])
        metrics['properties'] = dict(metrics['properties'], analysis={k: v for k, v in schema.items() if k not in {'$defs', '$id'}})
        jsonschema.Draft202012Validator(metrics).validate(report)

    def assert_basic(self, result):
        self.assertEqual(set(result['languages']), {'JS', 'JSX', 'TS', 'TSX', 'Rust'})
        for language, row in result['languages'].items():
            for stage in ['extraction', 'resolution']:
                self.assertEqual((row[stage]['fp'], row[stage]['fn']), (0, 0), (language, stage, row))
            self.assertFalse(row['unknown_detection']['missing'], (language, row))
        self.assertFalse(result['analysis']['scope_removal_authorized'])

    def test_actual_absence_subprocess_scores_all_languages(self):
        # Production entry, fresh interpreter, empty executable search path.
        env = dict(os.environ, PATH=str(self.root), PYTHONDONTWRITEBYTECODE='1', PYRAMID_USAGE='off')
        self.assertIsNone(shutil.which('ast-grep', path=env['PATH']))
        self.assertIsNone(shutil.which('sg', path=env['PATH']))
        command = [sys.executable, str(PLUGIN / 'scripts/pyramid_benchmark.py'), '--manifest', str(CORPUS / 'basic/manifest.json'), '--provider', 'auto']
        process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result['provider'], 'python')
        self.assertEqual(result['cache'], 'disabled')
        self.assertIn({'reason': 'ast-grep-unavailable'}, result['analysis']['diagnostics'])
        self.assert_basic(result)
        self.validate_report(result)

    def test_real_ast_grep_on_frozen_basic_corpus(self):
        if deps._provider('auto')[0] is None: self.skipTest('Optional ast-grep absent; absence qualified separately')
        result = benchmark(CORPUS / 'basic/manifest.json', provider='ast-grep')
        self.assertEqual(result['provider'], 'ast-grep', result['analysis']['diagnostics'])
        self.assert_basic(result)
        self.validate_report(result)

    def test_previous_pilot_is_regression_for_declared_rust_module_ownership(self):
        result = benchmark(CORPUS / 'heldout/manifest.json', provider='python')
        self.validate_report(result)
        rust = result['languages']['Rust']['resolution']
        self.assertEqual(rust['tp'] + rust['fn'], 3)
        self.assertEqual((rust['tp'], rust['fp'], rust['fn']), (3, 0, 0))
        self.assertIsNone(result['languages']['JS']['resolution']['recall'])

    def test_default_api_and_benchmark_do_not_discover_or_launch_ast_grep(self):
        with mock.patch.object(deps.shutil, 'which', side_effect=AssertionError('unexpected executable discovery')), mock.patch.object(deps, '_ast_ranges', side_effect=AssertionError('unexpected AST process')):
            result = benchmark(CORPUS / 'basic/manifest.json')
        self.assertEqual(result['provider'], 'python')
        self.assertEqual(result['analysis']['requested_provider'], 'python')
        self.assertEqual(result['analysis']['diagnostics'], [])
        self.assert_basic(result)

    def rust_project(self):
        self.write('Cargo.toml', '[package]\nname="fixture"\nversion="0.1.0"\nedition="2021"\n')
        self.write('src/lib.rs', 'mod consumer; mod model; mod nested { pub fn helper() {} }')
        self.write('src/model.rs', 'pub struct Thing;')
        self.write('src/consumer.rs', 'use super::model::Thing; use crate::nested::helper; use super::*;')

    def test_rust_parent_inline_symbols_path_attributes_and_repeated_reads(self):
        self.rust_project()
        result = deps.analyze_dependencies(self.root, ['src/consumer.rs'], provider='python')
        self.assertEqual([edge['target'] for edge in result['edges']], ['src/model.rs', 'src/lib.rs', 'src/lib.rs'])
        self.assertIn('src/lib.rs', result['inputs'])
        self.write('src/lib.rs', '#[path="renamed.rs"] mod model; mod consumer; mod nested { pub fn helper() {} }')
        self.write('src/renamed.rs', 'pub struct Thing;')
        newer = deps.analyze_dependencies(self.root, ['src/consumer.rs'], provider='python')
        self.assertEqual(newer['edges'][0]['target'], 'src/renamed.rs')
        self.assertNotEqual(newer['identity_sha256'], result['identity_sha256'])

    def test_rust_does_not_infer_unreferenced_file_or_reexport_symbol_owner(self):
        self.rust_project()
        self.write('src/ghost.rs', 'pub struct Thing;')
        self.write('src/consumer.rs', 'use crate::ghost::Thing; use crate::nested::missing;')
        report = deps.analyze_dependencies(self.root, ['src/consumer.rs'], provider='python')
        self.assertEqual(report['edges'], [])
        self.assertEqual(len(report['unresolved']), 2)
        self.write('src/lib.rs', 'mod consumer; mod model; pub use model::Thing;')
        self.write('src/consumer.rs', 'use crate::Thing;')
        report = deps.analyze_dependencies(self.root, ['src/consumer.rs'], provider='python')
        self.assertFalse(report['edges'])
        expected = {('src/consumer.rs', 'use', 'src/model.rs', 1)}
        self.assertEqual(score(expected, set())['fn'], 1)
        self.assertFalse(report['scope_removal_authorized'])

    def test_rust_ambiguous_roots_conditional_paths_cycles_and_limits_abstain(self):
        self.rust_project()
        self.write('src/lib.rs', 'mod consumer; mod model;')
        self.write('src/main.rs', 'mod consumer; #[path="other.rs"] mod model;')
        self.write('src/other.rs', 'pub struct Thing;')
        self.write('src/consumer.rs', 'use crate::model::Thing;')
        report = deps.analyze_dependencies(self.root, ['src/consumer.rs'], provider='python')
        self.assertFalse(report['edges'])
        self.assertEqual(report['unresolved'][0]['reason'], 'ambiguous-module-resolution')
        (self.root / 'src/main.rs').unlink()
        self.write('src/lib.rs', 'mod consumer; #[cfg_attr(feature="x", path="other.rs")] mod model;')
        self.assertFalse(deps.analyze_dependencies(self.root, ['src/consumer.rs'], provider='python')['edges'])
        self.write('src/lib.rs', 'mod consumer; #[path="lib.rs"] mod model;')
        cycle = deps.analyze_dependencies(self.root, ['src/consumer.rs'], provider='python')
        self.assertFalse(cycle['scan']['complete'])
        self.assertFalse(cycle['edges'])
        self.rust_project()
        with mock.patch.object(deps, 'MAX_RUST_MODULE_FILES', 1):
            limited = deps.analyze_dependencies(self.root, ['src/consumer.rs'], provider='python')
        self.assertFalse(limited['scan']['complete'])
        self.assertIn('rust-module-index-incomplete', [d['reason'] for d in limited['diagnostics']])

    def test_rust_supporting_file_change_invalidates_identity_and_custom_roots_are_unknown(self):
        self.rust_project()
        run = lambda: deps.analyze_dependencies(self.root, ['src/consumer.rs'], provider='python')
        before = run()
        self.write('src/lib.rs', 'mod consumer; mod model; mod nested { pub fn changed() {} }')
        after = run()
        self.assertNotEqual(before['identity_sha256'], after['identity_sha256'])
        self.assertTrue(after['unresolved'])
        self.write('Cargo.toml', '[package]\nname="fixture"\nversion="0.1.0"\n[lib]\npath="different.rs"\n')
        custom = run()
        self.assertFalse(custom['edges'])
        self.assertEqual(custom['unresolved'][0]['reason'], 'rust-custom-crate-root-unresolved')

    def test_supporting_rust_source_change_during_indexing_is_not_complete(self):
        self.rust_project()
        original = deps.RustModules.read
        changed = False
        def changing(index, relative):
            nonlocal changed
            result = original(index, relative)
            if str(relative) == 'src/lib.rs' and not changed:
                changed = True
                self.write('src/lib.rs', 'mod consumer; mod model;')
            return result
        with mock.patch.object(deps.RustModules, 'read', changing):
            result = deps.analyze_dependencies(self.root, ['src/consumer.rs'], provider='python')
        self.assertFalse(result['scan']['complete'])
        self.assertIn('candidate-changed-during-analysis', [d['reason'] for d in result['diagnostics']])

    def test_actual_tool_absence_on_new_independent_corpus_retains_reexport_gaps(self):
        env = dict(os.environ, PATH=str(self.root), PYTHONDONTWRITEBYTECODE='1', PYRAMID_USAGE='off')
        command = [sys.executable, str(PLUGIN / 'scripts/pyramid_benchmark.py'), '--manifest', str(CORPUS / 'heldout-v2/manifest.json'), '--provider', 'auto']
        process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.validate_report(report)
        self.assertEqual(report['provider'], 'python')
        self.assertEqual(set(report['languages']), {'JS', 'JSX', 'TS', 'TSX', 'Rust'})
        rust = report['languages']['Rust']['resolution']
        self.assertEqual((rust['tp'], rust['fp'], rust['fn']), (2, 0, 2))
        self.assertEqual(rust['recall'], 0.5)
        self.assertTrue(rust['false_negatives'])
        for row in report['languages'].values():
            self.assertFalse(row['unknown_detection']['missing'])

    def test_failed_timed_out_and_invalid_ast_output_fall_back_visibly(self):
        self.write('main.ts', 'import "./dep";')
        self.write('dep.ts', 'export {};')
        for failure in [subprocess.TimeoutExpired('ast-grep', 1), ValueError('ast-scan-failed'), KeyError('range')]:
            with self.subTest(failure=type(failure).__name__), mock.patch.object(deps, '_provider', return_value=('/synthetic/ast-grep', '0.45.3', [])), mock.patch.object(deps, '_ast_ranges', side_effect=failure):
                result = deps.analyze_dependencies(self.root, ['main.ts'], provider='ast-grep')
                self.assertEqual(result['provider'], 'python')
                self.assertEqual(result['edges'][0]['target'], 'dep.ts')
                self.assertEqual(result['diagnostics'][0]['failure'], type(failure).__name__)

    def test_unrelated_sg_is_rejected_and_probe_timeout_diagnosed(self):
        with mock.patch.object(deps.shutil, 'which', side_effect=[None, '/usr/bin/sg']), mock.patch.object(deps.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'sg util-linux 2.40\n', b'')):
            executable, _, diagnoses = deps._provider('auto')
            self.assertIsNone(executable)
            self.assertEqual(diagnoses[0]['reason'], 'incompatible-executable')
        with mock.patch.object(deps.shutil, 'which', return_value='/timeout'), mock.patch.object(deps.subprocess, 'run', side_effect=subprocess.TimeoutExpired('probe', 2)):
            self.assertEqual(deps._provider('auto')[2][0]['reason'], 'provider-probe-failed')

    def test_imports_config_provider_and_candidate_membership_change_identity(self):
        main = self.write('main.ts', 'import "./dep";')
        self.write('dep.ts', 'export {};')
        run = lambda: deps.analyze_dependencies(self.root, ['main.ts'], provider='python')
        initial = run()
        self.assertEqual(run()['identity_sha256'], initial['identity_sha256'])
        other = self.write('dep.tsx', 'export {};')
        ambiguous = run()
        self.assertFalse(ambiguous['edges'])
        self.assertNotEqual(initial['identity_sha256'], ambiguous['identity_sha256'])
        other.unlink()
        self.assertEqual(run()['identity_sha256'], initial['identity_sha256'])
        self.write('tsconfig.json', '{"compilerOptions":{"baseUrl":"."}}')
        configured = run()
        self.assertNotEqual(initial['identity_sha256'], configured['identity_sha256'])
        main.write_text('import "./missing";')
        self.assertNotEqual(configured['identity_sha256'], run()['identity_sha256'])

    def test_broken_config_escape_symlink_truncation_and_malformed_source_are_visible(self):
        self.write('main.ts', 'import "alias"; import "../outside"; import(variable);')
        self.write('tsconfig.json', '{"compilerOptions":{"paths":{"alias":false}}}')
        (self.root / 'link.ts').symlink_to(self.root / 'main.ts')
        result = deps.analyze_dependencies(self.root, ['main.ts', 'link.ts'], provider='python')
        self.assertFalse(result['scan']['complete'])
        self.assertTrue(result['scan']['skipped'])
        self.assertEqual(result['diagnostics'][0]['reason'], 'unsupported-or-unreadable-config')
        self.assertEqual(len(result['edges']), 0)
        self.assertFalse(result['scope_removal_authorized'])
        limited = deps.analyze_dependencies(self.root, ['main.ts', 'link.ts'], provider='python', limit=1)
        self.assertEqual(limited['scan']['truncated'], 1)
        _, unknown = deps.extract('import "unterminated', 'TS')
        self.assertEqual(unknown[0]['reason'], 'unterminated-string')

    def test_unicode_positions_python_ast_and_source_changed_during_scan(self):
        refs, _ = deps.extract('const x="雪";\nimport "./dep";', 'TS')
        self.assertEqual((refs[0]['line'], refs[0]['column']), (2, 1))
        refs, _ = deps.extract('from .helper import X\nimport pathlib', 'Python')
        self.assertEqual([r['specifier'] for r in refs], ['.helper', 'pathlib'])
        main = self.write('main.ts', 'import "./dep";')
        def changed(*args):
            main.write_text('import "./other";')
            return {main: []}
        with mock.patch.object(deps, '_provider', return_value=('ast-grep', '0.45.3', [])), mock.patch.object(deps, '_ast_ranges', side_effect=changed):
            result = deps.analyze_dependencies(self.root, ['main.ts'], provider='ast-grep')
        self.assertFalse(result['scan']['complete'])
        self.assertIn('candidate-changed-during-analysis', [d['reason'] for d in result['diagnostics']])

    def test_corpus_tampering_and_zero_denominators(self):
        shutil.copytree(CORPUS / 'basic', self.root / 'copy')
        (self.root / 'copy/js/main.js').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            benchmark(self.root / 'copy/manifest.json', provider='python')
        self.assertIsNone(score(set(), set())['precision'])
        self.assertEqual(score({('expected',)}, set())['recall'], 0)
