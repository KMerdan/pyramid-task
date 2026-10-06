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
)
from pyramid_live import LiveVisualizationServer
from pyramid_visualizer import render_visualization
from pyramid_output import compact_response
from pyramid_assurance import RUNTIME_VERSION
from pyramid_usage import UsageRecorder, usage_report


def add_project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True, help="Project root containing .pyramid")


def add_version(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-version", type=int, help="Reject a stale mutation")
    parser.add_argument("--expected-context", help="Reject a mutation from another plan generation or state")


def add_scoped_guard(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--expected-guard",
        help="Use a task- or audit-scoped mutation guard instead of global graph context",
    )


def add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--compact", dest="compact", action="store_true",
                        help="Use compact responses (default); retain safety information")
    output.add_argument("--full", dest="compact", action="store_false",
                        help="Return the complete command response when more decision detail is needed")
    parser.set_defaults(compact=True)


def expected_guard(args: argparse.Namespace) -> int | dict[str, Any] | None:
    context_id = getattr(args, "expected_context", None)
    graph_version = getattr(args, "expected_version", None)
    if context_id:
        return {"graph_version": graph_version, "context_id": context_id}
    return graph_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyramid",
        description="Pyramid Task V3 brownfield change-assurance runtime",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a project from a candidate plan")
    add_project(create)
    create.add_argument("--plan", required=True)
    create.add_argument("--actor", required=True)
    create.add_argument(
        "--mode",
        choices=["auto", "greenfield", "brownfield"],
        default="auto",
        help="Auto-detect existing-system work by default",
    )
    create.add_argument("--baseline", help="Optional pyramid-baseline-v1 JSON")
    create.add_argument("--assurance", help="Optional pyramid-assurance-v1 JSON")
    create.add_argument("--force", action="store_true", help="Deprecated; unsafe replacement is rejected")
    add_json(create)

    new_intent = sub.add_parser(
        "new-intent",
        help="Preview or start a new intent through the safe lifecycle transition",
    )
    add_project(new_intent)
    new_intent.add_argument("--plan", required=True)
    new_intent.add_argument("--actor", required=True)
    new_intent.add_argument("--reason", required=True)
    new_intent.add_argument(
        "--mode",
        choices=["auto", "greenfield", "brownfield"],
        default="auto",
    )
    new_intent_mode = new_intent.add_mutually_exclusive_group(required=True)
    new_intent_mode.add_argument("--preview", action="store_true")
    new_intent_mode.add_argument("--apply", action="store_true")
    new_intent.add_argument("--approved-by")
    new_intent.add_argument("--approval-reference")
    new_intent.add_argument("--approved-new-intent-sha256")
    add_version(new_intent)
    add_json(new_intent)

    assess = sub.add_parser("assess", help="Preview or apply a brownfield system baseline")
    add_project(assess)
    assess.add_argument("--baseline", required=True)
    assess.add_argument("--actor", required=True)
    assess_mode = assess.add_mutually_exclusive_group(required=True)
    assess_mode.add_argument("--preview", action="store_true")
    assess_mode.add_argument("--apply", action="store_true")
    add_version(assess)
    add_json(assess)

    impact = sub.add_parser(
        "impact",
        help="Preview or apply impact, inspection, finding, drift, and control records",
    )
    add_project(impact)
    impact.add_argument("--assurance", required=True)
    impact.add_argument("--actor", required=True)
    impact_mode = impact.add_mutually_exclusive_group(required=True)
    impact_mode.add_argument("--preview", action="store_true")
    impact_mode.add_argument("--apply", action="store_true")
    add_version(impact)
    add_json(impact)

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
    inspect.add_argument("--project", help="Project root; required except for global --usage")
    group = inspect.add_mutually_exclusive_group()
    group.add_argument("--usage", action="store_true", help="Report local cross-project CLI usage (no project required)")
    group.add_argument("--summary", action="store_true")
    group.add_argument("--ready", action="store_true")
    group.add_argument("--blocked", action="store_true")
    group.add_argument("--pending-audits", action="store_true")
    group.add_argument("--paused", action="store_true")
    group.add_argument("--assurance", action="store_true")
    group.add_argument("--assurance-summary", action="store_true")
    group.add_argument("--assurance-detail", action="store_true")
    group.add_argument(
        "--parallel-ready",
        action="store_true",
        help="Derive conflict-safe same-wave task batches for sub-agent orchestration",
    )
    group.add_argument("--audit-readiness")
    group.add_argument("--harness", help="Show scoped proof contracts, pre-run candidate templates, and reusable runs")
    group.add_argument("--node")
    group.add_argument("--footprint", action="store_true", help="Bounded read-only artifact counts, bytes and current references; never deletes")
    inspect.add_argument("--footprint-detail", action="store_true", help="With --footprint, list at most 100 files")
    inspect.add_argument("--footprint-limit", type=int, default=10000, help="With --footprint, scan at most this many entries (1-100000)")
    inspect.add_argument(
        "--max-agents",
        type=int,
        default=4,
        help="Maximum coordinator plus sub-agents in one parallel batch",
    )
    inspect.add_argument("--usage-days", type=int, help="Limit --usage to the last N UTC calendar days")
    add_json(inspect)

    diff = sub.add_parser("diff", help="Show compact event changes between graph versions")
    add_project(diff)
    diff.add_argument("--from-version", type=int, required=True)
    diff.add_argument("--to-version", type=int)
    diff.add_argument("--detail", action="store_true", help="Include complete before, after, and payload values")
    add_json(diff)

    take = sub.add_parser("take", help="Claim a ready task")
    add_project(take)
    choice = take.add_mutually_exclusive_group(required=True)
    choice.add_argument("--node")
    choice.add_argument("--next", action="store_true")
    take.add_argument("--actor", required=True)
    take.add_argument("--lease-minutes", type=int, default=120)
    add_version(take)
    add_scoped_guard(take)
    add_json(take)

    pause = sub.add_parser("pause", help="Pause an owned task with an immutable handoff record")
    add_project(pause)
    pause.add_argument("--node", required=True)
    pause.add_argument("--actor", required=True)
    pause.add_argument("--reason", required=True)
    pause.add_argument("--handoff", required=True, help="pyramid-handoff-draft-v1 JSON")
    pause.add_argument("--mode", choices=["hold", "handoff"], default="hold")
    pause.add_argument("--resume-minutes", type=int, default=60, help="Owner hold duration; ignored for handoff mode")
    add_version(pause)
    add_scoped_guard(pause)
    add_json(pause)

    resume = sub.add_parser("resume", help="Resume a paused task from its validated handoff record")
    add_project(resume)
    resume.add_argument("--node", required=True)
    resume.add_argument("--actor", required=True)
    resume.add_argument("--handoff", help="Optional active handoff ID assertion")
    resume.add_argument("--lease-minutes", type=int, default=120)
    resume.add_argument("--accept-stale", action="store_true", help="Explicitly accept graph, assurance, or worktree drift")
    resume.add_argument("--takeover", action="store_true", help="Take an expired hold owned by another actor")
    resume.add_argument("--for-recovery", action="store_true", help="Resume a blocked task for recovery without clearing its blocker or bypassing guards")
    add_version(resume)
    add_json(resume)

    update = sub.add_parser("update", help="Record a worker transition")
    add_project(update)
    update.add_argument("--node", required=True)
    update.add_argument("--actor", required=True)
    update.add_argument("--status", required=True, choices=["implemented", "blocked", "at-risk", "clear", "release"])
    update.add_argument("--reason")
    update.add_argument("--result")
    add_version(update)
    add_scoped_guard(update)
    add_json(update)

    audit = sub.add_parser("audit", help="Record an evidence-backed audit")
    add_project(audit)
    audit.add_argument("--node", required=True)
    audit.add_argument("--actor", required=True)
    audit.add_argument("--result", required=True, choices=["pass", "fail"])
    audit.add_argument("--evidence", required=True)
    add_version(audit)
    add_scoped_guard(audit)
    add_json(audit)

    amend = sub.add_parser("amend", help="Preview/apply additive file context for one owned task")
    add_project(amend)
    amend.add_argument("--proposal", required=True)
    amend.add_argument("--actor", required=True)
    mode = amend.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    amend.add_argument("--expected-amendment", help="Exact token returned by preview; required on apply")
    add_json(amend)

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

    history = sub.add_parser(
        "history",
        help="Query immutable intent chronicles or bind one to a clean Git commit",
    )
    add_project(history)
    history_query = history.add_mutually_exclusive_group()
    history_query.add_argument("--intent", help="Show the latest chronicle for a plan or chronicle ID")
    history_query.add_argument("--path", help="Find intents that declared or materially changed a path")
    history_query.add_argument("--commit", help="Find intents bound to a Git commit")
    history_query.add_argument("--replay", help="Return a read-only replay context for an intent")
    history_query.add_argument("--bind", help="Bind an intent chronicle to the current clean Git HEAD")
    history_query.add_argument(
        "--doctor", action="store_true", help="Inspect ledger integrity and pending append recovery"
    )
    history_query.add_argument(
        "--repair", action="store_true", help="Complete a valid interrupted history append"
    )
    history.add_argument("--actor", help="Required with --bind")
    add_json(history)

    visualize = sub.add_parser("visualize", help="Render an interactive browser graph")
    add_project(visualize)
    visualize.add_argument("--output")
    visualize.add_argument("--live", action="store_true", help="Serve a live view that follows validated graph publications")
    visualize.add_argument("--port", type=int, default=0, help="Live server port; 0 selects an available port")
    visualize.add_argument("--poll-interval", type=float, default=0.25, help="Seconds between publication checks")
    visualize.add_argument("--open", dest="open_browser", action="store_true", help="Open the live URL in the default browser")
    add_json(visualize)
    parser.set_defaults(command_catalog=tuple(sub.choices))
    return parser


def emit(data: dict[str, Any], _: bool = False) -> int:
    rendered = json.dumps(data, indent=2, ensure_ascii=False)
    print(rendered, flush=True)
    return len((rendered + "\n").encode("utf-8"))


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.command == "create":
        return create_project(
            args.project,
            args.plan,
            args.actor,
            args.force,
            mode=args.mode,
            baseline_path=args.baseline,
            assurance_path=args.assurance,
        ), 0
    if args.command == "new-intent":
        return new_intent_project(
            args.project,
            args.plan,
            args.actor,
            args.reason,
            mode=args.mode,
            apply=args.apply,
            approved_by=args.approved_by,
            approval_reference=args.approval_reference,
            approved_new_intent_sha256=args.approved_new_intent_sha256,
            expected_version=expected_guard(args),
        ), 0
    if args.command == "assess":
        return assess_project(
            args.project,
            args.baseline,
            args.actor,
            apply=args.apply,
            expected_version=expected_guard(args),
        ), 0
    if args.command == "impact":
        return impact_project(
            args.project,
            args.assurance,
            args.actor,
            apply=args.apply,
            expected_version=expected_guard(args),
        ), 0
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
        transition = intent_transition_route(args.project)
        if lifecycle.get("lifecycle", {}).get("status") == "archived":
            return {
                "status": "healthy",
                "validation": validation,
                "lifecycle": lifecycle,
                "intent_transition": transition,
                "compiled": None,
            }, 0
        return {
            "status": "healthy",
            "validation": validation,
            "lifecycle": lifecycle,
            "intent_transition": transition,
            "compiled": compile_project(args.project),
        }, 0
    if args.command == "inspect":
        if args.usage:
            result = usage_report(args.command_catalog, days=args.usage_days, detail=not args.compact)
            return result, 1 if result["status"] == "unavailable" else 0
        return inspect_project(
            args.project,
            summary=args.summary,
            ready=args.ready,
            blocked=args.blocked,
            pending_audits=args.pending_audits,
            paused=args.paused,
            assurance_view=args.assurance,
            assurance_summary_view=args.assurance_summary,
            assurance_detail=args.assurance_detail,
            parallel_ready=args.parallel_ready,
            max_agents=args.max_agents,
            audit_readiness=args.audit_readiness,
            harness=args.harness,
            footprint=args.footprint,
            footprint_detail=args.footprint_detail,
            footprint_limit=args.footprint_limit,
            nid=args.node,
        ), 0
    if args.command == "diff":
        return inspect_changes(
            args.project,
            args.from_version,
            args.to_version,
            detail=args.detail,
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
            expected_version=expected_guard(args),
            expected_guard=args.expected_guard,
        ), 0
    if args.command == "pause":
        return pause_task(
            args.project,
            args.node,
            args.actor,
            args.reason,
            args.handoff,
            mode=args.mode,
            resume_minutes=args.resume_minutes,
            expected_version=expected_guard(args),
            expected_guard=args.expected_guard,
        ), 0
    if args.command == "resume":
        return resume_task(
            args.project,
            args.node,
            args.actor,
            handoff_id=args.handoff,
            lease_minutes=args.lease_minutes,
            accept_stale=args.accept_stale,
            takeover=args.takeover,
            for_recovery=args.for_recovery,
            expected_version=expected_guard(args),
        ), 0
    if args.command == "update":
        return update_task(
            args.project,
            args.node,
            args.actor,
            args.status,
            reason=args.reason,
            result_path=args.result,
            expected_version=expected_guard(args),
            expected_guard=args.expected_guard,
        ), 0
    if args.command == "audit":
        return audit_node(
            args.project,
            args.node,
            args.actor,
            args.result,
            args.evidence,
            expected_version=expected_guard(args),
            expected_guard=args.expected_guard,
        ), 0
    if args.command == "replan":
        return replan_project(
            args.project,
            args.plan,
            args.actor,
            args.reason,
            apply=args.apply,
            allow_intent_change=args.allow_intent_change,
            expected_version=expected_guard(args),
        ), 0
    if args.command == "amend":
        return amend_task(
            args.project, args.proposal, args.actor,
            apply=args.apply, expected_amendment=args.expected_amendment,
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
            expected_version=expected_guard(args),
        ), 0
    if args.command == "reopen":
        return reopen_node(
            args.project,
            args.node,
            args.actor,
            args.reason,
            evidence_path=args.evidence,
            expected_version=expected_guard(args),
        ), 0
    if args.command == "close":
        return close_project(args.project, args.actor, expected_version=expected_guard(args)), 0
    if args.command == "archive":
        return archive_project(
            args.project,
            args.actor,
            args.reason,
            expected_version=expected_guard(args),
        ), 0
    if args.command == "reset":
        return reset_project(
            args.project,
            args.plan,
            args.actor,
            args.reason,
            expected_version=expected_guard(args),
        ), 0
    if args.command == "restore":
        return restore_project(
            args.project,
            args.archive,
            args.actor,
            args.reason,
            expected_version=expected_guard(args),
        ), 0
    if args.command == "clean":
        return clean_project(args.project), 0
    if args.command == "lifecycle":
        return inspect_lifecycle(args.project), 0
    if args.command == "history":
        if args.doctor:
            return inspect_history_health(args.project), 0
        if args.repair:
            return repair_history(args.project), 0
        if args.bind:
            if not args.actor:
                raise PyramidError("history --bind requires --actor")
            return bind_history_commit(args.project, args.bind, args.actor), 0
        return inspect_history(
            args.project,
            intent=args.intent,
            path=args.path,
            commit=args.commit,
            replay=args.replay,
        ), 0
    if args.command == "visualize":
        if args.live:
            raise PyramidError("Live visualization is a long-running command and must be started from the CLI")
        return render_visualization(args.project, args.output), 0
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
