# Contributing

Thanks for helping improve Pyramid Task. Contributions should strengthen either planning quality, deterministic correctness, interoperability, or human legibility without weakening evidence requirements.

## Before opening a pull request

1. Open an issue for substantial behavioral or schema changes.
2. Fork the repository and create a focused branch.
3. Keep agent reasoning in `SKILL.md` and references; keep fragile state transitions and validation in Python.
4. Add tests for behavior changes and schemas for serialized contracts.
5. Run the complete check suite.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
make check
```

## Test scope and evidence

- Runtime and CLI tests create isolated projects and exercise real files, guards, events, state transitions, proof hashes, artifact imports and recovery paths. Efficiency tests verify that compact output preserves safety data and full records remain recoverable.
- Usage tests run real multi-project and concurrent CLI processes against temporary databases. Other CLI fixtures explicitly disable collection. Keep developer/test calls out of real user counters (`PYRAMID_USAGE=off`); fault-injected execution exceptions test accounting, not product outcomes.
- Legacy-removal tests use serialized format fixtures and real CLI/API calls to verify rejection without file changes, removed command/flag handling, and continued support for existing V3 migration provenance. They do not simulate successful migrations.
- Most harness tests supply synthetic observations to test evidence contracts. Their `passed` fixture values are not actual project tests or model reviews. The executed-probe integration test separately runs a real subprocess, derives failure/success from its exit and output, rejects failed completion, records the failure, repairs the input and verifies publication and audit through the CLI.
- Targeted mocks inject ownership/conflict states, clock expiry or I/O failures; they do not replace the amendment validator or force a passing result. The concurrent-update projection test constructs an intervening mutation deterministically; it is not a scheduling stress test.
- The image fixture tests artifact-format requirements, not browser capture or visual judgment. No suite certifies screenshot interpretation, agent planning quality, real-product acceptance, host compaction, or end-to-end token/latency savings. Those require relevant real observations or separately scoped evaluations.

Keep contract fixtures for fast negative-path coverage, and use executed integration tests where behavior crosses a process or persistence boundary. Do not label synthetic evidence as performed product validation or duplicate checks without a distinct failure mode.

## Design invariants

- `.pyramid/plan.json` is canonical topology; generated files are projections.
- `.pyramid/state.json`, `project.json`, and brownfield companions hold only current canonical state; immutable events are separate hash-linked records.
- `level` expresses distance from intent; `wave` expresses earliest safe execution.
- Parallel groups are derived, read-only projections. Same-wave is required, while dependency, scope, generated output, asset, assurance, and drift checks decide actual safety.
- A worker result cannot verify its own parent outcome.
- Multi-branch composition requires an explicit joint audit.
- Failed and superseded evidence remains traceable.
- Mutations require an actor and produce immutable events.
- Global graph versions order history; task and audit guards prevent unrelated changes from becoming false conflicts.
- Readiness and audit must use the same implementation-frontier freshness rules.
- Evidence-only classification requires declared output scope; generated output requires a real baseline-asset mapping.
- Reset and restore preserve recoverable archives.
- Existing project operations and restore sources require V3 format; do not reintroduce implicit V2/V2.1 migration. Keep historical provenance intact and distinguish project format from plan schema version.
- Agent packets never expand normal authorization to files or external systems.
- Codex and Claude Code manifests ship from `main` and keep the same base release version; only the Codex manifest may carry a cache-busting build suffix.
- Pure domain modules do not import `pyramid_core`. The facade preserves compatibility exports and named clock/fault adapters; storage and publication modules own locks, guarded commits, events, and projections. Use the [runtime navigation](docs/runtime-navigation.md) to find the implementation and matching checks.

## Skill changes

Keep `SKILL.md` files concise and imperative. Put detailed contracts in `references/`, reusable deterministic behavior in `scripts/`, and output material in `assets/`. A skill folder must include matching frontmatter and `agents/openai.yaml` metadata.

Route agents to the smallest query that can answer the question. Do not instruct them to read all event files, full assurance data, or the complete graph when a frontier, selected packet, audit-readiness response, or bounded diff is sufficient.

For multi-agent work, give each worker only the selected task packet. Keep topology, lifecycle, shared assurance refreshes, and join audits with one coordinator.

## Documentation changes

Keep the README, published examples, schemas, skill instructions, and runtime help consistent. Documentation must distinguish canonical state, immutable history, and generated projections; distinguish global context from scoped guards; and describe refresh policies as scheduling intent rather than a waiver of audit freshness.

`make check` includes runtime tests and the stdlib-only guidance/trace-grader tests in `tools/tests`. Model-backed evaluation is optional and separately authorized; ordinary checks do not invoke a model service. Read [the evaluation guide](tools/skill_evals/README.md) before using that runner.

## Pull requests

Explain:

- the problem and intended behavior;
- why the chosen approach preserves the invariants;
- serialized or compatibility impact;
- tests and manual checks performed.

Keep changes focused. Do not commit generated project state, credentials, caches, or unrelated formatting churn.

By contributing, you agree that your contribution is licensed under the MIT License.
