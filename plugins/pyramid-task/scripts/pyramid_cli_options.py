"""Shared CLI argument and guard adapters."""
from __future__ import annotations
import argparse
from typing import Any

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
