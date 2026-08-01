#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pyramid_core import (
    PyramidError,
    archive_project,
    audit_node,
    clean_project,
    close_project,
    compile_project,
    create_project,
    expand_project,
    inspect_lifecycle,
    inspect_project,
    replan_project,
    reopen_node,
    reset_project,
    restore_project,
    take_task,
    update_task,
    validate_project,
)
from pyramid_visualizer import render_visualization


def add_project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True, help="Project root containing .pyramid")


def add_version(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-version", type=int, help="Reject a stale mutation")


def add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyramid", description="Pyramid Task Planner V2 runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a project from a candidate plan")
    add_project(create)
    create.add_argument("--plan", required=True)
    create.add_argument("--actor", required=True)
    create.add_argument("--force", action="store_true", help="Deprecated; unsafe replacement is rejected")
    add_json(create)

    validate = sub.add_parser("validate", help="Validate canonical plan and state")
    add_project(validate)
    add_json(validate)

    compile_cmd = sub.add_parser("compile", help="Regenerate graph, ready index, and Markdown")
    add_project(compile_cmd)
    add_json(compile_cmd)

    doctor = sub.add_parser("doctor", help="Validate and compile when valid")
    add_project(doctor)
    add_json(doctor)

    inspect = sub.add_parser("inspect", help="Query an existing project")
    add_project(inspect)
    group = inspect.add_mutually_exclusive_group()
    group.add_argument("--summary", action="store_true")
    group.add_argument("--ready", action="store_true")
    group.add_argument("--blocked", action="store_true")
    group.add_argument("--pending-audits", action="store_true")
    group.add_argument("--node")
    add_json(inspect)

    take = sub.add_parser("take", help="Claim a ready task")
    add_project(take)
    choice = take.add_mutually_exclusive_group(required=True)
    choice.add_argument("--node")
    choice.add_argument("--next", action="store_true")
    take.add_argument("--actor", required=True)
    take.add_argument("--lease-minutes", type=int, default=120)
    add_version(take)
    add_json(take)

    update = sub.add_parser("update", help="Record a worker transition")
    add_project(update)
    update.add_argument("--node", required=True)
    update.add_argument("--actor", required=True)
    update.add_argument("--status", required=True, choices=["implemented", "blocked", "at-risk", "clear", "release"])
    update.add_argument("--reason")
    update.add_argument("--result")
    add_version(update)
    add_json(update)

    audit = sub.add_parser("audit", help="Record an evidence-backed audit")
    add_project(audit)
    audit.add_argument("--node", required=True)
    audit.add_argument("--actor", required=True)
    audit.add_argument("--result", required=True, choices=["pass", "fail"])
    audit.add_argument("--evidence", required=True)
    add_version(audit)
    add_json(audit)

    replan = sub.add_parser("replan", help="Preview or apply a new topology")
    add_project(replan)
    replan.add_argument("--plan", required=True)
    replan.add_argument("--actor", required=True)
    replan.add_argument("--reason", required=True)
    mode = replan.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    replan.add_argument("--allow-intent-change", action="store_true")
    add_version(replan)
    add_json(replan)

    expand = sub.add_parser("expand", help="Preview or apply an approved task subtree")
    add_project(expand)
    expand.add_argument("--proposal", required=True)
    expand.add_argument("--actor", required=True)
    mode = expand.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    expand.add_argument("--approved-by")
    expand.add_argument("--approval-reference")
    expand.add_argument("--approved-proposal-sha256")
    add_version(expand)
    add_json(expand)

    reopen = sub.add_parser("reopen", help="Return a verified or failed executable node to rework")
    add_project(reopen)
    reopen.add_argument("--node", required=True)
    reopen.add_argument("--actor", required=True)
    reopen.add_argument("--reason", required=True)
    reopen.add_argument("--evidence")
    add_version(reopen)
    add_json(reopen)

    close = sub.add_parser("close", help="Formally complete a fully verified intent")
    add_project(close)
    close.add_argument("--actor", required=True)
    add_version(close)
    add_json(close)

    archive = sub.add_parser("archive", help="Freeze the current plan in a restorable archive")
    add_project(archive)
    archive.add_argument("--actor", required=True)
    archive.add_argument("--reason", required=True)
    add_version(archive)
    add_json(archive)

    reset = sub.add_parser("reset", help="Archive the current plan and start a new plan")
    add_project(reset)
    reset.add_argument("--plan", required=True)
    reset.add_argument("--actor", required=True)
    reset.add_argument("--reason", required=True)
    add_version(reset)
    add_json(reset)

    restore = sub.add_parser("restore", help="Restore an archived plan as the current plan")
    add_project(restore)
    restore.add_argument("--archive", required=True, help="Archive ID or archived plan ID")
    restore.add_argument("--actor", required=True)
    restore.add_argument("--reason", required=True)
    add_version(restore)
    add_json(restore)

    clean = sub.add_parser("clean", help="Regenerate derived artifacts without changing canonical history")
    add_project(clean)
    add_json(clean)

    lifecycle = sub.add_parser("lifecycle", help="Inspect plan lifecycle and available archives")
    add_project(lifecycle)
    add_json(lifecycle)

    visualize = sub.add_parser("visualize", help="Render an interactive browser graph")
    add_project(visualize)
    visualize.add_argument("--output")
    add_json(visualize)
    return parser


def emit(data: dict[str, Any], _: bool = False) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.command == "create":
        return create_project(args.project, args.plan, args.actor, args.force), 0
    if args.command == "validate":
        result = validate_project(args.project)
        return result, 0 if result["valid"] else 1
    if args.command == "compile":
        return compile_project(args.project), 0
    if args.command == "doctor":
        validation = validate_project(args.project)
        if not validation["valid"]:
            return {"status": "invalid", **validation}, 1
        lifecycle = inspect_lifecycle(args.project)
        if lifecycle.get("lifecycle", {}).get("status") == "archived":
            return {"status": "healthy", "validation": validation, "lifecycle": lifecycle, "compiled": None}, 0
        return {"status": "healthy", "validation": validation, "compiled": compile_project(args.project)}, 0
    if args.command == "inspect":
        return inspect_project(
            args.project,
            summary=args.summary,
            ready=args.ready,
            blocked=args.blocked,
            pending_audits=args.pending_audits,
            nid=args.node,
        ), 0
    if args.command == "take":
        if args.lease_minutes < 1:
            raise PyramidError("lease-minutes must be positive")
        return take_task(
            args.project,
            args.actor,
            nid=args.node,
            take_next=args.next,
            lease_minutes=args.lease_minutes,
            expected_version=args.expected_version,
        ), 0
    if args.command == "update":
        return update_task(
            args.project,
            args.node,
            args.actor,
            args.status,
            reason=args.reason,
            result_path=args.result,
            expected_version=args.expected_version,
        ), 0
    if args.command == "audit":
        return audit_node(
            args.project,
            args.node,
            args.actor,
            args.result,
            args.evidence,
            expected_version=args.expected_version,
        ), 0
    if args.command == "replan":
        return replan_project(
            args.project,
            args.plan,
            args.actor,
            args.reason,
            apply=args.apply,
            allow_intent_change=args.allow_intent_change,
            expected_version=args.expected_version,
        ), 0
    if args.command == "expand":
        return expand_project(
            args.project,
            args.proposal,
            args.actor,
            apply=args.apply,
            approved_by=args.approved_by,
            approval_reference=args.approval_reference,
            approved_proposal_sha256=args.approved_proposal_sha256,
            expected_version=args.expected_version,
        ), 0
    if args.command == "reopen":
        return reopen_node(
            args.project,
            args.node,
            args.actor,
            args.reason,
            evidence_path=args.evidence,
            expected_version=args.expected_version,
        ), 0
    if args.command == "close":
        return close_project(args.project, args.actor, expected_version=args.expected_version), 0
    if args.command == "archive":
        return archive_project(
            args.project,
            args.actor,
            args.reason,
            expected_version=args.expected_version,
        ), 0
    if args.command == "reset":
        return reset_project(
            args.project,
            args.plan,
            args.actor,
            args.reason,
            expected_version=args.expected_version,
        ), 0
    if args.command == "restore":
        return restore_project(
            args.project,
            args.archive,
            args.actor,
            args.reason,
            expected_version=args.expected_version,
        ), 0
    if args.command == "clean":
        return clean_project(args.project), 0
    if args.command == "lifecycle":
        return inspect_lifecycle(args.project), 0
    if args.command == "visualize":
        return render_visualization(args.project, args.output), 0
    raise PyramidError(f"Unsupported command: {args.command}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        data, code = run(args)
        emit(data, getattr(args, "json", False))
        return code
    except PyramidError as exc:
        emit({"ok": False, "error": str(exc)}, getattr(args, "json", False))
        return 2
    except KeyboardInterrupt:
        emit({"ok": False, "error": "Interrupted"}, getattr(args, "json", False))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
