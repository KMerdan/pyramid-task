from __future__ import annotations

import concurrent.futures
import contextlib
import io
import json
import os
import queue
import sqlite3
import subprocess
import sys
import tempfile
import threading
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

    def failing_cli(self, **kwargs):
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
        first, second, failure = self.create('one'), self.create('two'), self.failing_cli()
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
        self.failing_cli(env={**self.env, 'PYRAMID_USAGE': 'off'})
        self.cli('--help')
        self.cli('inspect', '--ready', code=2)
        self.cli('inspect', '--usage', '--project', str(self.root), code=2)
        self.cli('inspect', '--usage', '--usage-days', '0', code=2)
        self.cli('inspect', '--project', str(self.root), '--usage-days', '2', code=2)
        self.assertFalse(self.storage.exists())

    def test_parallel_processes_do_not_lose_counts(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            calls = list(pool.map(lambda _: self.failing_cli(), range(24)))
        diagnostics = [{'exit': r.returncode, 'stderr': r.stderr} for r in calls if r.stderr]
        self.assertTrue(all('usage tracking unavailable' not in r.stderr for r in calls), diagnostics)
        result = self.report()
        self.assertEqual(24, result['totals']['invocations'], [result['totals'], diagnostics])
        self.assertEqual(24, result['totals']['failed'], [result['totals'], diagnostics])
        self.assertEqual(0, result['totals']['unfinished'], [result['totals'], diagnostics])

    def test_warm_usage_schema_is_read_without_repeated_schema_writes(self):
        statements = []
        connect = sqlite3.connect

        def observe(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        args = pyramid.build_parser().parse_args(['inspect', '--project', str(self.root)])
        with mock.patch.dict(os.environ, self.env), mock.patch('pyramid_usage.sqlite3.connect', side_effect=observe):
            for _ in range(3):
                recorder = UsageRecorder.start(args, 'test')
                self.assertIsNotNone(recorder)
                recorder.finish(0, 42)
        sql = [s.lower().replace(' ', '') for s in statements]
        self.assertEqual(1, sum(s.startswith('createtable') for s in sql), statements)
        self.assertEqual(1, sum(s.startswith('pragmauser_version=') for s in sql), statements)
        self.assertEqual(3, self.report()['totals']['succeeded'])

    def locked_cli(self, phase, recover, command=None):
        """Real independent CLI/SQLite contention, ordered by trace barriers, not sleeps."""
        storage = self.root / (phase + str(recover))
        env = {**self.env, 'PYRAMID_USAGE_DIR': str(storage)}
        original = self.failing_cli(env=env)
        arguments = command or ['inspect', '--project', str(self.root / 'PRIVATE-MISSING-PROJECT'),
                                '--node', 'PRIVATE-NODE', '--json']
        script = r'''
import json, runpy, sqlite3, sys, time
from pathlib import Path
cli, phase, recover, arguments = sys.argv[1:]
sys.path.insert(0, str(Path(cli).parent))
import pyramid_usage
if recover == 'True':
    # IPC scheduling is not the retry-budget assertion; timeout controls use the default.
    pyramid_usage._LOCK_BUDGET_SECONDS = 5.0
seen, phase_started = False, None
def trace(frame, event, arg):
    global seen, phase_started
    if Path(frame.f_code.co_filename).name != 'pyramid_usage.py':
        return None
    if event == 'call' and frame.f_code.co_name == 'finish' and phase == 'finish':
        print('FINISH-READY', file=sys.stderr, flush=True)
        sys.stdin.readline()
    if event == 'call' and frame.f_code.co_name == phase:
        phase_started = time.monotonic()
    if event == 'return' and frame.f_code.co_name == phase and recover == 'False':
        print('PHASE-MS:' + str((time.monotonic() - phase_started) * 1000), file=sys.stderr, flush=True)
    if (event == 'exception' and not seen and recover == 'True'
            and isinstance(arg[1], sqlite3.OperationalError) and 'locked' in str(arg[1])):
        seen = True
        print('LOCK-READY', file=sys.stderr, flush=True)
        sys.stdin.readline()
    return trace
sys.settrace(trace)
sys.argv = [cli, *json.loads(arguments)]
runpy.run_path(cli, run_name='__main__')
'''
        lines, messages = [], queue.Queue()
        with contextlib.closing(sqlite3.connect(storage / 'usage.sqlite3')) as holder:
            if phase == 'start':
                holder.execute('BEGIN IMMEDIATE')
            with subprocess.Popen([sys.executable, '-B', '-c', script, str(PLUGIN / 'scripts/pyramid.py'),
                                   phase, str(recover), json.dumps(arguments)],
                                  env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) as child:
                def read_errors():
                    for line in child.stderr:
                        lines.append(line)
                        messages.put(line.rstrip())
                    messages.put(None)

                reader = threading.Thread(target=read_errors, daemon=True)
                reader.start()

                def expect(marker):
                    try:
                        observed = messages.get(timeout=15)
                    except queue.Empty:
                        self.fail(f'Timed out waiting for {marker} ({phase}); stderr={lines[-8:]}')
                    self.assertEqual(marker, observed, ''.join(lines))

                def proceed():
                    child.stdin.write('go\n')
                    child.stdin.flush()

                try:
                    if phase == 'finish':
                        expect('FINISH-READY')
                        holder.execute('BEGIN IMMEDIATE')
                        proceed()
                    if recover:
                        expect('LOCK-READY')
                        holder.rollback()
                        proceed()
                    child.wait(timeout=15)
                    output = child.stdout.read()
                finally:
                    holder.rollback()
                    if child.poll() is None:
                        child.kill()
                        child.wait()
                    reader.join(5)
                self.assertEqual(0 if command else original.returncode, child.returncode, ''.join(lines))
                if command is None:
                    self.assertEqual(original.stdout, output, ''.join(lines))
                else:
                    self.assertEqual('taken', json.loads(output)['status'])
                if not recover:
                    timings = [float(s.removeprefix('PHASE-MS:')) for s in lines if s.startswith('PHASE-MS:')]
                    self.assertEqual(1, len(timings), lines)
                    self.assertLess(timings[0], 2000, lines)
        totals = json.loads(self.cli('inspect', '--usage', '--json', env=env).stdout)['totals']
        return ''.join(lines), totals

    def test_busy_start_and_finish_retry_only_database_work_after_lock_release(self):
        for phase in ['start', 'finish']:
            with self.subTest(phase=phase):
                stderr, totals = self.locked_cli(phase, recover=True)
                self.assertNotIn('usage tracking unavailable', stderr)
                self.assertEqual(2, totals['invocations'], [totals, stderr])
                self.assertEqual(2, totals['failed'], [totals, stderr])
                self.assertEqual(0, totals['unfinished'], [totals, stderr])

    def test_busy_timeout_diagnoses_phase_and_preserves_original_cli_result(self):
        for phase in ['start', 'finish']:
            with self.subTest(phase=phase):
                stderr, totals = self.locked_cli(phase, recover=False)
                self.assertIn('phase=' + phase, stderr)
                self.assertIn('reason=locked', stderr)
                self.assertNotIn(str(self.root), stderr)
                self.assertNotIn('PRIVATE-NODE', stderr)
                self.assertEqual(1 if phase == 'start' else 2, totals['invocations'])
                self.assertEqual(0 if phase == 'start' else 1, totals['unfinished'])

    def test_completion_retry_never_reexecutes_a_successful_task_mutation(self):
        project = self.root / 'real-project'
        self.cli('create', '--project', str(project), '--plan', str(PLUGIN / 'assets/example-plan.json'),
                 '--actor', 'planner', '--mode', 'greenfield', '--json',
                 env={**self.env, 'PYRAMID_USAGE': 'off'})
        stderr, totals = self.locked_cli('finish', True,
            ['take', '--project', str(project), '--node', 'RESEARCH-101', '--actor', 'worker', '--json'])
        self.assertNotIn('usage tracking unavailable', stderr)
        self.assertEqual(2, totals['invocations'])
        self.assertEqual(1, totals['succeeded'])
        self.assertEqual(0, totals['unfinished'])
        events = [json.loads(p.read_text()) for p in (project / '.pyramid/events').glob('*.json')]
        self.assertEqual(1, sum(e['type'] == 'task.taken' for e in events), events)
        self.assertEqual(2, json.loads((project / '.pyramid/state.json').read_text())['graph_version'])

    def test_write_rollback_retries_but_uncertain_committed_increment_is_not_replayed(self):
        import pyramid_usage
        connect = sqlite3.connect
        args = pyramid.build_parser().parse_args(['inspect', '--project', str(self.root)])
        for fault in ['uncommitted-write', 'after-commit']:
            with self.subTest(fault=fault):
                class FaultConnection(sqlite3.Connection):
                    injected = False

                    def execute(connection, statement, *parameters):
                        cursor = super().execute(statement, *parameters)
                        if fault == 'uncommitted-write' and statement.lstrip().startswith('INSERT') and not connection.injected:
                            connection.injected = True
                            raise sqlite3.OperationalError('database is locked')
                        return cursor

                    def commit(connection):
                        super().commit()
                        if fault == 'after-commit' and not connection.injected:
                            connection.injected = True
                            raise sqlite3.OperationalError('database is locked')

                env = {**self.env, 'PYRAMID_USAGE_DIR': str(self.root / fault)}
                with mock.patch.dict(os.environ, env), contextlib.redirect_stderr(io.StringIO()) as warning:
                    with mock.patch.object(pyramid_usage.sqlite3, 'connect',
                                           side_effect=lambda *a, **k: connect(*a, **k, factory=FaultConnection)):
                        recorder = UsageRecorder.start(args, 'test')
                        if recorder is not None:
                            recorder.finish(0, 42)
                totals = json.loads(self.cli('inspect', '--usage', '--json', env=env).stdout)['totals']
                self.assertEqual(1, totals['invocations'], totals)
                self.assertEqual(int(fault == 'after-commit'), totals['unfinished'], totals)
                self.assertEqual(fault == 'after-commit', recorder is None)
                if fault == 'after-commit':
                    self.assertIn('phase=start', warning.getvalue())

    def test_busy_commit_rolls_back_before_retrying_the_increment(self):
        self.failing_cli()
        busy, release = threading.Event(), threading.Event()
        connect, errors, rollbacks = sqlite3.connect, [], []
        args = pyramid.build_parser().parse_args(['inspect', '--project', str(self.root)])

        class CommitProbe(sqlite3.Connection):
            def commit(connection):
                try:
                    return super().commit()
                except sqlite3.OperationalError:
                    busy.set()
                    if not release.wait(5):
                        raise RuntimeError('Commit retry barrier timed out')
                    raise

            def rollback(connection):
                super().rollback()
                rollbacks.append(True)

        def writer():
            try:
                recorder = UsageRecorder.start(args, 'test')
                if recorder is None:
                    raise RuntimeError('Usage start did not recover')
                recorder.finish(0, 42)
            except Exception as error:
                errors.append(repr(error))

        with contextlib.closing(connect(self.db)) as reader:
            reader.execute('BEGIN')
            reader.execute('SELECT * FROM counts').fetchall()
            with mock.patch.dict(os.environ, self.env), mock.patch('pyramid_usage._LOCK_BUDGET_SECONDS', 5), \
                    mock.patch('pyramid_usage.sqlite3.connect',
                               side_effect=lambda *a, **k: connect(*a, **k, factory=CommitProbe)):
                thread = threading.Thread(target=writer)
                thread.start()
                try:
                    self.assertTrue(busy.wait(5), errors)
                finally:
                    reader.rollback()
                    release.set()
                    thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertFalse(errors)
        self.assertEqual([True], rollbacks)
        self.assertEqual(2, self.report()['totals']['invocations'])
        self.assertEqual(1, self.report()['totals']['succeeded'])

    def test_locked_storage_does_not_change_the_command_result(self):
        original = self.failing_cli()
        lock = sqlite3.connect(self.db)
        try:
            lock.execute('BEGIN EXCLUSIVE')
            result = self.failing_cli()
            self.assertEqual(original.stdout, result.stdout)
            self.assertIn('usage tracking unavailable', result.stderr)
        finally:
            lock.rollback()
            lock.close()
        self.assertEqual(1, self.report()['totals']['invocations'])

    def test_corrupt_or_unwritable_storage_is_visible_without_blocking_work(self):
        self.storage.mkdir()
        self.db.write_bytes(b'not a sqlite database')
        result = self.failing_cli()
        self.assertIn('usage tracking unavailable', result.stderr)
        report = self.report(code=1)
        self.assertEqual('unavailable', report['status'])
        self.assertIsNone(report['totals'])
        self.assertEqual([], report['commands'])
        self.assertEqual(b'not a sqlite database', self.db.read_bytes())
        bad_dir = self.root / 'not-a-directory'
        bad_dir.write_text('preserve me')
        self.assertIn('usage tracking unavailable', self.failing_cli(
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
        self.failing_cli()
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
        self.failing_cli()
        with contextlib.closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('PRAGMA user_version=99')
        self.assertIsNone(self.report(code=1)['totals'])
        self.assertIn('usage tracking unavailable', self.failing_cli().stderr)
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
