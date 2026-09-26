from __future__ import annotations

import concurrent.futures
import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jsonschema

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'scripts'))
import pyramid
from pyramid_usage import UsageRecorder, usage_path


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.storage = self.root / 'usage'
        self.db = self.storage / 'usage.sqlite3'
        self.env = {**os.environ, 'PYRAMID_USAGE': 'on', 'PYRAMID_USAGE_DIR': str(self.storage),
                    'PYTHONDONTWRITEBYTECODE': '1'}

    def cli(self, *args, code=0, env=None):
        result = subprocess.run([sys.executable, '-B', str(PLUGIN / 'scripts/pyramid.py'), *args],
                                env=env or self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(code, result.returncode, result.stdout + result.stderr)
        return result

    def report(self, *args, code=0):
        result = json.loads(self.cli('inspect', '--usage', '--json', *args, code=code).stdout)
        schema = json.loads((PLUGIN / 'schemas/usage-report.schema.json').read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(result, schema)
        return result

    def create(self, name='project'):
        return self.cli('create', '--project', str(self.root / name), '--plan',
                        str(PLUGIN / 'assets/example-plan.json'), '--actor', 'PRIVATE-ACTOR',
                        '--mode', 'greenfield', '--json')

    def fail(self, **kwargs):
        return self.cli('inspect', '--project', str(self.root / 'PRIVATE-MISSING-PROJECT'),
                        '--node', 'PRIVATE-NODE', '--json', code=2, **kwargs)

    def test_empty_report_is_read_only_and_lists_every_command(self):
        result = self.report()
        self.assertEqual('empty', result['status'])
        self.assertEqual(0, result['totals']['invocations'])
        catalog = pyramid.build_parser().get_default('command_catalog')
        self.assertEqual(set(catalog), {row['command'] for row in result['commands']})
        self.assertTrue(all(set(row) == {'command', 'invocations'} for row in result['commands']))
        self.assertEqual(['orchestrate', 'simplify'], result['unmeasured_skills'])
        self.assertFalse(self.storage.exists())
        self.assertFalse((self.root / '.pyramid').exists())

    def test_real_calls_across_projects_count_once_without_storing_arguments(self):
        first, second, failure = self.create('one'), self.create('two'), self.fail()
        before = self.db.read_bytes()
        result = self.report('--full')
        self.assertEqual(before, self.db.read_bytes())
        counts = {r['command']: r for r in result['commands']}
        self.assertEqual(2, counts['create']['succeeded'])
        self.assertEqual(1, counts['inspect']['failed'])
        self.assertEqual(0, counts['audit']['invocations'])
        self.assertEqual(3, result['totals']['invocations'])
        self.assertEqual(0, result['totals']['unfinished'])
        self.assertEqual(sum(len(r.stdout.encode('utf-8')) for r in (first, second, failure)),
                         result['totals']['stdout_bytes'])
        self.assertEqual(result, self.report('--full'))
        for private in [str(self.root), 'PRIVATE-ACTOR', 'PRIVATE-NODE', 'PRIVATE-MISSING-PROJECT',
                        str(PLUGIN / 'assets/example-plan.json')]:
            self.assertNotIn(private.encode(), self.db.read_bytes())
        self.assertEqual(0o600, self.db.stat().st_mode & 0o777)

    def test_update_modes_and_output_size_are_measured_from_real_cli(self):
        self.create()
        project = str(self.root / 'project')
        self.cli('take', '--project', project, '--node', 'RESEARCH-101', '--actor', 'worker')
        args = ('update', '--project', project, '--node', 'RESEARCH-101', '--actor', 'worker', '--status', 'clear')
        compact, full = self.cli(*args), self.cli(*args, '--full')
        rows = [r for r in self.report('--full')['breakdown'] if r['command'] == 'update']
        self.assertEqual(2, len(rows))
        self.assertEqual({'clear'}, {r['mode'] for r in rows})
        sizes = {r['format']: r['stdout_bytes'] for r in rows}
        self.assertEqual(len(compact.stdout.encode()), sizes['compact'])
        self.assertEqual(len(full.stdout.encode()), sizes['full'])
        self.assertLess(sizes['compact'], sizes['full'])

    def test_disabled_help_and_parser_errors_never_create_storage(self):
        self.fail(env={**self.env, 'PYRAMID_USAGE': 'off'})
        self.cli('--help')
        self.cli('inspect', '--ready', code=2)
        self.cli('inspect', '--usage', '--project', str(self.root), code=2)
        self.cli('inspect', '--usage', '--usage-days', '0', code=2)
        self.cli('inspect', '--project', str(self.root), '--usage-days', '2', code=2)
        self.assertFalse(self.storage.exists())

    def test_parallel_processes_do_not_lose_counts(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            calls = list(pool.map(lambda _: self.fail(), range(24)))
        self.assertTrue(all('usage tracking unavailable' not in r.stderr for r in calls))
        result = self.report()
        self.assertEqual(24, result['totals']['invocations'])
        self.assertEqual(24, result['totals']['failed'])
        self.assertEqual(0, result['totals']['unfinished'])

    def test_locked_storage_does_not_change_the_command_result(self):
        original = self.fail()
        lock = sqlite3.connect(self.db)
        try:
            lock.execute('BEGIN EXCLUSIVE')
            result = self.fail()
            self.assertEqual(original.stdout, result.stdout)
            self.assertIn('usage tracking unavailable', result.stderr)
        finally:
            lock.rollback()
            lock.close()
        self.assertEqual(1, self.report()['totals']['invocations'])

    def test_corrupt_or_unwritable_storage_is_visible_without_blocking_work(self):
        self.storage.mkdir()
        self.db.write_bytes(b'not a sqlite database')
        result = self.fail()
        self.assertIn('usage tracking unavailable', result.stderr)
        report = self.report(code=1)
        self.assertEqual('unavailable', report['status'])
        self.assertIsNone(report['totals'])
        self.assertEqual([], report['commands'])
        self.assertEqual(b'not a sqlite database', self.db.read_bytes())
        bad_dir = self.root / 'not-a-directory'
        bad_dir.write_text('preserve me')
        self.assertIn('usage tracking unavailable', self.fail(
            env={**self.env, 'PYRAMID_USAGE_DIR': str(bad_dir)}).stderr)
        self.assertEqual('preserve me', bad_dir.read_text())

    def test_hard_exit_remains_unfinished_not_successful(self):
        script = (
            'import argparse, os; from pyramid_usage import UsageRecorder; '
            'r=UsageRecorder.start(argparse.Namespace(command="inspect", compact=True), "test"); '
            'assert r is not None; os._exit(0)'
        )
        result = subprocess.run([sys.executable, '-B', '-c', script],
                                env={**self.env, 'PYTHONPATH': str(PLUGIN / 'scripts')},
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, self.report()['totals']['unfinished'])
        self.assertEqual(0, self.report()['totals']['succeeded'])

    def test_interruption_and_unexpected_exception_are_not_successes(self):
        for exception in (KeyboardInterrupt(), RuntimeError('injected execution failure')):
            with mock.patch.dict(os.environ, self.env), mock.patch.object(sys, 'argv', [
                'pyramid', 'inspect', '--project', str(self.root), '--summary'
            ]), mock.patch.object(pyramid, 'run', side_effect=exception), contextlib.redirect_stdout(io.StringIO()):
                if isinstance(exception, KeyboardInterrupt):
                    self.assertEqual(130, pyramid.main())
                else:
                    with self.assertRaises(RuntimeError):
                        pyramid.main()
        counts = self.report()['totals']
        self.assertEqual((2, 1, 1, 0), tuple(counts[k] for k in ('invocations', 'failed', 'interrupted', 'unfinished')))

    def test_day_filter_and_disabled_report_retain_existing_data(self):
        self.fail()
        with contextlib.closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE counts SET day='2000-01-01'")
        self.assertEqual(0, self.report('--usage-days', '1')['totals']['invocations'])
        self.assertEqual(1, self.report()['totals']['invocations'])
        disabled = json.loads(self.cli('inspect', '--usage',
                                      env={**self.env, 'PYRAMID_USAGE': 'off'}).stdout)
        self.assertFalse(disabled['collection_enabled'])
        self.assertEqual(1, disabled['totals']['invocations'])

    def test_completion_storage_failure_remains_unfinished(self):
        args = pyramid.build_parser().parse_args(['inspect', '--project', str(self.root)])
        with mock.patch.dict(os.environ, self.env):
            recorder = UsageRecorder.start(args, 'test')
        self.assertIsNotNone(recorder)
        with contextlib.closing(sqlite3.connect(self.db)) as lock:
            lock.execute('BEGIN EXCLUSIVE')
            with contextlib.redirect_stderr(io.StringIO()) as warning:
                recorder.finish(0, 42)
            self.assertIn('usage tracking unavailable', warning.getvalue())
            lock.rollback()
        self.assertEqual(1, self.report()['totals']['unfinished'])
        recorder.finish(0, 42)  # A repeated finish must not double-count.
        self.assertEqual(0, self.report()['totals']['succeeded'])

    def test_future_schema_and_invalid_counts_are_not_reported_as_zero(self):
        self.fail()
        with contextlib.closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('PRAGMA user_version=99')
        self.assertIsNone(self.report(code=1)['totals'])
        self.assertIn('usage tracking unavailable', self.fail().stderr)
        with contextlib.closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('PRAGMA user_version=1')
            connection.execute('UPDATE counts SET succeeded=999')
        self.assertIsNone(self.report(code=1)['totals'])

    def test_default_location_is_shared_and_overrides_must_be_absolute(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(Path, 'home', return_value=self.root):
            self.assertEqual(self.root / '.local/state/pyramid-task/usage.sqlite3', usage_path())
        with mock.patch.dict(os.environ, {'PYRAMID_USAGE_DIR': 'relative-path'}):
            with self.assertRaises(ValueError):
                usage_path()


if __name__ == '__main__':
    unittest.main()
