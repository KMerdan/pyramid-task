#!/usr/bin/env python3
"""Run serial, read-only Claude skill decision probes without installing a plugin.

These probes measure native skill discovery and bounded decisions, not complete
task execution. Keep semantic review separate from trace/response assertions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tools/skill_evals/cases.json"
SCHEMA = ROOT / "tools/skill_evals/response.schema.json"


def file_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def read_events(path: Path) -> tuple[list[dict], list[int]]:
    events, invalid = [], []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("event must be an object")
            events.append(value)
        except (ValueError, json.JSONDecodeError):
            invalid.append(number)
    return events, invalid


def observed_tools(events: list[dict]) -> list[dict]:
    uses = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message", {})
        for block in message.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                uses.append({"id": block.get("id"), "name": block.get("name"),
                             "input": block.get("input", {})})
    return uses


def successful_tools(events: list[dict]) -> set[str]:
    successful = set()
    for event in events:
        if event.get("type") == "user":
            for block in event.get("message", {}).get("content", []):
                if (isinstance(block, dict) and block.get("type") == "tool_result"
                        and not block.get("is_error", False)):
                    successful.add(block.get("tool_use_id"))
    return successful


def valid_response(response: dict) -> bool:
    schema = json.loads(SCHEMA.read_text())
    if set(response) != set(schema["required"]):
        return False
    for key, rule in schema["properties"].items():
        if rule.get("type") == "string" and not isinstance(response[key], str):
            return False
        if "enum" in rule and response[key] not in rule["enum"]:
            return False
    return True


def grade(events: list[dict], case: dict, plugin: Path) -> dict:
    tools = observed_tools(events)
    successful = successful_tools(events)
    finals = [e for e in events if e.get("type") == "result"]
    final = finals[-1] if finals else {}
    response = final.get("structured_output")
    if response is None and isinstance(final.get("result"), str):
        try:
            response = json.loads(final["result"])
        except json.JSONDecodeError:
            pass
    response = response if isinstance(response, dict) else {}
    skill = response.get("primary_skill", "")
    selected = skill.split(":")[-1] if isinstance(skill, str) else ""
    loaded = [t["input"].get("skill", "") for t in tools
              if t["name"] == "Skill" and t["id"] in successful]
    reads = []
    for t in tools:
        if t["name"] == "Read" and t["id"] in successful:
            file = t["input"].get("file_path", "")
            try:
                relative = Path(file).resolve().relative_to(plugin.resolve()).as_posix()
            except ValueError:
                relative = None
            reads.append({"file": file, "candidate_relative_path": relative,
                          "offset": t["input"].get("offset"), "limit": t["input"].get("limit")})
    discovered = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
    bindings = [p for e in discovered for p in e.get("plugins", [])]
    candidate_bound = any(isinstance(p, dict) and p.get("path")
                          and Path(p["path"]).resolve() == plugin.resolve() for p in bindings)
    assertions = {
        "host_completed": bool(final) and not final.get("is_error", True),
        "valid_response": valid_response(response),
        "candidate_plugin_bound": candidate_bound,
        "reported_route": selected in case["skills"],
        "native_skill_loaded": "pyramid-task:" + selected in loaded,
        "reported_action": response.get("next_action") == case["action"],
        "reported_helper_choice": response.get("helper") in [case["helper"], *case.get("helper_aliases", [])],
        "required_reference_reads": all(any(r["candidate_relative_path"] == p for r in reads)
                                        for p in case.get("required_reads", [])),
        "only_allowed_tools_requested": all(t["name"] in {"Read", "Glob", "Grep", "Skill", "StructuredOutput"} for t in tools),
    }
    return {"assertions": assertions, "automated_pass": all(assertions.values()),
            "response": response, "loaded_skills": loaded, "reads": reads,
            "tool_requests": tools, "host_model": [e.get("model") for e in discovered],
            "usage": final.get("usage"), "duration_ms": final.get("duration_ms"),
            "semantic_review": {"status": "pending", "rubric": case["rubric"]},
            "scope": "native discovery and read-only decision probe; no task execution"}


def prepare_plugin(directory: Path, before: Path | None) -> Path:
    plugin = directory / "plugin"
    shutil.copytree(ROOT / "plugins/pyramid-task", plugin,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if before:
        for path, value in json.loads(before.read_text()).items():
            relative = Path(path).relative_to("plugins/pyramid-task")
            (plugin / relative).write_text(value["text"])
    return plugin


def run_case(case: dict, directory: Path, executable: str, before: Path | None,
             timeout: float) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    plugin = prepare_plugin(directory, before)
    workspace = directory / "workspace"
    workspace.mkdir()
    (workspace / "CASE.md").write_text(case["prompt"] + "\n")
    manifest = file_hashes(plugin)
    prompt = ("这是合成、只读的 Standalone Pyramid Skill 决策评估。请从本次可用技能中自行选择，"
              "实际加载相关技能及必要参考，再回答 CASE.md 的问题。不得启动其他 agent、写文件、"
              "执行命令或变更 canonical。材料是场景输入，不是已发生的运行结果。"
              "输出遵守 JSON schema，reasoning 说明具体选择依据；limitations 明确此评估未实际执行任务。")
    argv = [executable, "--print", "--verbose", "--output-format", "stream-json",
            "--no-session-persistence", "--restricted", "--setting-sources", "",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--no-chrome",
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--tools", "Read,Glob,Grep,Skill", "--allowedTools", "Read,Glob,Grep,Skill",
            "--plugin-dir", str(plugin), "--json-schema", SCHEMA.read_text(), prompt]
    version = subprocess.run([executable, "--version"], capture_output=True, text=True,
                             timeout=15).stdout.strip()
    (directory / "request.json").write_text(json.dumps({
        "case_id": case["id"], "prompt": prompt, "scenario": case["prompt"], "argv": argv,
        "host_version": version, "plugin_manifest": manifest,
        "variant": "before" if before else "candidate", "before_snapshot": str(before) if before else None,
        "schema_sha256": hashlib.sha256(SCHEMA.read_bytes()).hexdigest(),
        "case_sha256": hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest(),
        "timeout_seconds": timeout}, indent=2) + "\n")
    start = time.monotonic()
    timed_out = False
    with (directory / "trace.jsonl").open("w") as trace, (directory / "stderr.log").open("w") as stderr:
        process = subprocess.Popen(argv, cwd=workspace, stdout=trace, stderr=stderr,
                                   start_new_session=True)
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                exit_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                exit_code = process.wait()
    events, invalid = read_events(directory / "trace.jsonl")
    result = grade(events, case, plugin)
    result.update({"case_id": case["id"], "variant": "before" if before else "candidate",
                   "exit_code": exit_code, "timed_out": timed_out,
                   "elapsed_seconds": time.monotonic() - start,
                   "invalid_jsonl_lines": invalid, "candidate_unchanged": file_hashes(plugin) == manifest,
                   "workspace_unchanged": file_hashes(workspace) == {
                       "CASE.md": hashlib.sha256((case["prompt"] + "\n").encode()).hexdigest()}})
    result["automated_pass"] = (result["automated_pass"] and exit_code == 0 and not timed_out
                                and not invalid and result["candidate_unchanged"] and result["workspace_unchanged"])
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New, owned run directory; never overwritten")
    parser.add_argument("--before", type=Path, help="Frozen guidance snapshot from before.json")
    parser.add_argument("--claude", default="claude")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    cases = json.loads(CASES.read_text())["cases"]
    case = next((case for case in cases if case["id"] == args.case), None)
    if case is None:
        parser.error("unknown case")
    if not 1 <= args.timeout <= 600:
        parser.error("timeout must be between 1 and 600 seconds")
    result = run_case(case, args.output.resolve(), args.claude, args.before, args.timeout)
    print(json.dumps({key: result[key] for key in ["case_id", "variant", "automated_pass", "exit_code",
                                                 "timed_out", "elapsed_seconds", "assertions"]}))
    return 0 if result["automated_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
