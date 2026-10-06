# Documentation index

## Start by task

| I want to… | Read |
| --- | --- |
| Understand or use Pyramid | [Repository README](../README.md) |
| Check the current version, completed work and limits | [Current context](../CONTEXT.md) |
| Install or update a host plugin | [Installation instructions](../README.md#install) |
| Develop or validate the source | [Contributing](../CONTRIBUTING.md) |
| Understand runtime ownership and module boundaries | [Architecture](architecture.md) |
| Understand outcome proof and visual feedback | [Harness contract](../plugins/pyramid-task/references/development-harness.md) |
| Trace the 4.1 decisions and actual qualification | [4.1 development index](planning/v4.1/README.md) |
| Understand A/B/C, goal prompt and 4.2 qualification | [Improvement index](planning/improvement/README.md) |
| Draft continuation without granting authority | [Goal-prompt skill](../plugins/pyramid-task/skills/goal-prompt/SKILL.md) |
| Review the next development-system intent and Exact Context requirements | [Candidate r3 planning record](planning/development-system/README.md) |

## Topic owners

- `CONTEXT.md`: dated repository status and release/installation boundaries.
- `README.md`: user entry point, commands and installation workflow.
- `architecture.md`: runtime responsibilities and module extraction direction.
- Plugin `skills/*/SKILL.md` and `references/`: agent workflows and detailed
  contracts. Scripts, schemas and tests establish actual runtime behavior.
- `CONTRIBUTING.md`: maintainer checks and evidence standards.
- `CHANGELOG.md`: versioned changes, not a live installation dashboard.

Update the owner rather than copying its full content into another page.

The improvement index owns the current decisions; its qualification summary is a
dated source observation, not installation or remote publication. Large working
runs remain local and ignored.

## Historical material and agent boundaries

`planning/v4.1/*.json`, `planning/v4.1/reviews/` and its case fixtures retain
planning inputs and reviews. `../proof-output/v4.1/` retains dated observations,
including failed and superseded attempts. Neither directory is the current
canonical task ledger, proof of a new run, or instructions to restart completed
tasks. Begin with the evidence index, not every log or trace.

User authorization and applicable `AGENTS.md` instructions govern actions.
Check code, schemas and actual results for behavior; use validated `.pyramid`
state for local execution status when present. Current topic owners explain
those facts; historical snapshots do not override them. Generated `.pyramid`
and `docs/tasks/` files are not hand-edited documentation.

Follow [repository guidance](../AGENTS.md) and [contribution checks](../CONTRIBUTING.md)
before submission. Documentation changes do not authorize plugin installation,
history mutation, deployment or another project's changes.
