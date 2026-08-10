from __future__ import annotations

import copy
import fnmatch
import hashlib
import re
from collections import defaultdict, deque
from typing import Any

from pyramid_graph import AUDIT_BLOCKING

BATCHABLE_REFRESH_POLICIES = {"per-wave", "pre-audit", "release"}
BROAD_WRITE_PATTERNS = {
    "",
    ".",
    "./",
    "..",
    "../**",
    "/",
    "*",
    "**",
    "**/*",
}


def _normalize_pattern(value: str) -> str:
    stripped = value.strip().replace("\\", "/")
    if stripped in {".", "./"}:
        return "."
    while stripped.startswith("./"):
        stripped = stripped[2:]
    return stripped.rstrip("/") or "/"


def _scope_is_broad_or_external(pattern: str) -> bool:
    normalized = _normalize_pattern(pattern)
    return (
        normalized in BROAD_WRITE_PATTERNS
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:/", normalized) is not None
        or ".." in normalized.split("/")
    )


def _static_prefix(pattern: str) -> str:
    normalized = _normalize_pattern(pattern)
    if _scope_is_broad_or_external(normalized):
        return ""
    wildcard = re.search(r"[*?[]", normalized)
    prefix = normalized[: wildcard.start()] if wildcard else normalized
    return prefix.rstrip("/")


def _prefix_contains(parent: str, child: str) -> bool:
    return not parent or child == parent or child.startswith(parent + "/")


def _patterns_overlap(left: str, right: str) -> bool:
    a = _normalize_pattern(left)
    b = _normalize_pattern(right)
    if _scope_is_broad_or_external(a) or _scope_is_broad_or_external(b):
        return True
    if fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a):
        return True
    a_prefix = _static_prefix(a)
    b_prefix = _static_prefix(b)
    return _prefix_contains(a_prefix, b_prefix) or _prefix_contains(
        b_prefix, a_prefix
    )


def _task_scopes(node: dict[str, Any]) -> list[str]:
    agent = node.get("agent", {})
    scopes = list(agent.get("allowed_write_scope", []))
    scopes.extend(agent.get("evidence_outputs", []))
    scopes.extend(
        output.get("pattern")
        for output in agent.get("generated_outputs", [])
        if isinstance(output, dict) and isinstance(output.get("pattern"), str)
    )
    return sorted({item for item in scopes if isinstance(item, str) and item.strip()})


def _scope_conflicts(
    left: dict[str, Any], right: dict[str, Any]
) -> list[str]:
    conflicts: list[str] = []
    for left_scope in _task_scopes(left):
        for right_scope in _task_scopes(right):
            if _patterns_overlap(left_scope, right_scope):
                conflicts.append(
                    f"write-scope-overlap:{left_scope}<->{right_scope}"
                )
    return sorted(set(conflicts))


def _task_assets(
    node: dict[str, Any], assurance: dict[str, Any] | None
) -> set[str]:
    if node.get("agent", {}).get("effect") == "evidence-only":
        return set()
    task = node["id"]
    assets = {
        impact.get("asset_id")
        for impact in (assurance or {}).get("impacts", [])
        if task in impact.get("task_ids", [])
        and impact.get("status") != "dismissed"
        and isinstance(impact.get("asset_id"), str)
    }
    for output in node.get("agent", {}).get("generated_outputs", []):
        if isinstance(output, dict):
            assets.update(
                asset
                for asset in output.get("asset_ids", [])
                if isinstance(asset, str)
            )
    return assets


def _inspection_relevant(
    inspection: dict[str, Any], task: str, assets: set[str]
) -> bool:
    inspection_tasks = set(inspection.get("task_ids", []))
    return bool(assets.intersection(inspection.get("asset_ids", []))) and (
        not inspection_tasks or task in inspection_tasks
    )


def _shared_inspections(
    assurance: dict[str, Any] | None,
    left: str,
    right: str,
    shared_assets: set[str],
) -> list[dict[str, Any]]:
    return [
        inspection
        for inspection in (assurance or {}).get("inspections", [])
        if _inspection_relevant(inspection, left, shared_assets)
        and _inspection_relevant(inspection, right, shared_assets)
    ]


def _dependency_index(
    plan: dict[str, Any], task_ids: set[str]
) -> tuple[
    dict[tuple[str, str], list[str]],
    dict[str, set[str]],
]:
    direct: dict[tuple[str, str], list[str]] = defaultdict(list)
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in plan.get("edges", []):
        if edge.get("type") not in AUDIT_BLOCKING:
            continue
        source = edge["from"]
        target = edge["to"]
        adjacency[source].add(target)
        if source in task_ids and target in task_ids:
            direct[tuple(sorted((source, target)))].append(
                f"dependency-coupling:{source}->{target}:{edge['type']}"
            )
    reachability: dict[str, set[str]] = {}
    for start in sorted(task_ids):
        reached: set[str] = set()
        queue = deque(sorted(adjacency.get(start, set())))
        while queue:
            current = queue.popleft()
            if current in reached:
                continue
            reached.add(current)
            queue.extend(sorted(adjacency.get(current, set())))
        reachability[start] = reached
    return (
        {pair: sorted(reasons) for pair, reasons in direct.items()},
        reachability,
    )


def _dependency_conflict(
    left: str,
    right: str,
    direct: dict[tuple[str, str], list[str]],
    reachability: dict[str, set[str]],
) -> list[str]:
    pair = tuple(sorted((left, right)))
    direct_reasons = direct.get(pair, [])
    if direct_reasons:
        return direct_reasons
    if right in reachability.get(left, set()):
        return [f"dependency-coupling:{left}~>{right}:transitive"]
    if left in reachability.get(right, set()):
        return [f"dependency-coupling:{right}~>{left}:transitive"]
    return []


def _pair_analysis(
    left: dict[str, Any],
    right: dict[str, Any],
    assurance: dict[str, Any] | None,
    task_assets: dict[str, set[str]],
    direct_dependencies: dict[tuple[str, str], list[str]],
    dependency_reachability: dict[str, set[str]],
) -> dict[str, Any]:
    reasons = _dependency_conflict(
        left["id"],
        right["id"],
        direct_dependencies,
        dependency_reachability,
    )
    reasons.extend(_scope_conflicts(left, right))
    shared_assets = task_assets[left["id"]].intersection(
        task_assets[right["id"]]
    )
    shared_inspections = _shared_inspections(
        assurance, left["id"], right["id"], shared_assets
    )
    if shared_assets:
        unsafe_assets: set[str] = set()
        for asset in shared_assets:
            covering = [
                inspection
                for inspection in shared_inspections
                if asset in inspection.get("asset_ids", [])
            ]
            if not covering or any(
                inspection.get("refresh_policy")
                not in BATCHABLE_REFRESH_POLICIES
                for inspection in covering
            ):
                unsafe_assets.add(asset)
        if unsafe_assets:
            reasons.append(
                "shared-assets-without-batch-refresh:"
                + ",".join(sorted(unsafe_assets))
            )
    return {
        "reasons": sorted(set(reasons)),
        "shared_asset_ids": sorted(shared_assets),
        "shared_inspections": sorted(
            (
                {
                    "id": inspection["id"],
                    "refresh_policy": inspection["refresh_policy"],
                }
                for inspection in shared_inspections
                if isinstance(inspection.get("id"), str)
                and inspection.get("refresh_policy")
                in BATCHABLE_REFRESH_POLICIES
            ),
            key=lambda inspection: inspection["id"],
        ),
    }


def _audit_coverage(plan: dict[str, Any], gate: str) -> set[str]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in plan.get("edges", []):
        if edge.get("type") in AUDIT_BLOCKING:
            adjacency[edge["from"]].append(edge["to"])
    covered: set[str] = set()
    queue = deque(sorted(adjacency.get(gate, [])))
    while queue:
        current = queue.popleft()
        if current in covered:
            continue
        covered.add(current)
        queue.extend(sorted(adjacency.get(current, [])))
    return covered


def _join_gate(plan: dict[str, Any], task_ids: set[str]) -> str | None:
    gates = sorted(
        (
            node
            for node in plan.get("nodes", [])
            if node.get("kind") == "audit"
            and node.get("selection") == "primary"
            and node.get("id") not in task_ids
            and task_ids.issubset(_audit_coverage(plan, node["id"]))
        ),
        key=lambda node: (node.get("wave", 0), node.get("level", 0), node["id"]),
    )
    return gates[0]["id"] if gates else None


def _task_inspection_ids(
    node: dict[str, Any],
    assets: set[str],
    assurance: dict[str, Any] | None,
) -> list[str]:
    return sorted(
        inspection["id"]
        for inspection in (assurance or {}).get("inspections", [])
        if isinstance(inspection.get("id"), str)
        and _inspection_relevant(inspection, node["id"], assets)
    )


def _task_record(
    node: dict[str, Any],
    task_guards: dict[str, str],
    assets: set[str],
    assurance: dict[str, Any] | None,
) -> dict[str, Any]:
    agent = node.get("agent", {})
    return {
        "task": node["id"],
        "title": node["title"],
        "kind": node["kind"],
        "level": node["level"],
        "wave": node["wave"],
        "workstream": node["workstream"],
        "effect": agent.get("effect", "mixed"),
        "claim_guard": task_guards[node["id"]],
        "allowed_write_scope": copy.deepcopy(
            agent.get("allowed_write_scope", [])
        ),
        "asset_ids": sorted(assets),
        "inspection_ids": _task_inspection_ids(node, assets, assurance),
    }


def _effective_refresh_boundary(policies: set[str]) -> str | None:
    if "per-wave" in policies:
        return "per-wave"
    if policies:
        return "pre-audit"
    return None


def _group_id(plan_id: str, wave: int, task_ids: list[str]) -> str:
    material = f"{plan_id}\0{wave}\0{'|'.join(task_ids)}".encode("utf-8")
    token = hashlib.sha256(material).hexdigest()[:10].upper()
    return f"PARALLEL-W{wave}-{token}"


def build_parallel_frontier(
    plan: dict[str, Any],
    candidate_ids: list[str],
    *,
    task_guards: dict[str, str],
    context: dict[str, Any],
    graph_version: int,
    max_agents: int = 4,
    assurance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive conflict-safe parallel batches without mutating canonical state."""
    if max_agents < 1:
        raise ValueError("max_agents must be positive")
    nodes = {node["id"]: node for node in plan.get("nodes", [])}
    candidates = [
        nodes[task]
        for task in sorted(set(candidate_ids))
        if task in nodes and task in task_guards
    ]
    task_assets = {
        node["id"]: _task_assets(node, assurance) for node in candidates
    }
    direct_dependencies, dependency_reachability = _dependency_index(
        plan, set(task_assets)
    )
    pair_cache: dict[tuple[str, str], dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    by_wave: dict[int, list[dict[str, Any]]] = defaultdict(list)
    task_blockers: dict[str, list[str]] = defaultdict(list)
    open_drift_tasks = {
        drift.get("task")
        for drift in (assurance or {}).get("scope_drift", [])
        if drift.get("status") == "open"
    }
    for node in candidates:
        by_wave[node["wave"]].append(node)
        broad = sorted(
            scope
            for scope in _task_scopes(node)
            if _scope_is_broad_or_external(scope)
        )
        if broad:
            task_blockers[node["id"]].append(
                "broad-write-scope:" + ",".join(broad)
            )
        if node["id"] in open_drift_tasks:
            task_blockers[node["id"]].append("open-scope-drift")
        effect = node.get("agent", {}).get("effect", "mixed")
        if effect in {"source-change", "mixed"} and not _task_scopes(node):
            task_blockers[node["id"]].append(
                "missing-write-scope-for-writing-effect"
            )
        if (
            assurance is not None
            and effect in {"source-change", "mixed"}
            and not task_assets[node["id"]]
        ):
            task_blockers[node["id"]].append("missing-impact-coverage")

    for wave, wave_nodes in sorted(by_wave.items()):
        ordered = sorted(wave_nodes, key=lambda node: (node["level"], node["id"]))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                key = tuple(sorted((left["id"], right["id"])))
                analysis = _pair_analysis(
                    left,
                    right,
                    assurance,
                    task_assets,
                    direct_dependencies,
                    dependency_reachability,
                )
                pair_cache[key] = analysis
                if analysis["reasons"]:
                    conflicts.append(
                        {
                            "tasks": [left["id"], right["id"]],
                            "wave": wave,
                            "reasons": analysis["reasons"],
                        }
                    )

    raw_groups: list[list[dict[str, Any]]] = []
    grouped_ids: set[str] = set()
    if max_agents >= 2:
        for _, wave_nodes in sorted(by_wave.items()):
            ordered = sorted(wave_nodes, key=lambda node: (node["level"], node["id"]))
            batches: list[list[dict[str, Any]]] = []
            for node in ordered:
                if task_blockers[node["id"]]:
                    continue
                placed = False
                for batch in batches:
                    if len(batch) >= max_agents:
                        continue
                    safe = True
                    for peer in batch:
                        key = tuple(sorted((node["id"], peer["id"])))
                        if pair_cache[key]["reasons"]:
                            safe = False
                            break
                    if safe:
                        batch.append(node)
                        placed = True
                        break
                if not placed:
                    batches.append([node])
            for singleton in [batch for batch in batches if len(batch) == 1]:
                lone = singleton[0]
                for donor in [batch for batch in batches if len(batch) > 2]:
                    movable = next(
                        (
                            peer
                            for peer in donor
                            if not pair_cache[
                                tuple(sorted((lone["id"], peer["id"])))
                            ]["reasons"]
                        ),
                        None,
                    )
                    if movable is not None:
                        donor.remove(movable)
                        singleton.append(movable)
                        break
            for batch in batches:
                if len(batch) >= 2:
                    raw_groups.append(batch)
                    grouped_ids.update(node["id"] for node in batch)

    groups: list[dict[str, Any]] = []
    for batch in raw_groups:
        task_ids = sorted(node["id"] for node in batch)
        shared_assets: set[str] = set()
        inspection_schedule: dict[str, str] = {}
        for index, left in enumerate(task_ids):
            for right in task_ids[index + 1 :]:
                analysis = pair_cache[(left, right)]
                shared_assets.update(analysis["shared_asset_ids"])
                inspection_schedule.update(
                    {
                        inspection["id"]: inspection["refresh_policy"]
                        for inspection in analysis["shared_inspections"]
                    }
                )
        wave = batch[0]["wave"]
        scopes = [scope for node in batch for scope in _task_scopes(node)]
        groups.append(
            {
                "id": _group_id(plan["plan_id"], wave, task_ids),
                "wave": wave,
                "levels": sorted({node["level"] for node in batch}),
                "task_ids": task_ids,
                "recommended_agents": len(task_ids),
                "recommended_subagents": len(task_ids) - 1,
                "isolation": "separate-worktrees" if scopes else "shared-read-only",
                "join_gate": _join_gate(plan, set(task_ids)),
                "shared_asset_ids": sorted(shared_assets),
                "shared_inspection_ids": sorted(inspection_schedule),
                "shared_inspections": [
                    {"id": inspection, "refresh_policy": policy}
                    for inspection, policy in sorted(
                        inspection_schedule.items()
                    )
                ],
                "effective_refresh_boundary": _effective_refresh_boundary(
                    set(inspection_schedule.values())
                ),
                "tasks": [
                    _task_record(
                        nodes[task],
                        task_guards,
                        task_assets[task],
                        assurance,
                    )
                    for task in task_ids
                ],
            }
        )

    groups.sort(
        key=lambda group: (
            group["wave"],
            -group["recommended_agents"],
            group["id"],
        )
    )

    serial_tasks: list[dict[str, Any]] = []
    for node in sorted(candidates, key=lambda item: (item["wave"], item["level"], item["id"])):
        if node["id"] in grouped_ids:
            continue
        reasons = list(task_blockers[node["id"]])
        if max_agents < 2:
            reasons.append("agent-budget-below-two")
        for conflict in conflicts:
            if node["id"] in conflict["tasks"]:
                reasons.extend(conflict["reasons"])
        if not reasons:
            reasons.append("no-parallel-safe-peer-in-wave")
        serial_tasks.append(
            {
                "task": node["id"],
                "title": node["title"],
                "wave": node["wave"],
                "reasons": sorted(set(reasons)),
            }
        )

    return {
        "schema": "pyramid-parallel-frontier-v1",
        "plan_id": plan["plan_id"],
        "graph_version": graph_version,
        "context": copy.deepcopy(context),
        "max_agents": max_agents,
        "candidate_count": len(candidates),
        "parallel_task_count": len(grouped_ids),
        "groups": groups,
        "serial_tasks": serial_tasks,
        "conflicts": conflicts,
    }
