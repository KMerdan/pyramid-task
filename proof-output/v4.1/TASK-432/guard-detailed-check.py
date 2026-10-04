"""Actual public-CLI lease renewal and stable-caller integration; owned fixture only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[3]
runtime = repo / "plugins/pyramid-task/scripts/pyramid.py"
caller = Path(__file__).with_name("guard-caller.py")
env = dict(os.environ, PYRAMID_USAGE="off", PYTHONDONTWRITEBYTECODE="1")
records = []
def cli(project, *args):
    done = subprocess.run([sys.executable, "-B", str(runtime), args[0], "--project",
                           str(project), *args[1:], "--json"],
                          env=env, capture_output=True, text=True, timeout=20)
    payload = json.loads(done.stdout)
    records.append({"operation": args[0], "args": list(args), "runtime":"4.1.0-candidate",
                    "exit_code": done.returncode, "result": payload})
    assert done.returncode == 0, done.stdout + done.stderr
    return payload

with tempfile.TemporaryDirectory(prefix="pyramid41-guard-") as temp:
    project = Path(temp) / "project"
    cli(project, "create", "--plan", str(repo / "plugins/pyramid-task/assets/example-plan.json"),
        "--actor", "guard-join")
    taken = cli(project, "take", "--node", "RESEARCH-101", "--actor", "guard-join")
    old_guard = taken["packet"]["mutation_guard"]
    old_lease = taken["packet"]["lease_expires_at"]
    draft = {"schema": "pyramid-handoff-draft-v1",
        "summary": "Owned disposable lease renewal proof; no source mutation.",
        "progress": ["Claim acquired through actual CLI."],
        "changed_files": [], "changed_assets": [], "checks": [], "decisions": [],
        "assumptions": [], "blockers": [], "risks": [],
        "next_steps": ["Resume and reconcile current guard without editing the caller."],
        "recommended_first_action": "Inspect paused frontier and resume with its canonical context.",
        "context_references": [], "external_session_refs": [], "running_resources": []}
    # Runtime-test fixture material, not a canonical write or authored guide.
    draft_path = Path(temp) / "handoff.json"
    draft_path.write_text(json.dumps(draft))
    before = hashlib.sha256(caller.read_bytes()).hexdigest()
    cli(project, "pause", "--node", "RESEARCH-101", "--actor", "guard-join",
        "--reason", "Exercise owned lease renewal", "--handoff", str(draft_path),
        "--mode", "hold", "--expected-guard", old_guard)
    paused = cli(project, "inspect", "--paused")
    resumed = cli(project, "resume", "--node", "RESEARCH-101", "--actor", "guard-join",
        "--expected-version", str(paused["graph_version"]),
        "--expected-context", paused["context"]["id"])
    new_guard = resumed["packet"]["mutation_guard"]
    assert new_guard != old_guard
    assert resumed["packet"]["lease_expires_at"] != old_lease
    for guard, expected in [(old_guard, 2), (new_guard, 0)]:
        done = subprocess.run([sys.executable, "-B", str(caller), str(runtime),
                               str(project), guard], env=env, capture_output=True,
                              text=True, timeout=20)
        records.append({"operation": "frozen-caller-release", "invocation_guard":guard,
                        "caller":str(caller), "caller_sha256":before, "exit_code": done.returncode,
                        "result": json.loads(done.stdout)})
        assert done.returncode == expected, done.stdout + done.stderr
    after = hashlib.sha256(caller.read_bytes()).hexdigest()
    assert before == after
    validation = cli(project, "validate")
    assert validation["valid"]
    print(json.dumps({"caller_sha256_before": before, "caller_sha256_after": after,
        "lease_renewed": True, "old_guard_refused": True,
        "new_guard_accepted": True, "host_permission_changed": False,
        "fixture_only": True, "cli": records}, indent=2))
