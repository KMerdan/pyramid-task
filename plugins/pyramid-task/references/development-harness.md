# Outcome-scoped development harness

Use this contract when planning or changing proof, setting up a missing probe, collecting evidence, or recovering stale evidence. The harness grows with the current outcome, not with a tool checklist. `plan.json` owns it; `docs/tasks/DEVELOPMENT_HARNESS.md` and task packets are generated views. Do not maintain a second handwritten acceptance guide in `CLAUDE.md` or `AGENTS.md`; link to the generated view if useful.

## Plan the smallest sufficient proof

1. Inspect the actual project phase, existing tests, launch commands, browser tools, data fixtures, logs and probes. Identify the claims and failure modes of the next outcome, including inherited behavior it can affect.
2. Map those claims to existing procedures first. One well-chosen run may cover several criteria, tasks, an outcome and an inspection. Do not add a unit, integration, browser and visual-regression test for the same claim by default. Different observations of one run are not separate test suites.
3. Choose external, internal and visual observations by the claim. Inspect relevant internal invariants—not every variable or table. A visible interface normally needs a real rendered capture and model inspection; API/DB success alone cannot establish layout, clipping, readability, overlays or error presentation. A documentation/layout outcome may also need visual inspection. Explain genuinely inapplicable channels rather than forcing a fake UI onto a headless outcome.
4. Reuse the available project-fit browser path: host browser tooling, Chrome DevTools MCP, existing Playwright, or another suitable capture mechanism. Do not install all of them or require a baseline pixel-diff suite. A screenshot must show the intended route, viewport, fixture and candidate; the agent must actually open/view it and record what it observed. DOM text or a saved image's existence is not visual review.
5. Add only missing capability: for example an existing test fixture, a read-only debug probe, a stable local launch command, or one capture procedure. Represent real setup work using existing implementation/contract/integration nodes, or a bounded deliverable of an existing task. If shared or prerequisite setup needs a separate task, make the acceptance gate depend on it. Product work that does not need that capability can proceed in parallel. Setup must be runnable before collecting acceptance proof, not merely described in Markdown.
6. Keep write scope and generated/evidence outputs explicit. Prefer a project-relative evidence staging directory outside `.pyramid/`, generated `docs/tasks/`, and source inputs. Do not classify source, tests, fixtures or configuration as evidence outputs to suppress invalidation. Probe setup must use safe fixtures and avoid exposing credentials or production data.

## Canonical contract: plan schema 2

New plans use `schema_version: 2`; project format remains V3 and state schema remains 1. Every primary acceptance criterion must be covered by a `required_evidence[].verification` entry. Prefer one procedure covering several criteria when it is sufficient:

```json
{
  "id": "EV-SIGNUP",
  "type": "browser-scenario",
  "description": "Signup renders correctly and persists one valid account",
  "verification": {
    "criteria": ["AC-SIGNUP-01", "AC-SIGNUP-02"],
    "method": "browser",
    "procedure": "Use the existing local signup fixture; submit a new account, query its test DB record, and capture and inspect desktop and narrow-screen success/error states. Reuse scripts/check-signup if available; establish it only if needed.",
    "inputs": ["src/**/*.ts", "src/**/*.tsx", "tests/signup/**", "package-lock.json", "config/test-env.json"],
    "observations": ["external", "internal", "visual"],
    "not_applicable": {},
    "environment": "Local test server built from this candidate; isolated signup fixture; record route, viewport and build identity in evidence"
  }
}
```

This is a shape example, not a command or a mandatory stack. Select existing patterns that match the actual repository; every declared input pattern must match files before collection. Include the procedure implementation, behavior-affecting dependencies, fixtures and environment configuration. A `review` may have no repository inputs only for a genuinely non-repository claim; retain the inspected source as an artifact. `method` is `command`, `browser` or `review`; it does not launch a tool automatically.

A gate or parent that needs the **same proof**, not another test execution, declares:

```json
{"criteria": ["AC-OUTCOME-01"], "reuse": "TASK-SIGNUP/EV-SIGNUP"}
```

Reuse must establish the consumer's actual criterion. New composition, safety or release claims still need their own observation. Reuse references must resolve to a primary requirement and cannot cycle. Separate unrelated proof families to avoid unnecessarily broad invalidation.

## Collect and submit

1. Read the task packet and use `inspect --harness <node> --json` (with the normal `--project` argument). It returns only that node's contracts, pre-run candidate templates, setup blockers and reusable run references. Prefer a currently valid reusable run when it proves the claim; do not rerun a test solely because another node owns acceptance.
   A compact node packet may contain summary-only harness detail, not a run template. Compact `--harness` retains complete templates; use `--full` when omitted contract detail is needed. A health-only update with a current packet does not require this query or another run.
2. Capture the template **before** running checks. Resolve any setup blocker, launch/rebuild the actual candidate, perform the procedure, and observe all required channels. For browser or external state, verify the server/build and fixture identity; a repository hash alone does not identify a remote process or database. Record relevant identity in artifacts and observations. A read-only helper can execute or review against an isolated immutable candidate, subject to `intra-task-helpers.md`; revalidate the candidate on join before promoting its result.
3. Fill each observation with `result: "passed"`, a concrete `summary`, the actual `reviewer` (agent/tool identity), and artifact objects containing a project-relative `path` and the file's `sha256`. The template's `not-run` observations cannot pass. Visual observations require a PNG, JPEG or WebP capture **and actual model review**. Use bounded reports, never raw secrets or unbounded logs. Limits are 16 MiB per artifact, 16 artifacts per observation, 32 MiB per run.
4. Add the resulting template under `proofs` in the normal `agent-result-v1` or `audit-result-v1`. Or use a returned `{"requirement":"EV-ID","reuse_run":"RUN-..."}` reference. The runtime generates check/criterion summaries when omitted or empty; supplied failed checks are never replaced by passing ones. The remaining result fields and brownfield assurance assertion are unchanged. An executable task's passing audit may omit `proofs` to revalidate its last implementation proof; a parent with no implementation submits explicit proof/reuse references.
5. Stage artifacts outside canonical storage. The normal guarded update/audit ingests them into content-addressed `.pyramid/reports/proof-artifacts/`, deduplicates bytes, and publishes paths with the existing event/head boundary. Do not copy evidence into that directory yourself. Normal task packets carry contracts, not logs, images, historical runs or the full guide.
6. Before audit, use `inspect --audit-readiness <node>`. Missing submitted proof is a blocker, not a demand to repeat a run: query `--harness` for reusable proof. Audit rechecks candidate fingerprints and related prerequisite evidence; closure does the same for all primary claims. Graph mutation guards and source fingerprints have different jobs; retain both.

`RUN-...` identifies observation content, not a process-execution attestation. Hashes establish declared input/artifact identity, not test quality, honest tool execution or unchanged external state. The agent must substantiate those claims. Never claim that the runtime independently judged an image. If environmental state can change independently, capture it through a reproducible local fixture/manifest, refresh that manifest before reuse, and re-observe when identity is uncertain.

## Evolve, recover and retire

Keep fresh task/audit authority outside reviewed procedure source; follow the
two-identity recipe in `agent-contracts.md`. Renewed authority does not alter the
source fingerprint, grant host permission or certify an older observation.

| Transition | Required behavior |
| --- | --- |
| Create / new intent | Design schema-2 proof with the current outcomes; no speculative future harness |
| Take / implement | Establish missing capability before acceptance; implement independent work concurrently where safe |
| Update / audit | Check source identity, actual observations and artifacts; reuse valid proof rather than duplicating tests |
| Replan / expand | Preserve stable IDs and useful capabilities; change only affected contracts; update generated guide through compilation |
| Pause / resume | Preserve commands, fixture/process references, partial evidence and cleanup ownership in the existing handoff; recapture current inputs on resume; a live process is not durable proof |
| Reopen / failure | Preserve failed observations and history; repair or replan the affected claim; do not weaken acceptance to pass |
| Close | All primary proof must still match current declared inputs; retain residual limits and meaningful human decisions |
| Archive / reset / restore | Proof artifacts follow existing report snapshots; restore evidence history, not confidence in a different working tree; rerun readiness |

Replanning invalidates changed claims, shared proof families, and old/new dependent ancestors while preserving implementation records and unaffected branches. Candidate hashes exclude graph counters and timestamps; unrelated updates do not invalidate proof. Source/dependency changes inside a declared scope do. Evidence-only reports remain excluded from implementation invalidation and must not be verification inputs.

In 4.1, proof identity covers the producer's contract and relevant prerequisites,
not every incoming consumer. Adding a consumer can preserve unchanged producer
proof; the consumer and changed parent composition still need their own acceptance.
Stored 4.0 proof is not automatically current: a guarded replan may add an explicit
compatibility binding only after checking its exact old contract hash, run identity,
inputs and artifacts. It does not rewrite observations or migrate on read. Query
`--harness` and `--audit-readiness`; status or unchanged source alone is insufficient.
4.0 cannot use that binding. Recovery needs matching runtime and canonical snapshot,
with later history preserved, not a blind runtime downgrade.

Existing schema-1 plans stay readable/executable in legacy-unbound mode. Adopting bound proof is an explicit complete candidate replan to schema 2; fill the contracts, preview affected claims, and use the usual guarded apply. Do not auto-migrate all projects on plugin install or silently claim old reports were candidate-bound. Downgrading an active schema-2 plan is rejected. Older runtimes reject schema 2 instead of ignoring its proof contract. Snapshot/Observer verification is recorded historical state; `--harness`, `--audit-readiness` and closure verify against the current working tree, which the graph event watcher does not monitor.

Use deterministic assertions for measurable behavior and model inspection for visual/semantic claims. Use a separate reviewer for consequential joint claims when useful. Reserve human decisions for material acceptance ambiguity, required authority, irreversible/high-impact actions or unresolved consequential risk—not routine screenshots and test logs. Stop a repair loop when the same failure repeats without new evidence; diagnose or replan instead of retrying indefinitely or escalating every ordinary defect to the user.
