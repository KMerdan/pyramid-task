---
name: inspect
description: Inspect Pyramid status, readiness, evidence gaps or task details, and analyze the global command usage audit for workflow overhead. Use for command counts, usage frequency and efficiency questions; task evidence verification belongs to audit, causal intent history to history.
---

# Inspect a Pyramid Task Plan

Start with the smallest runtime query. Route cross-intent causality, path/commit provenance, and replay questions to `pyramid-task:history`. Load `../../references/demonstrable-increments.md` only for delivery or increment progress, `../../references/graph-contract.md` only for topology, `../../references/agent-contracts.md` only for one detailed node, `../../references/handoff-contract.md` only for paused work, `../../references/brownfield-assurance.md` only when assurance is present, and `../../references/lifecycle-contract.md` only for lifecycle questions.

For proof collection or reuse, query `inspect --harness <node> --json`. It returns scoped contracts, pre-run candidate templates, setup blockers and reusable runs without executing tools or writing state. Consult `../../references/development-harness.md` when interpreting or changing proof. Recorded verification in the Observer is historical; audit readiness checks the current declared inputs.

For repeated proof or broad-input cost, use `inspect --project <root> --proof-analysis <node> --json`. Add `--source-dependencies` only when source relationships inform scope review. Read `../../references/proof-analysis.md` for providers, bounds, fallback accuracy and limitations. Check uncertainty and current proof blockers; never use this projection to waive required inputs or inspections. Normal inspection does not launch the extractor.

## Inspect artifact footprint

For artifact size/retention questions, use `inspect --project <root> --footprint --json`.
It scans at most 10,000 entries and returns counts/bytes, declared classes, current
result/audit references and explicit unknowns. Use `--footprint-detail` only for
the first 100 paths, or `--footprint-limit <1-100000>` for an explicit larger/smaller
bounded scan. Check `scan.complete` and exclusions before interpreting totals.
The query does not read historical payloads, certify ownership or authorize
deletion. Unreferenced-in-current-state is not unused; failed/active/archived
evidence may still be needed. Normal queries do not run this scan.

## Analyze the usage audit

Route requests such as “analyze the Pyramid usage audit”, “which commands do we actually use?” or “check workflow overhead” here, not to `pyramid-task:audit`. For an ambiguous “audit” request, use the conversation context or ask whether the user means usage analysis or task evidence verification.

Skip the project workflow below; no `--project`, graph validation or canonical evidence reads are needed:

```bash
python3 ../../scripts/pyramid.py inspect --usage --json
# For a requested recent window:
python3 ../../scripts/pyramid.py inspect --usage --usage-days 30 --json
```

Check store status, recording dates, selected window and collection limitations first. An empty or unavailable store cannot establish that commands are unnecessary. Counts cover recorded CLI invocations on this machine, not skill invocation, internal API calls or earlier unrecorded work. `orchestrate` and `simplify` are unmeasured, not unused.

Compare invocation counts, failure/unfinished counts, stdout bytes and duration; use `--full` only when a mode/version/output-format breakdown is needed to explain a pattern. Separate measured findings from hypotheses and suggest the smallest follow-up measurement. Counts alone cannot prove duplicated work or missing workflow steps; rare recovery/safety commands can be essential. Historical counters for removed commands do not mean those commands remain available. Duration and output bytes are not model time or tokens.

Keep recommendations read-only: do not change the workflow, disable collection or remove commands from an analysis request.

## Workflow

1. Locate `<project-root>/.pyramid/plan.json`.
2. Run validation before relying on derived state:

```bash
python3 ../../scripts/pyramid.py validate --project <project-root> --json
```

3. Use the smallest query that answers the request:

```bash
python3 ../../scripts/pyramid.py inspect --project <project-root> --summary --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --ready --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --parallel-ready --max-agents 4 --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --blocked --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --pending-audits --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --audit-readiness GATE-205 --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --paused --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --node TASK-203 --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --assurance-summary --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --assurance --json
python3 ../../scripts/pyramid.py inspect --project <project-root> --assurance-detail --json
python3 ../../scripts/pyramid.py diff --project <project-root> --from-version <version> --json
python3 ../../scripts/pyramid.py lifecycle --project <project-root> --json
```

Use `--assurance-detail` only for individual assurance records and `diff --detail` only when compact changed-field summaries are insufficient. Use the returned task or audit mutation guard for scoped work; reserve the global context identity for topology, lifecycle, and full assurance mutations.

Use `--parallel-ready` when the question is which ready tasks can safely run together. Its groups are derived from the current wave, dependency, write/generated scope, asset, inspection-policy, and drift state; they are not stored graph versions. Route actual multi-agent execution through `pyramid-task:orchestrate`.

4. Explain derived facts with causes: unmet dependencies for `locked`, ownership for working tasks, handoff mode and deadline for paused tasks, failed checks, assurance blockers, stale evidence, open drift, and material findings.
5. For delivery progress, read the selected increment-ladder decision and inspect only its outcome and gate nodes. Report the last verified increment, the next gate and exact blockers, ahead-of-gate work, stale inherited proof, and remaining rungs. Do not invent a runtime increment status.
6. Distinguish `implemented` from `verified`, task readiness from assurance readiness, a wave from a demonstrable increment, and node completion from plan closure. Report labeled coverage counts, not an invented percentage.

## Boundaries

- Keep this interface read-only.
- Do not infer readiness from Markdown prose when the runtime supplies derived availability.
- Do not infer a runnable release from wave completion, batch completion, or implemented tasks.
- Do not load the entire graph when one node packet answers the request.
- Do not read every event file to explain recent changes; use the bounded diff query.
- Surface validation failures before summarizing status.
