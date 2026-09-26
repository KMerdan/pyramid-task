"""Strict additive amendment preparation; no persistence or agent reasoning."""
from __future__ import annotations

import copy
from pathlib import PurePosixPath
from typing import Any


def prepare_amendment(plan: dict[str, Any], proposal: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[str]]]:
    fields = {"schema", "task", "reason", "boundary_review", "add_write_paths", "add_context_paths"}
    if not isinstance(proposal, dict) or set(proposal) != fields or proposal.get("schema") != "pyramid-amendment-v1":
        raise ValueError("Amendment must match pyramid-amendment-v1; semantic fields require replan")
    for field in ("task", "reason", "boundary_review"):
        if not isinstance(proposal[field], str) or not proposal[field].strip():
            raise ValueError(f"Amendment {field} must be non-empty")
    additions = {}
    for field, target in (("add_write_paths", "allowed_write_scope"), ("add_context_paths", "required_context")):
        values = proposal[field]
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError(f"{field} must be a list of exact repository-relative file paths")
        if len(set(values)) != len(values):
            raise ValueError(f"{field} contains duplicate paths")
        for value in values:
            path = PurePosixPath(value)
            if (not value or value != str(path) or path.is_absolute()
                    or any(part in {".", "..", ".git", ".pyramid"} for part in path.parts)
                    or any(char in value for char in "*?[]\\:\n\r")
                    or value.startswith("docs/tasks/") or value != value.strip()):
                raise ValueError(f"Unsafe or non-exact amendment path: {value!r}")
        additions[target] = list(values)
    candidate = copy.deepcopy(plan)
    node = next((node for node in candidate["nodes"] if node["id"] == proposal["task"]), None)
    if node is None:
        raise ValueError(f"Unknown task: {proposal['task']}")
    for field, values in additions.items():
        if set(values).intersection(node["agent"][field]):
            raise ValueError(f"{field} already contains a requested path")
        node["agent"][field].extend(values)
    if not any(additions.values()):
        raise ValueError("Amendment has no additions")
    candidate["revision"] = plan["revision"] + 1
    return candidate, additions
