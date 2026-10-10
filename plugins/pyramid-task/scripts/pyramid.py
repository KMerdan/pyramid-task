#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pyramid_core import (
    PyramidError,
    amend_task,
    archive_project,
    assess_project,
    audit_node,
    clean_project,
    close_project,
    compile_project,
    create_project,
    expand_project,
    bind_history_commit,
    inspect_lifecycle,
    inspect_history,
    inspect_history_health,
    inspect_changes,
    inspect_project,
    impact_project,
    intent_transition_route,
    new_intent_project,
    pause_task,
    replan_project,
    repair_history,
    reopen_node,
    resume_task,
    reset_project,
    restore_project,
    take_task,
    update_task,
    validate_project,
    load_project,
)
from pyramid_live import LiveVisualizationServer
from pyramid_visualizer import render_visualization
from pyramid_output import compact_response
from pyramid_assurance_contracts import RUNTIME_VERSION
from pyramid_usage import UsageRecorder, usage_report


from pyramid_cli_options import add_project, add_version, add_scoped_guard, add_json, expected_guard
import pyramid_cli_plan as _cli_plan
import pyramid_cli_task as _cli_task
import pyramid_cli_queries as _cli_queries

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyramid", description="Pyramid Task V3 brownfield change-assurance runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    _cli_plan.add_initial_commands(sub)
    _cli_queries.add_initial_commands(sub)
    _cli_task.add_initial_commands(sub)
    _cli_task.add_amend_commands(sub)
    _cli_plan.add_replan_commands(sub)
    _cli_plan.add_expand_commands(sub)
    _cli_task.add_reopen_commands(sub)
    _cli_plan.add_lifecycle_commands(sub)
    _cli_queries.add_lifecycle_commands(sub)
    parser.set_defaults(command_catalog=tuple(sub.choices))
    return parser


def emit(data: dict[str, Any], _: bool = False) -> int:
    rendered = json.dumps(data, indent=2, ensure_ascii=False)
    print(rendered, flush=True)
    return len((rendered + "\n").encode("utf-8"))


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.command in ('create', 'new-intent', 'assess', 'impact', 'replan', 'expand', 'close', 'archive', 'reset', 'restore', 'clean'):
        return _cli_plan.run_plan(args)
    if args.command in ('take', 'pause', 'resume', 'update', 'audit', 'amend', 'reopen'):
        return _cli_task.run_task(args)
    if args.command in ('validate', 'compile', 'doctor', 'inspect', 'diff', 'lifecycle', 'history', 'visualize'):
        return _cli_queries.run_queries(args)
    raise PyramidError(f"Unsupported command: {args.command}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "inspect":
        if args.usage and args.project:
            parser.error("--usage is global; omit --project")
        if not args.usage and not args.project:
            parser.error("inspect requires --project unless --usage is selected")
        if args.usage_days is not None and (not args.usage or not 1 <= args.usage_days <= 36500):
            parser.error("--usage-days requires --usage and a value from 1 to 36500")
    recorder = UsageRecorder.start(args, RUNTIME_VERSION)
    exit_code, stdout_bytes = 1, 0
    try:
        if args.command == "visualize" and args.live:
            if args.output:
                raise PyramidError("--output cannot be combined with --live")
            server = LiveVisualizationServer(
                args.project,
                port=args.port,
                poll_interval=args.poll_interval,
            )
            stdout_bytes = emit(server.describe(), args.json)
            if args.open_browser:
                server.open_browser()
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                exit_code = 0
                return 0
            exit_code = 0
            return 0
        if args.command == "visualize" and args.open_browser:
            raise PyramidError("--open requires --live")
        data, code = run(args)
        if getattr(args, "compact", False):
            data = compact_response(data, args.command)
        stdout_bytes = emit(data, getattr(args, "json", False))
        exit_code = code
        return code
    except PyramidError as exc:
        stdout_bytes = emit({"ok": False, "error": str(exc)}, getattr(args, "json", False))
        exit_code = 2
        return 2
    except KeyboardInterrupt:
        stdout_bytes = emit({"ok": False, "error": "Interrupted"}, getattr(args, "json", False))
        exit_code = 130
        return 130
    finally:
        if recorder is not None:
            recorder.finish(exit_code, stdout_bytes)


if __name__ == "__main__":
    raise SystemExit(main())
