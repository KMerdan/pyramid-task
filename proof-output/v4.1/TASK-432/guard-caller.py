"""Frozen reviewed caller: runtime guard is argument data, never a source literal."""
import os
import subprocess
import sys

runtime, project, guard = sys.argv[1:]
env = dict(os.environ, PYRAMID_USAGE="off", PYTHONDONTWRITEBYTECODE="1")
result = subprocess.run(
    [sys.executable, "-B", runtime, "update", "--project", project,
     "--node", "RESEARCH-101", "--actor", "guard-join", "--status", "release",
     "--expected-guard", guard, "--reason", "Owned stable-caller qualification release", "--json"],
    # The caller source is frozen before checks; authority remains invocation data.
    env=env, capture_output=True, text=True, timeout=15,
)
print(result.stdout, end="")
print(result.stderr, end="", file=sys.stderr)
raise SystemExit(result.returncode)
