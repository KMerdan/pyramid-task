"""Local CLI counters, independent of project state and agent evidence.

Store aggregate measurements only. Collection is best-effort; failures must not
change a development command's result or require broader execution permissions.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCHEMA_VERSION = 1
_LOCK_BUDGET_SECONDS = 0.5
COUNTERS = ('invocations', 'succeeded', 'failed', 'interrupted', 'duration_ms', 'stdout_bytes')
MODES = {
    'inspect': ('summary', 'ready', 'blocked', 'pending_audits', 'paused', 'assurance',
                'assurance_summary', 'assurance_detail', 'parallel_ready', 'audit_readiness',
                'harness', 'node'),
    'history': ('doctor', 'repair', 'bind', 'intent', 'path', 'commit', 'replay'),
    'visualize': ('live',),
    'resume': ('for_recovery',),
    'take': ('next', 'node'),
    'diff': ('detail',),
}


def collection_enabled() -> bool:
    return os.environ.get('PYRAMID_USAGE', 'on').lower() not in {'off', '0', 'false'}


def usage_path() -> Path:
    override = os.environ.get('PYRAMID_USAGE_DIR')
    base = Path(override).expanduser() if override else (
        Path(os.environ['XDG_STATE_HOME']).expanduser() / 'pyramid-task'
        if os.environ.get('XDG_STATE_HOME') else Path.home() / '.local/state/pyramid-task'
    )
    if not base.is_absolute():
        raise ValueError('Usage directory must be absolute')
    return base / 'usage.sqlite3'


def command_mode(args) -> str:
    # Only allowlisted option names/enum values; never persist argument values.
    if args.command == 'update' and args.status in {'implemented', 'blocked', 'at-risk', 'clear', 'release'}:
        return args.status
    for flag in ('preview', 'apply', *MODES.get(args.command, ())):
        if getattr(args, flag, False):
            return flag.replace('_', '-')
    return 'default'


def _locked(error) -> bool:
    if not isinstance(error, sqlite3.OperationalError):
        return False
    code = getattr(error, 'sqlite_errorcode', None)
    if isinstance(code, int):
        return (code & 255) in {5, 6}  # SQLite BUSY/LOCKED, including extended codes.
    # Python 3.10 does not expose sqlite_errorcode.
    return str(error).lower().startswith(('database is locked', 'database table is locked',
                                          'database schema is locked'))


def _transaction(connection, write) -> None:
    """Retry usage writes only after confirmed non-commit or rollback."""
    deadline = time.monotonic() + _LOCK_BUDGET_SECONDS
    while True:
        begun = False
        try:
            connection.execute('BEGIN IMMEDIATE')
            begun = True
            write()
            connection.commit()
            return
        except BaseException as error:
            safe_to_retry = not begun and not connection.in_transaction
            if connection.in_transaction:
                connection.rollback()
                safe_to_retry = not connection.in_transaction
            remaining = deadline - time.monotonic()
            # Never replay an increment whose commit may already have succeeded.
            if not (_locked(error) and safe_to_retry and remaining > 0):
                raise
            time.sleep(min(0.01, remaining))


def _warn(phase, error) -> None:
    reason = ('locked' if _locked(error) else 'sqlite-error' if isinstance(error, sqlite3.Error)
              else 'invalid-data' if isinstance(error, ValueError) else 'storage-error')
    code = getattr(error, 'sqlite_errorcode', None)
    code = code if isinstance(code, int) else 'unknown'
    try:
        print('Warning: Pyramid usage tracking unavailable; command behavior is unchanged. '
              f'(phase={phase}, reason={reason}, sqlite_code={code}) '
              'Use inspect --usage to check storage, or PYRAMID_USAGE=off to disable.', file=sys.stderr)
    except OSError:
        pass


def _close(connection, phase) -> None:
    if connection is not None:
        try:
            connection.close()
        except (OSError, sqlite3.Error) as error:
            _warn(phase, error)


class UsageRecorder:
    def __init__(self, connection, key):
        self.connection, self.key = connection, key
        self.started = time.perf_counter()

    @classmethod
    def start(cls, args, version: str):
        if not collection_enabled() or (args.command == 'inspect' and getattr(args, 'usage', False)):
            return None
        connection = None
        try:
            path = usage_path()
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.is_symlink():
                raise OSError('Refuse symlink usage database')
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
            # One bounded retry budget per recording phase, not per SQL statement.
            connection = sqlite3.connect(path, timeout=0)
            now = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
            key = (now[:10], version, args.command, command_mode(args),
                   'compact' if getattr(args, 'compact', True) else 'full')
            def record_start():
                schema = connection.execute('PRAGMA user_version').fetchone()[0]
                if schema not in (0, SCHEMA_VERSION):
                    raise ValueError('Unsupported usage schema')
                if schema == 0:
                    connection.execute('''CREATE TABLE IF NOT EXISTS counts (
                        day TEXT, version TEXT, command TEXT, mode TEXT, format TEXT,
                        invocations INTEGER NOT NULL DEFAULT 0,
                        succeeded INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
                        interrupted INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER NOT NULL DEFAULT 0,
                        stdout_bytes INTEGER NOT NULL DEFAULT 0, first_seen TEXT, last_seen TEXT,
                        PRIMARY KEY (day, version, command, mode, format))''')
                    connection.execute('PRAGMA user_version=1')
                connection.execute('''INSERT INTO counts
                    (day, version, command, mode, format, invocations, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(day, version, command, mode, format) DO UPDATE SET
                    invocations=invocations+1, last_seen=excluded.last_seen''', (*key, now, now))
            _transaction(connection, record_start)
            return cls(connection, key)
        except (OSError, sqlite3.Error, ValueError) as error:
            _close(connection, 'start')
            _warn('start', error)
            return None

    def finish(self, exit_code: int, stdout_bytes: int) -> None:
        connection, self.connection = self.connection, None
        if connection is None:
            return
        elapsed = max(0, round((time.perf_counter() - self.started) * 1000))
        outcome = 'succeeded' if exit_code == 0 else ('interrupted' if exit_code == 130 else 'failed')
        try:
            def record_finish():
                connection.execute(f'''UPDATE counts SET {outcome}={outcome}+1,
                    duration_ms=duration_ms+?, stdout_bytes=stdout_bytes+?
                    WHERE day=? AND version=? AND command=? AND mode=? AND format=?''',
                    (elapsed, stdout_bytes, *self.key))
            _transaction(connection, record_finish)
        except (OSError, sqlite3.Error) as error:
            _warn('finish', error)
        finally:
            _close(connection, 'finish')


def _measure(rows) -> dict:
    result = {field: sum(row[field] for row in rows) for field in COUNTERS}
    completed = result['succeeded'] + result['failed'] + result['interrupted']
    result['unfinished'] = result['invocations'] - completed
    result['average_ms'] = round(result['duration_ms'] / completed, 2) if completed else None
    return result


def _command_measure(command, rows, detail):
    measured = _measure([row for row in rows if row['command'] == command])
    if not detail and not measured['invocations']:
        return {'command': command, 'invocations': 0}
    return {'command': command, **measured}


def usage_report(commands, *, days: int | None = None, detail: bool = False) -> dict:
    if days is not None and days < 1:
        raise ValueError('usage-days must be positive')
    cutoff = ((datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
              if days is not None else None)
    rows, status, error, storage = [], 'empty', None, None
    try:
        path = usage_path()
        storage = str(path)
        if path.is_symlink():
            raise OSError('Refuse symlink usage database')
        if path.exists():
            connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.1)
            try:
                connection.row_factory = sqlite3.Row
                if connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
                    raise ValueError('Unsupported usage schema')
                rows = list(connection.execute('SELECT * FROM counts WHERE (? IS NULL OR day >= ?)',
                                               (cutoff, cutoff)))
                for row in rows:
                    if (any(not isinstance(row[field], int) or row[field] < 0 for field in COUNTERS)
                            or row['succeeded'] + row['failed'] + row['interrupted'] > row['invocations']
                            or row['format'] not in {'compact', 'full'}
                            or any(not isinstance(row[field], str) or not row[field]
                                   for field in ('day', 'version', 'command', 'mode', 'first_seen', 'last_seen'))):
                        raise ValueError('Invalid usage counters')
                status = 'available' if rows else 'empty'
            finally:
                connection.close()
    except (OSError, sqlite3.Error, ValueError) as exc:
        rows = []
        status, error = 'unavailable', f'Cannot read local usage counters ({type(exc).__name__})'
    result = {
        'schema': 'pyramid-usage-report-v1', 'status': status, 'error': error,
        'scope': 'local-user-all-projects', 'storage': storage,
        'collection_enabled': collection_enabled(),
        'window': {'days': days, 'from_utc': cutoff},
        'first_recorded': min((row['first_seen'] for row in rows), default=None),
        'last_recorded': max((row['last_seen'] for row in rows), default=None),
        'totals': _measure(rows) if status != 'unavailable' else None,
        'commands': [_command_measure(command, rows, detail)
                     for command in sorted(set(commands) | {r['command'] for r in rows})]
                    if status != 'unavailable' else [],
        'unmeasured_skills': ['orchestrate', 'simplify'],
        'limitations': [
            'Counts CLI calls, not skill invocations or internal Python API calls; no historical backfill.',
            'Help, argument-parser rejections, inspect --usage, disabled and failed collection are excluded.',
            'Unfinished means still running, killed, or completion recording failed; it is not a failure verdict.',
            'Machine-local, best-effort coverage only; the query does not test storage write permission.',
            'Duration is CLI wall time (including live-server lifetime), not agent work or model latency.',
            'Stdout bytes are not tokens or proof of useful work; low usage alone does not prove redundancy.',
        ],
    }
    if detail:
        groups = sorted({(r['command'], r['mode'], r['format'], r['version']) for r in rows})
        result['breakdown'] = [
            {'command': c, 'mode': m, 'format': f, 'version': v,
             **_measure([r for r in rows if (r['command'], r['mode'], r['format'], r['version']) == (c, m, f, v)])}
            for c, m, f, v in groups
        ]
    return result
