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

## Design invariants

- `.pyramid/plan.json` is canonical topology; generated files are projections.
- `.pyramid/state.json`, `project.json`, and brownfield companions hold only current canonical state; immutable events are separate hash-linked records.
- `level` expresses distance from intent; `wave` expresses earliest safe execution.
- A worker result cannot verify its own parent outcome.
- Multi-branch composition requires an explicit joint audit.
- Failed and superseded evidence remains traceable.
- Mutations require an actor and produce immutable events.
- Global graph versions order history; task and audit guards prevent unrelated changes from becoming false conflicts.
- Readiness and audit must use the same implementation-frontier freshness rules.
- Evidence-only classification requires declared output scope; generated output requires a real baseline-asset mapping.
- Reset and restore preserve recoverable archives.
- Agent packets never expand normal authorization to files or external systems.
- Codex and Claude Code manifests ship from `main` and keep the same base release version; only the Codex manifest carries a cache-busting build suffix.

## Skill changes

Keep `SKILL.md` files concise and imperative. Put detailed contracts in `references/`, reusable deterministic behavior in `scripts/`, and output material in `assets/`. A skill folder must include matching frontmatter and `agents/openai.yaml` metadata.

Route agents to the smallest query that can answer the question. Do not instruct them to read all event files, full assurance data, or the complete graph when a frontier, selected packet, audit-readiness response, or bounded diff is sufficient.

## Documentation changes

Keep the README, published examples, schemas, skill instructions, and runtime help consistent. Documentation must distinguish canonical state, immutable history, and generated projections; distinguish global context from scoped guards; and describe refresh policies as scheduling intent rather than a waiver of audit freshness.

## Pull requests

Explain:

- the problem and intended behavior;
- why the chosen approach preserves the invariants;
- serialized or compatibility impact;
- tests and manual checks performed.

Keep changes focused. Do not commit generated project state, credentials, caches, or unrelated formatting churn.

By contributing, you agree that your contribution is licensed under the MIT License.
