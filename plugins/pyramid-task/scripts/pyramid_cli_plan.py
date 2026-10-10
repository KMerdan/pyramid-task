"""plan CLI family; existing parser order and operation branches."""
from __future__ import annotations
from pyramid_errors import PyramidError
from pyramid_cli_options import add_json
from pyramid_cli_options import add_project
from pyramid_cli_options import add_version
from pyramid_plan_lifecycle import archive_project
from pyramid_assurance_commands import assess_project
from pyramid_plan_lifecycle import clean_project
from pyramid_plan_commands import close_project
from pyramid_plan_commands import create_project
from pyramid_plan_commands import expand_project
from pyramid_cli_options import expected_guard
from pyramid_assurance_commands import impact_project
from pyramid_plan_lifecycle import new_intent_project
from pyramid_plan_commands import replan_project
from pyramid_plan_lifecycle import reset_project
from pyramid_plan_lifecycle import restore_project

def add_initial_commands(sub):
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


def add_replan_commands(sub):
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


def add_expand_commands(sub):
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


def add_lifecycle_commands(sub):
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


def run_plan(args):
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
    raise PyramidError(f"Unsupported command: {args.command}")
