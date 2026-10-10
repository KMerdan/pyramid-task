"""task CLI family; existing parser order and operation branches."""
from __future__ import annotations
from pyramid_errors import PyramidError
from pyramid_cli_options import add_json
from pyramid_cli_options import add_project
from pyramid_cli_options import add_scoped_guard
from pyramid_cli_options import add_version
from pyramid_task_commands import amend_task
from pyramid_task_commands import audit_node
from pyramid_cli_options import expected_guard
from pyramid_task_commands import pause_task
from pyramid_task_commands import reopen_node
from pyramid_task_commands import resume_task
from pyramid_task_commands import take_task
from pyramid_task_commands import update_task

def add_initial_commands(sub):
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


def add_amend_commands(sub):
    amend = sub.add_parser("amend", help="Preview/apply additive file context for one owned task")
    add_project(amend)
    amend.add_argument("--proposal", required=True)
    amend.add_argument("--actor", required=True)
    mode = amend.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    amend.add_argument("--expected-amendment", help="Exact token returned by preview; required on apply")
    add_json(amend)


def add_reopen_commands(sub):
    reopen = sub.add_parser("reopen", help="Return a verified or failed executable node to rework")
    add_project(reopen)
    reopen.add_argument("--node", required=True)
    reopen.add_argument("--actor", required=True)
    reopen.add_argument("--reason", required=True)
    reopen.add_argument("--evidence")
    add_version(reopen)
    add_json(reopen)


def run_task(args):
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
    if args.command == "amend":
            return amend_task(
                args.project, args.proposal, args.actor,
                apply=args.apply, expected_amendment=args.expected_amendment,
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
    raise PyramidError(f"Unsupported command: {args.command}")
