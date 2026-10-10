# Skill decision evaluation

This maintenance suite supplements runtime tests. It does not run on customer
tasks and is not shipped as skill workflow instructions. `cases.json` contains
12 synthetic routing/decision cases and semantic rubrics. Expected answers are
not included in the model prompt. No canonical project or customer source is
sent to the evaluator.

The current case set is v2: the no-helper cases explicitly permit `none`/`serial`
aliases, and helper cases permit orchestrate's existing intra-task route. The
first in-session v1 run retained its original, narrower field checks; do not
reinterpret those frozen scores as a v2 run or claim an improvement from changing
the answer key. Semantic reviews and literal field matches remain separate.

Run one fresh, serial Claude Code session against a disposable copy:

Model-backed runs send the selected copied skill text and synthetic case to
Claude. Obtain authorization for that destination and payload before running;
`make check` performs only local tests and never invokes this runner.

```bash
python3 -B tools/eval_skill_guidance.py --case helper-preflight --output /tmp/pyramid-eval-candidate-01
python3 -B tools/eval_skill_guidance.py --case helper-preflight --before /absolute/path/to/before.json --output /tmp/pyramid-eval-before-01
```

The source copy, request/schema hashes, exact host version, JSONL trace, elapsed
time and structured result stay in the new output directory. Only Read, Glob,
Grep and Skill are available. Commands, writes, MCP, browser integration and agent
spawning are disabled. Existing plugin installations are not changed. Do not
override these restrictions to make a case pass. The host can still contain
built-in skills: initialization records the actual discovered plugin and model.
The grader requires the candidate plugin binding and a successful native Skill
tool result, not merely a claimed skill name in the final answer.
Claude's schema response tool, StructuredOutput, is also allowed for final output.

These are native discovery and **read-only decision probes**. They cannot qualify
task claiming, implementation, actual helper dispatch/reconciliation, CLI query
execution or canonical audit acceptance. Cases requesting only analysis should
never cause those actions. Tool whitelisting establishes isolation, not a test
of whether a fully capable agent would refrain from unauthorized actions.

Review `reasoning` against each case's rubric using the trace and loaded source.
Keep semantic review separate from machine assertions and record reviewer identity.
Automated action/route fields measure reported choices; they do not prove semantic
correctness. Failed/denied reads do not count as observed reads. Missing host
credentials, network/approval failures and timeouts are environment blockers,
not skill-quality failures or successful tests. Preserve failed attempts.

Use the same runtime, prompts, host model and permissions in a before/candidate
pair. Begin with small-fix, helper-preflight and helper-candidate; expand to the
remaining near-miss cases after inspecting real failures. Repeat promising pairs
and keep later unseen cases held out. Single runs provide smoke evidence, not a
statistically reliable improvement estimate. Host-reported token counts refer to
the entire session, including system context; do not call them skill-only tokens.
Absent usage is unavailable, not zero. Codex and Claude qualification must be
recorded separately; this runner currently supports Claude only.

Run local structural checks without external models or third-party packages:

```bash
python3 -B tools/validate_skill_guidance.py
python3 -B -m unittest discover -s tools/tests -v
```

The validator intentionally accepts this repository's existing metadata profile:
flat name/description frontmatter and the three string UI fields. Unsupported
YAML forms fail closed. Extend the profile and its tests or adopt a maintained
development parser before adding nested metadata, policy or dependencies. This
does not impose a YAML dependency on installed runtime users or replace the
skill-creator's general `quick_validate.py`.
