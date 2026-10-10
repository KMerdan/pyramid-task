"""Value-only task/audit result contracts and ordered prerequisite errors.

No project, clock or command imports; inputs retain existing validation semantics.
"""
from __future__ import annotations
from typing import Any
from pyramid_graph import EXECUTABLE_KINDS, AUDIT_BLOCKING, edges_from, edges_to, node_map
from pyramid_validation import _is_string_list
from pyramid_assurance_contracts import CHANGE_CLASSES
from pyramid_changes import _classified_changes, _generated_assets_for_path, _path_matches


def _validate_agent_result(result: dict[str, Any], node: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("schema") != "agent-result-v1":
        errors.append("result.schema must be agent-result-v1")
    if result.get("task") != node["id"]:
        errors.append(f"result.task must be {node['id']}")
    if result.get("outcome") != "implemented":
        errors.append("result.outcome must be implemented")
    for field in ("changed_files", "checks", "acceptance_evidence", "discovered_risks", "suggested_graph_changes"):
        if not isinstance(result.get(field), list):
            errors.append(f"result.{field} must be an array")
    if "changed_assets" in result and not _is_string_list(result.get("changed_assets")):
        errors.append("result.changed_assets must be a string array when provided")
    change_effect = result.get("change_effect", "mixed")
    if change_effect not in {"source-change", "evidence-only", "mixed"}:
        errors.append(
            "result.change_effect must be source-change, evidence-only, or mixed when provided"
        )
    changes = result.get("changes", [])
    if not isinstance(changes, list):
        errors.append("result.changes must be an array when provided")
        changes = []
    changed_files = {
        item for item in result.get("changed_files", []) if isinstance(item, str)
    }
    classified_paths: set[str] = set()
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            errors.append(f"result.changes[{index}] must be an object")
            continue
        path = change.get("path")
        change_class = change.get("class")
        if not isinstance(path, str) or not path.strip():
            errors.append(f"result.changes[{index}].path must be non-empty")
            continue
        if path in classified_paths:
            errors.append(f"result.changes contains duplicate path {path}")
        classified_paths.add(path)
        if path not in changed_files:
            errors.append(f"result.changes path {path} is absent from changed_files")
        if change_class not in CHANGE_CLASSES:
            errors.append(f"result.changes[{index}].class is invalid")
    if changes and classified_paths != changed_files:
        errors.append("result.changes must classify every changed_files entry")

    agent_contract = node.get("agent", {})
    declared_effect = agent_contract.get("effect", "mixed")
    records = _classified_changes(result, node)
    for record in records:
        path, change_class = record["path"], record["class"]
        if change_class == "generated" and not _generated_assets_for_path(node, path):
            errors.append(
                f"Generated change {path} lacks an agent.generated_outputs declaration"
            )
        if change_class == "evidence" and not _path_matches(
            path, agent_contract.get("evidence_outputs", [])
        ):
            errors.append(
                f"Evidence change {path} is outside declared evidence output scope"
            )
    if change_effect == "evidence-only" and any(
        record["class"] != "evidence" for record in records
    ):
        errors.append("evidence-only results may contain only evidence changes")
    if declared_effect == "evidence-only" and change_effect != "evidence-only":
        errors.append("this task contract requires an evidence-only result")
    if declared_effect == "source-change" and change_effect == "evidence-only":
        errors.append("this task contract does not permit an evidence-only result")
    evidence_by_id = {
        item.get("criterion"): item
        for item in result.get("acceptance_evidence", [])
        if isinstance(item, dict)
    }
    for criterion in node["acceptance_criteria"]:
        evidence = evidence_by_id.get(criterion["id"])
        if not evidence or evidence.get("result") != "passed" or not evidence.get("reference"):
            errors.append(f"Missing passing acceptance evidence for {criterion['id']}")
    return errors


def _audit_prerequisite_errors(plan: dict[str, Any], state: dict[str, Any], node: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    item = state["nodes"][node["id"]]
    if node["kind"] in EXECUTABLE_KINDS and item["execution"] != "implemented":
        errors.append(f"{node['id']} must be implemented before audit pass")
    for edge in edges_from(plan, node["id"], AUDIT_BLOCKING | {"validated-by"}):
        if state["nodes"][edge["to"]]["verification"] != "passed":
            errors.append(f"{edge['type']} target {edge['to']} is not verified")
    if node["kind"] in {"intent", "outcome", "capability", "work-package"}:
        nodes = node_map(plan)
        for edge in edges_to(plan, node["id"], {"contributes-to"}):
            child = nodes[edge["from"]]
            if child["selection"] == "primary" and state["nodes"][child["id"]]["verification"] != "passed":
                errors.append(f"Contributing child {child['id']} is not verified")
    return errors


def _validate_audit_result(result: dict[str, Any], nid: str, expected_result: str) -> list[str]:
    errors: list[str] = []
    if result.get("schema") != "audit-result-v1":
        errors.append("audit schema must be audit-result-v1")
    if result.get("target") != nid:
        errors.append(f"audit target must be {nid}")
    if result.get("result") != expected_result:
        errors.append(f"audit result must be {expected_result}")
    checks = result.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("audit checks must be a non-empty array")
    else:
        seen = set()
        for check in checks:
            if not isinstance(check, dict):
                errors.append("each audit check must be an object")
                continue
            cid = check.get("id")
            if not isinstance(cid, str) or not cid.strip() or cid in seen:
                errors.append("audit check IDs must be non-empty and unique")
            else:
                seen.add(cid)
            if check.get("result") not in ("passed", "failed"):
                errors.append("audit check result must be passed or failed")
            refs = check.get("evidence")
            if not _is_string_list(refs) or not refs or any(not ref.strip() for ref in refs):
                errors.append("each audit check needs non-empty evidence references")
        statuses = [check.get("result") for check in checks if isinstance(check, dict)]
        if expected_result == "pass" and any(status != "passed" for status in statuses):
            errors.append("all checks must be passed for a passing audit")
        if expected_result == "fail" and "failed" not in statuses:
            errors.append("a failing audit must include a failed check")
    assertion = result.get("assurance")
    if assertion is not None:
        if not isinstance(assertion, dict):
            errors.append("audit assurance must be an object")
        else:
            for field in ("impact_ids", "inspection_ids", "finding_ids", "limitations"):
                if not _is_string_list(assertion.get(field)):
                    errors.append(f"audit assurance.{field} must be a string array")
            if assertion.get("scope_review") not in {"complete", "incomplete"}:
                errors.append("audit assurance.scope_review must be complete or incomplete")
    return errors
