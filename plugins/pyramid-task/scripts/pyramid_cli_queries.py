"""queries CLI family; existing parser order and operation branches."""
from __future__ import annotations
from pathlib import Path
from pyramid_errors import PyramidError
from pyramid_cli_options import add_json
from pyramid_cli_options import add_project
from pyramid_history_commands import bind_history_commit
from pyramid_publication import compile_project
from pyramid_queries import inspect_changes
from pyramid_queries import inspect_history
from pyramid_queries import inspect_history_health
from pyramid_project_queries import inspect_lifecycle
from pyramid_queries import inspect_project
from pyramid_project_queries import intent_transition_route
from pyramid_storage import load_project
from pyramid_visualizer import render_visualization
from pyramid_history_commands import repair_history
from pyramid_usage import usage_report
from pyramid_project_queries import validate_project

def add_initial_commands(sub):
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
    group.add_argument("--proof-analysis", metavar="NODE", help="Explain proof input overlap and reuse without changing authority")
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
    inspect.add_argument("--source-dependencies", action="store_true", help="With --proof-analysis, extract advisory JS/TS/Rust/Python dependencies")
    inspect.add_argument("--analysis-provider", choices=["auto", "python", "ast-grep"], default="python", help="Python by default without tool discovery; explicitly choose ast-grep or auto for optional AST extraction")
    inspect.add_argument("--analysis-limit", type=int, default=1000, help="Bound proof detail and source analysis to 1-10000 files")
    add_json(inspect)
    diff = sub.add_parser("diff", help="Show compact event changes between graph versions")
    add_project(diff)
    diff.add_argument("--from-version", type=int, required=True)
    diff.add_argument("--to-version", type=int)
    diff.add_argument("--detail", action="store_true", help="Include complete before, after, and payload values")
    add_json(diff)


def add_lifecycle_commands(sub):
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


def run_queries(args):
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
            if args.source_dependencies and not args.proof_analysis:
                raise PyramidError("--source-dependencies requires --proof-analysis")
            if args.analysis_provider != "python" and not args.source_dependencies:
                raise PyramidError("--analysis-provider requires --source-dependencies")
            if args.proof_analysis:
                from pyramid_proof_analysis import analyze_proofs, attach_dependencies
                paths, plan, state = load_project(args.project)
                try:
                    result = analyze_proofs(paths["root"], plan, state, args.proof_analysis, limit=args.analysis_limit)
                    if args.source_dependencies:
                        from pyramid_dependencies import LANGUAGES, analyze_dependencies
                        files = {path for proof in result["proofs"] for path in proof["files"] if Path(path).suffix in LANGUAGES}
                        result = attach_dependencies(result, analyze_dependencies(paths["root"], files, provider=args.analysis_provider, limit=args.analysis_limit))
                    return result, 0
                except ValueError as exc:
                    raise PyramidError(str(exc)) from exc
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
