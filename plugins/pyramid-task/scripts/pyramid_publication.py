"""Lock-bound history-index and ready/docs/graph publication.

The graph is atomically published once, last. Named reader/clock/text-writer
parameters preserve existing compatibility test seams; defaults are concrete
lower-layer dependencies, not a generic operation/transition callback engine.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from pyramid_errors import PyramidError
from pyramid_files import project_paths, project_lock, load_json, utc_now, write_projection_text, write_projection_json
from pyramid_storage import load_project, load_assurance_bundle, implementation_frontier
from pyramid_state import lifecycle_status, context_identity
from pyramid_graph import node_map, availability
from pyramid_history import rebuild_history_index, history_summary, HistoryError
from pyramid_projection import (graph_snapshot, prepare_graph_nodes, task_summary,
    node_doc_path, render_node_markdown, render_intent_markdown, batch_documents, render_project_readme)
from pyramid_verification import render_guide


def _compile_project_locked(project: str | Path, *, allow_archived: bool = False, read_project=load_project, clock=utc_now, text_writer=write_projection_text) -> dict[str, Any]:
    paths, plan, state = read_project(project)
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    frontier = implementation_frontier(paths)
    if lifecycle_status(state) == "archived" and not allow_archived:
        raise PyramidError("Archived plans are frozen; use their existing projections or restore the plan")
    try:
        rebuild_history_index(paths["meta"])
    except HistoryError as exc:
        raise PyramidError(str(exc)) from exc
    prepared = prepare_graph_nodes(plan, state, baseline, assurance, frontier)
    snapshot = graph_snapshot(
        plan, state, baseline, assurance, manifest, frontier,
        generated_at=clock(), prepared=prepared
    )
    snapshot["history"] = history_summary(paths["meta"], plan["plan_id"])
    by_id = node_map(plan)
    for item in snapshot["nodes"]:
        item["source_path"] = str(node_doc_path(paths, by_id[item["id"]]).relative_to(paths["root"]))
    ready_packets = [
        task_summary(plan, state, node["id"], baseline, assurance, frontier)
        for node in plan["nodes"]
        if availability(plan, state, node) in {"ready", "needs-rework"}
    ]
    ready_packets.sort(key=lambda item: (item["wave"], item["level"], item["task"]))
    write_projection_json(
        paths["ready"],
        {
            "schema": "pyramid-ready-v1",
            "graph_version": state["graph_version"],
            "context": context_identity(plan, state),
            "tasks": ready_packets,
        },
        writer=text_writer,
    )

    paths["docs"].mkdir(parents=True, exist_ok=True)
    if plan.get("schema_version") == 2:
        text_writer(paths["docs"] / "DEVELOPMENT_HARNESS.md", render_guide(plan))
    for node in plan["nodes"]:
        path = node_doc_path(paths, node)
        path.parent.mkdir(parents=True, exist_ok=True)
        text_writer(path,
            render_node_markdown(
                paths, plan, state, node, baseline, assurance, frontier
            ),
        )

    text_writer(paths["docs"] / "INTENT.md", render_intent_markdown(plan))
    for path, text in batch_documents(paths, plan):
        text_writer(path, text)
    text_writer(paths["docs"] / "README.md", render_project_readme(
        paths, plan, state, snapshot, ready_packets, baseline, assurance, frontier))
    # Publish the graph last. Live readers treat its atomic replacement as proof that
    # every other generated projection for this canonical version is complete.
    write_projection_json(paths["graph"], snapshot, writer=text_writer)
    return {
        "graph": str(paths["graph"]),
        "ready": str(paths["ready"]),
        "docs": str(paths["docs"]),
        "graph_version": state["graph_version"],
        "context": context_identity(plan, state),
        "ready_count": len(ready_packets),
    }


def compile_project(project: str | Path, *, allow_archived: bool = False, read_project=load_project, clock=utc_now, text_writer=write_projection_text) -> dict[str, Any]:
    paths = project_paths(project)
    with project_lock(paths):
        return _compile_project_locked(project, allow_archived=allow_archived, read_project=read_project, clock=clock, text_writer=text_writer)


def compile_and_load_graph(project: str | Path, *, allow_archived: bool = False, read_project=load_project, clock=utc_now, text_writer=write_projection_text) -> dict[str, Any]:
    """Compile and read one projection while its canonical context is locked."""
    paths = project_paths(project)
    with project_lock(paths):
        _compile_project_locked(project, allow_archived=allow_archived, read_project=read_project, clock=clock, text_writer=text_writer)
        return load_json(paths["graph"])
