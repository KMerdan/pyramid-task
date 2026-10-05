# Standalone Pyramid Skill — current context

Dated snapshot: 2026-10-05 in the isolated improvement worktree. This page owns repository status, not live host
installation state. Recheck Git, manifests, tests and local canonical state when
those facts matter; newer observations supersede this snapshot.

## Improvement workspace

This checkout is `dev/improvement`, based on published main `58559af`. The owner
requested A/B/C improvements and a dynamic project-aware goal-prompt skill,
dogfooding installed Pyramid 4.1 through completion and then merging locally.
The [improvement scope and candidate](docs/planning/improvement/README.md) owns
that direction. The approved transition created
`PYRAMID-DECISION-EFFICIENCY-20261005`; its ignored native state owns current
task/gate status. A/B/C and the goal prompt are implemented; final qualification
is underway. Both source manifests and runtime declare **4.2.0**, with 18 skills,
26 CLI commands and 31 schemas. Read the [qualification summary](docs/planning/improvement/qualification.md)
for actual checks and limits, not live acceptance or publication. Installed 4.1
remains the controller. No installation, push, deployment or merge is claimed
by this dated pre-closure source snapshot.
Main's pending documentation was copied and preserved, not reset or committed.

## Published baseline

Version **4.1.0** was committed and pushed to GitHub `main` as
[`58559af`](https://github.com/KMerdan/pyramid-task/commit/58559afb072f2b9acb4b4d59f3450abc99b7a50b).
That published package declared 4.1.0 and contained 17 skills, 26 CLI commands
and 31 schemas; project format remains V3.
No 4.1 Git tag was present at this check. Published source, a tagged release and
an installed plugin are separate facts.

This repository is the **Standalone Pyramid Skill**, not Hemkar Service,
Hemkar Skill or Hemkar CLI. Development and documentation work here do not
authorize operations on those separate targets.

## Completed development

The local intent `PYRAMID-41-PRECISE-PROGRESS-20261004` closed on 2026-10-04,
at canonical revision 7 and graph version 58. All 13 primary nodes passed
verification: six work tasks, three gates, three outcomes and the intent.
Its ignored `.pyramid` owns that local execution state; a fresh clone is not
expected to contain it. The portable revision-6 candidate is a planning
snapshot, not a completed-state backup or a new work queue.

[Development and evidence index](docs/planning/v4.1/README.md):

- Directional invalidation and producer-scoped proof, with explicit guarded
  compatibility bindings for intact 4.0 runs.
- Stable reviewed procedure source with fresh invocation guards passed as data.
- Bounded operational guidance and smallest complete demonstrable increments.
- Byte-identical projection write skipping, without incremental validation caches.
- Optional read-only footprint inspection and proof-input/output overlap checks.

## Qualification and limits

The recorded final qualification passed 176 tests and repository validation.
Real CLI/probe/recovery checks, isolated native Codex/Claude runs and independent
join review are indexed in the [qualification snapshot](proof-output/v4.1/TASK-432/qualification.md).
That report predates intent closure and publication; its statements about
uncommitted source and pending gates describe that earlier observation.
Do not rewrite captured evidence to reflect later events.

The native pilot did **not** establish token savings; aggregate candidate input
accounting increased on both hosts. Decision fixtures are not real product,
VM/database/browser/mail acceptance. Source qualification does not qualify a
user's installation. The existing HTTP-421 cleanup ResourceWarning remained
visible during passing tests.

Installed Codex/Claude plugins were left unchanged during development and push.
The owner chose to update them separately; their present versions are not
asserted here. Mixed 4.0/4.1 runtimes must not share an actively rebound plan.
Chronicle replay remains partial: creating a Git commit does not itself append
the separate validated code binding. No deployment, automatic cleanup, host
compaction hook or installer change is part of 4.1 or this improvement. Raw
improvement runs remain local and ignored, including failed attempts. Retain the
closed improvement worktree after merge; never overwrite main's prior canonical
state with a blind copy.

## Recheck and navigate

After the setup in [CONTRIBUTING.md](CONTRIBUTING.md), run from the repository root:

```bash
git status --short --branch
PYRAMID_USAGE=off PYTHONDONTWRITEBYTECODE=1 make check PYTHON=.venv/bin/python
```

Use the [documentation index](docs/README.md) to load only the relevant owner.
Runtime contracts live in the plugin references; historical planning and
qualification records do not grant authority or instruct agents to repeat work.
