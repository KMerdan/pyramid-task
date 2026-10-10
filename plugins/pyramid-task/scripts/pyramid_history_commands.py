"""Explicit history repair and code-binding effects; never implicit in queries."""
from __future__ import annotations
from pathlib import Path
from pyramid_errors import PyramidError
from pyramid_files import load_json
from pyramid_files import project_lock
from pyramid_files import project_paths
from pyramid_history import HistoryError
from pyramid_history import record_code_binding
from pyramid_history import repair_history_transaction
from pyramid_state import lifecycle_status
from typing import Any

from pyramid_queries import QueryPorts, default_ports


def repair_history(project: str | Path, *, ports: QueryPorts | None = None) -> dict[str, Any]:
    ports = ports or default_ports()
    paths = project_paths(project)
    with project_lock(paths):
        try:
            result = repair_history_transaction(paths["meta"])
        except HistoryError as exc:
            raise PyramidError(str(exc)) from exc
    validation = ports.validate_project(project)
    if not validation["valid"]:
        raise PyramidError(
            "History repair completed but project validation failed:\n- "
            + "\n- ".join(validation["errors"])
        )
    return {**result, "project_valid": True}


def bind_history_commit(
    project: str | Path,
    chronicle: str,
    actor: str,
    *,
    ports: QueryPorts | None = None,
) -> dict[str, Any]:
    ports = ports or default_ports()
    if not actor.strip():
        raise PyramidError("history code binding requires a non-empty actor")
    paths = project_paths(project)
    with project_lock(paths):
        ports.read_project(project)
        try:
            record = record_code_binding(
                paths["meta"], paths["root"], chronicle, actor
            )
        except HistoryError as exc:
            raise PyramidError(str(exc)) from exc
    if paths["plan"].exists() and lifecycle_status(load_json(paths["state"])) != "archived":
        ports.compile_project(project)
    return {
        "status": "bound",
        "chronicle_id": record["chronicle_id"],
        "commit": record["commit"],
        "tree": record.get("tree"),
        "replay_fidelity": record["replay_fidelity"],
        "record_id": record["record_id"],
    }
