"""Packaged viewer resources and explicit graph/render I/O; legacy exports retained."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pyramid_publication import compile_and_load_graph
from pyramid_queries import runtime_snapshot as graph_snapshot
from pyramid_state import lifecycle_status
from pyramid_storage import load_assurance_bundle, load_project
from pyramid_files import load_json, project_paths
from pyramid_observer import (
    EXECUTABLE_NODE_KINDS, _check_counts, _proof_summary, _outcome_status,
    _target_outcome, observer_projection, visualization_snapshot,
)

# Read package-relative resources once. Generated static/live pages stay self-contained.
_ASSETS = Path(__file__).resolve().parents[1] / "assets"
HTML_TEMPLATE = (_ASSETS / "observer.html").read_text(encoding="utf-8")
LIVE_SCRIPT = (_ASSETS / "live.js").read_text(encoding="utf-8")


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def load_visualization_graph(project: str | Path) -> dict[str, Any]:
    paths = project_paths(project)
    _, plan, state = load_project(project)
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if lifecycle_status(state) == "archived":
        graph = (
            load_json(paths["graph"])
            if paths["graph"].exists()
            else graph_snapshot(plan, state, baseline, assurance, manifest)
        )
    else:
        graph = compile_and_load_graph(project)
    return visualization_snapshot(graph)


def build_visualization_html(graph: dict[str, Any], *, live: bool = False) -> str:
    graph_json = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    return (
        HTML_TEMPLATE.replace("__LIVE_MODE__", "true" if live else "false")
        .replace("__LIVE_SCRIPT__", LIVE_SCRIPT if live else "")
        .replace("__GRAPH_DATA__", graph_json)
    )


def render_visualization(project: str | Path, output: str | Path | None = None) -> dict[str, Any]:
    paths = project_paths(project)
    graph = load_visualization_graph(project)
    html = build_visualization_html(graph)
    destination = Path(output).expanduser().resolve() if output else paths["html"]
    write_text_atomic(destination, html)
    return {
        "status": "rendered",
        "output": str(destination),
        "graph_version": graph["graph_version"],
        "nodes": len(graph["nodes"]),
        "views": ["observer", "history", "focus", "star", "pyramid", "dependency"],
        "overlays": ["assurance-status", "impact", "inspection", "finding", "scope-drift"],
    }
