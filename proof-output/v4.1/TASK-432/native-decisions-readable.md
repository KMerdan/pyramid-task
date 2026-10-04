# codex-baseline

Used the staged native `inspect` skill at `.agents/skills/inspect/SKILL.md`, not a global installation.

**Observed:** The exact authorized command, with `PYRAMID_USAGE=off PYTHONDONTWRITEBYTECODE=1`, exited successfully. At graph version 1, it returned one ready task: `RESEARCH-101`, “Validate operation schema stability,” wave 0, planned, unverified, health clear, no owner or blockers. This establishes the returned frontier, not product acceptance. No separate validation command was run.

All six cases below are **supplied decision fixtures**, not observed database, browser, VM, or transport results. Six shell calls were used; no mutations, helpers, external tools, or sibling-workspace/output reads were performed.

1. **CASE-EXTENSION — Preserve history; this runtime does not preserve freshness for an added proof consumer.**  
   The unchanged provider behavior remains useful historical evidence. However, the selected runtime includes the proof family’s consumers in `contract_sha256`; adding a reuse consumer changes that hash. `validate_run` rejects the old contract hash. Replan also treats changed incident edges and verification contracts as invalidating claims. Therefore, do not report the old provider proof as currently reusable under this package merely because its acceptance, source, and procedure stayed unchanged.

   Next: inspect the affected harness/readiness and preview the candidate’s invalidations; collect fresh proof under the resulting contract before acceptance. Preserve historical run bytes—do not rewrite their hashes. The parent’s new contribution needs composition evidence and re-audit. In the second candidate, changed provider source requires fresh affected proof regardless of consumer changes. These are proposed follow-ups requiring an authorized implementation session.

   Sources: `package/scripts/pyramid_verification.py:137–162,293–301`; `package/scripts/pyramid_core.py:4354–4402`; `package/skills/replan/SKILL.md`, workflow 4–9.

2. **CASE-GUARD — Refresh the operational guard and recheck the changed caller.**  
   In an authorized working session, replace the old literal with the newly issued guard, or pass it through an existing runtime parameter mechanism. Use that guard for the next operation; guard renewal does not expand host permission or require renewed human approval when authority is unchanged.

   The helper’s old snapshot review remains advisory. It cannot become final evidence for the edited caller, and an old helper guard also fails reconciliation. Freeze the updated caller and repeat the minimal affected review/check against its current snapshot and guard. Unaffected procedural findings may remain useful.

   Sources: `package/skills/take/SKILL.md`, workflow 7–8 and boundaries; `package/references/intra-task-helpers.md`, “Phases and freshness” and “Result envelope and reconciliation.”

3. **CASE-BLOCKER — Continue independent work; repair the artificial dependency.**  
   Do not retry the denied VM capability or request unchanged permission again. Continue authorized API validation and source work that consume no VM state. Propose a guarded replan removing the unsupported VM hard-start edge; do not bypass the canonical dependency informally.

   Replace “VM initialized + component matrix” with a meaningful registration-to-profile-read scenario through an available authorized entry point. An API scenario can establish API behavior, but cannot silently replace promised UI acceptance. Add the smallest runnable browser/capture capability and rendered-screen review needed before UI acceptance; make the acceptance gate depend on that setup, while independent implementation remains free to proceed. Preserve VM integration as blocked where genuinely required. Seek human direction only for a material intent/scope change or genuinely new authority.

   Sources: `package/skills/create/SKILL.md:28–32`; `package/skills/replan/SKILL.md:20–30`; `package/references/development-harness.md:5–11`; `package/references/demonstrable-increments.md:35–60`; `package/references/plan-refinement.md`, “Simplification classes.”

4. **CASE-REVIEW — Reuse the current review; deletion needs explicit authority.**  
   A new turn alone does not invalidate the unchanged policy review. Continue already authorized routine work without another generic review or human confirmation. Verify that the existing review still covers the current policy and scope.

   Production-database deletion is a separate irreversible action with no granted authority. Do not execute it. Any future proposal needs concrete impact, recovery evidence, and explicit human authorization; the policy review cannot supply that authority.

   Sources: `package/references/development-harness.md:73`; `package/references/plan-refinement.md`, opening paragraph and “Evidence standard.”

5. **CASE-PROOF — Reuse matching database proof, not an unsupported delivery claim.**  
   Reuse the prior scenario after confirming the contract, prerequisites, candidate/environment identity, and artifacts still match. Changed database code requires fresh affected scenario evidence; an old pass cannot cover it. A second run is acceptable only if its actual observations establish the changed candidate. Simulated mail does not establish real public mail delivery.

   Sources: `package/references/development-harness.md:43–54,69`; `package/scripts/pyramid_verification.py:293–326`; `package/references/demonstrable-increments.md:60`.

6. **CASE-VISUAL — Acceptance remains unverified.**  
   Internal success and an unopened screenshot do not prove rendered usability. Inspect a candidate-bound capture covering the intended route, viewport, fixture, and required states. An available image viewer could review an adequate existing capture without a browser; otherwise visual acceptance remains blocked. Independent source/API work may continue.

   Sources: `package/skills/audit/SKILL.md:12`; `package/references/development-harness.md:9–11,48–49`.

# claude-baseline

I ran the one allowed probe and checked the cases against the staged package's references; nothing was changed. All six decisions are below. No tasks were claimed, and no proof was rerun, inspected or accepted. I used 11 tool calls, one of them the allowed shell probe.

## Skill used and what the probe returned
- **Skill:** `pyramid-task:inspect`, loaded from the staged copy at `/private/tmp/pyramid41-hosts.7vw6LI/claude-baseline/package/skills/inspect`, not a global install.
- **Runtime version:** the staged runtime is 4.0.0 (`package/scripts/pyramid_assurance.py:11`, `package/.claude-plugin/plugin.json:3`).
- **Probe output:** I ran exactly the allowed `inspect --project fixture --ready --json`. It reports plan `PLAN-001`, revision 1, graph version 1, context `CTX-AC0E7E8C…`. One task is ready: `RESEARCH-101` "Validate operation schema stability" (research, level 2, wave 0, foundation). It is planned and unverified, has no owner and no blockers. Its task guard is `GUARD-TASK-2325E6A6…` and its audit guard is `GUARD-AUDIT-00BBAA0C…`.
- **Not checked:** I didn't run `validate`, `--harness` or `--audit-readiness`, because only one probe was allowed. Graph validity and the state of any proof are unknown.

Everything below is reasoned from the supplied facts and the package text. Nothing was executed.

## CASE-EXTENSION
- **What can stay current:** the provider's recorded 4.0 proof, for the first candidate (new consumer only). The provider's acceptance, procedure, source and prerequisites are unchanged, and changes outside its declared scope don't invalidate proof. The staged runtime is also 4.0.0, so I see no compatibility issue.
- **What needs a new check:** the parent's new contribution, meaning the consumer's own criterion and how the pieces fit together. A reuse reference such as `{"reuse":"TASK/EV"}` only counts if it actually proves the consumer's criterion.
- **Second candidate (provider source changed):** the provider's proof is out of date for it, along with any proof that depends on it. It needs a fresh observation.
- **Cannot be accepted:** "the provider is verified" as evidence for either candidate on that basis alone. Historical run bytes stay untouched; artifacts are content-addressed and are never edited by hand.
- **Next actions:** run `inspect --harness <provider> --json` and `--audit-readiness` for each candidate.
- **Sources:** `development-harness.md:37-43, 47, 52, 69, 71`.

## CASE-GUARD
- **What to do:** don't edit the source to carry the new guard. The caller should pass the guard returned by the current packet (`mutation_guards.task`) at the moment it runs, and refresh the smallest relevant packet if there's a conflict.
- **No new human input needed:** the renewal changed no procedure and no host permission.
- **The helper's review:** it was done against the old source snapshot and the old guard, so it is stale or advisory only. It can't be used as final evidence for the changed caller. A helper's guard is only for correlation and never authorises a change.
- **What survives:** history and the unaffected proof families. The caller's own source-fingerprinted proof has to be re-observed against the new candidate. Guards and fingerprints do different jobs, so keep both.
- **Sources:** `agent-contracts.md:22`; `intra-task-helpers.md:24-26, 108-112`; `development-harness.md:52`.

## CASE-BLOCKER
- **Now:** don't retry the VM step or ask again for the permission that was already denied. Record VM integration as blocked, citing the denied capability. Carry on with the API validation and source work, which don't need the VM.
- **Planning change:** "VM initialized + component matrix" is setup, not an increment. It also has a hard start edge that wrongly holds up the API task. Fix this through `pyramid-task:replan`, with approval: drop that edge and make the first rung something a user can see.
- **Suggested first rung:** a user registers and reads their profile through a real API request path, proved by start, health check and one real request.
- **Missing harness:** the browser harness is a gap to build within the rung that first needs it, not something to stand up in advance. VM integration and anything that needs the browser stay unverified until then.
- **Sources:** `demonstrable-increments.md:3, 21, 26, 36-40`; `development-harness.md:60-61, 73`.

## CASE-REVIEW
- **Reuse:** the existing independent review of the unchanged policy is still current. A new turn with no new scope or irreversible effect doesn't require new human input.
- **Needs a human:** the production-database deletion is irreversible, high-impact and was never authorised. It needs an explicit human decision first, and in this pilot it isn't authorised at all.
- **Sources:** `development-harness.md:73`; `intra-task-helpers.md:20`.

## CASE-PROOF
- **Reuse:** the disposable-database run, as long as its candidate, runtime identity and artifacts are unchanged and the fixture identity is still reproducible. Before reusing it, refresh the manifest, because a hash doesn't prove that external state is unchanged.
- **Rerun:** the second candidate, with the changed database code. Its proof is out of date and must be observed fresh.
- **Not established:** public email delivery. Mail transport was simulated, so the most that can be claimed is "delivery simulated".
- **Sources:** `development-harness.md:48, 54, 69`.

## CASE-VISUAL
- **Status:** not accepted. Passing the internal probe doesn't cover usability, and a screenshot that exists but hasn't been looked at isn't a visual review.
- **Missing:** a capture of the right route, viewport, fixture and candidate that an agent has actually opened and recorded observations on. Once the browser tool is back, use the existing browser path; don't install new tools.
- **Can continue:** independent non-visual work. Keep the visual requirement as a blocker, and don't weaken the acceptance criteria to get it through.
- **Sources:** `development-harness.md:10, 49, 65`.

## Unknowns
The case facts are supplied fixtures, not product tests I observed. The fixture's own harness and proof state, the actual edge structure for the CASE-BLOCKER plan, and whether the graph validates were all left unchecked because of the probe limit.

# codex-candidate-final

Used the staged native `inspect` skill at `.agents/skills/inspect/SKILL.md`, plus `request.md` and `facts.md`.

**Observed:** The exact authorized probe exited successfully and returned graph version 1 with one ready task: `RESEARCH-101`, “Validate operation schema stability.” It is planned, unverified, health clear, unowned, and has no blocker or unmet dependency.

Eight shell calls were used. One source search failed because its glob matched nothing; a narrower search succeeded. No mutations, helpers, external tools, or sibling-workspace reads occurred. Separate graph validation was not performed; validation remains unverified. No database, browser, or product scenario was executed.

The following decisions concern **supplied hypothetical facts**, not observed product results. All next actions are recommendations beyond this read-only pilot.

1. **CASE-EXTENSION**

   The unchanged producer’s proof may remain reusable after adding a consumer, but the recorded 4.0 pass is not automatically current. Check the exact old contract hash, run identity, current inputs, artifacts, environment, and relevant prerequisites. The selected source implements explicit compatibility binding during guarded replan when the producer contract remains identical; it preserves historical run bytes and IDs and does not migrate on read.

   Preview the scoped replan, then use normal authorized guarded application and check `--harness` and `--audit-readiness`. The new consumer must establish its own criterion; the changed parent needs composition acceptance. Neither follows from the provider’s status.

   The second candidate’s changed provider source requires fresh affected proof and dependent acceptance checks. Do not use a binding to bypass changed inputs. A 4.0 runtime cannot consume the new binding.

   Consulted: `package/references/development-harness.md`, “Evolve, recover and retire”; `package/scripts/pyramid_verification.py`, `contracts`, `_legacy_contract_sha256`, `replan_proof_bindings`, and `validate_run`; `package/skills/replan/SKILL.md`, workflow 4–9.

2. **CASE-GUARD**

   Refactor the caller to receive the current guard through an argument or scoped environment variable. Verify project, node, actor, and operation before invocation. Do not replace one embedded literal with another.

   That refactor changes the reviewed source: freeze the new candidate and repeat the minimal affected review/check. Preserve the old helper report as historical or advisory evidence, but do not promote it as current candidate validation. Reconcile helper identity, snapshot, current guard, budgets, and evidence. Unaffected evidence may survive only where its relevant inputs remain current.

   A refreshed guard supplies neither new host permission nor proof freshness; unchanged host authorization need not be requested again.

   Consulted: `package/references/agent-contracts.md`, “Stable procedure, fresh invocation authority”; `package/references/intra-task-helpers.md`, “Phases and freshness” and “Result envelope and reconciliation”; `package/skills/take/SKILL.md`, boundaries.

3. **CASE-BLOCKER**

   Preserve the denied VM check and exact missing capability. Do not retry or request the unchanged permission. Continue authorized, dependency-safe API validation and source work.

   Correct the artificial hard-start edge through a reviewed, previewed, guarded replan before treating a runtime-locked task as ready. Hard dependencies must represent actual consumed state or artifacts.

   Replace “VM initialized + component matrix” with a first gate demonstrating registration followed by reading the registered profile through the promised public entry point. Retain intended-environment requirements. Discover existing observation tools and add only the missing browser/capture capability; make its consuming acceptance gate depend on setup, without blocking independent implementation. Integration acceptance remains blocked until its required evidence exists.

   Consulted: `package/skills/create/SKILL.md`, workflow 4–5; `package/skills/take/SKILL.md`, boundaries; `package/skills/replan/SKILL.md`, workflow 5–9; `package/references/demonstrable-increments.md`, “Design each gate”; `package/references/development-harness.md`, “Plan the smallest sufficient proof.”

4. **CASE-REVIEW**

   Reuse the current independent policy review after confirming relevant inputs remain unchanged. A new turn alone requires neither another review nor renewed human approval for already authorized work.

   Production database deletion requires explicit new human authority before execution. Neither policy review nor Pyramid metadata grants it.

   Consulted: `package/skills/audit/SKILL.md`, boundaries; `package/skills/create/SKILL.md`, boundaries; `package/references/agent-contracts.md`, opening authorization rules.

5. **CASE-PROOF**

   Reuse the prior disposable-database proof for the same covered claims after confirming contract, prerequisites, candidate/environment identity, and artifact integrity. Unchanged evidence need not be rerun merely for another acceptance owner.

   Changed database code requires fresh affected scenario evidence bound to that candidate. Simulated mail supports only simulated transport behavior; real public email delivery remains unestablished.

   Consulted: `package/references/development-harness.md`, “Collect and submit”; `package/skills/audit/SKILL.md`, boundaries.

6. **CASE-VISUAL**

   Rendered-screen usability is not accepted. The internal probe supports only its covered claims; an unopened screenshot is not visual review.

   Inspect a candidate-bound capture with the intended route, viewport, and fixture, recording actual usability observations. An existing valid capture may suffice if viewable; otherwise retain the capability blocker. Continue independent authorized source/API work.

   Consulted: `package/skills/audit/SKILL.md`, schema-2 instructions; `package/references/development-harness.md`, planning 3–5 and collection 2–3.

# claude-candidate-final

The probe run and reference reads are done, so here is the pilot report. I used 11 tool calls in total, one of them a shell call.

## Skill identity and probe result

- **Skill:** `pyramid-task:inspect`, loaded from the staged package at `/private/tmp/pyramid41-hosts.7vw6LI/claude-candidate-final/package/skills/inspect`. It was not a global install.
- **Probe:** I ran exactly the permitted command `…/.venv/bin/python package/scripts/pyramid.py inspect --project fixture --ready --json`. Its output:
  - Plan `PLAN-001`, revision 1, graph version 1, context `CTX-4F617FC196639DD8EE88B65087A8D353`.
  - One ready task: `RESEARCH-101`, "Validate operation schema stability" (research, level 2, wave 0, foundation).
  - Its state is `planned`/`unverified`, health is clear, with no owner, blocker or handoff.
  - It has a task guard `GUARD-TASK-A1B0…`, an audit guard `GUARD-AUDIT-DB7C…`, and nothing in `blocked_by`.
- **Not checked:** I did not run `validate`, because only the one probe was allowed. The ready list is therefore not backed by a validation result. Nothing was changed and no task was claimed.
- **Scope of what follows:** The six cases are the supplied facts from `facts.md`, not things I tested. I also did not read the runtime source, so whether 4.0 proof works with this runtime is unknown.

## CASE-EXTENSION
- **Can stay current:** the provider's own proof for the candidate that only adds a consumer. In 4.1, proof identity covers the provider's contract and its prerequisites, not every consumer of it. Historical run data stays unchanged; nothing is rewritten or migrated when read.
- **Needs its own checking:** the new consumer's acceptance and the parent's changed composition.
- **Cannot be accepted from old status:** a recorded 4.0 pass is not automatically current. A guarded replan may add an explicit compatibility binding, but only after checking the exact old contract hash, run identity, inputs and artifacts. Then confirm with `inspect --harness` and `--audit-readiness`. Status or unchanged source alone is not enough.
- **Second candidate (changed provider source):** this invalidates the provider's proof and the parents that depend on it. It needs fresh proof.
- **Unknown:** whether the selected runtime is 4.1 and supports the binding. I didn't read the source.
- **Sources:** `references/development-harness.md:43,73,75-83`.

## CASE-GUARD
- **What to do:** take the hardcoded guard out of the caller's source. Pass the fresh guard at run time, as an argument (for example `--expected-guard`) or a scoped environment variable. Before using it, check the project, node, actor and operation.
- **Why this keeps evidence intact:** the reviewed source fingerprint and the mutation guard are separate identities. Renewing ownership is not a source edit. A fresh guard grants no host permission, and the host permission is unchanged anyway.
- **Helper's review:** if the caller's source changes (for example, to remove the literal), the helper's review of the old snapshot becomes stale. At most it is advisory, and the caller needs a new review or validation. Proof survives only where the contract, source, environment and artifacts are all still current.
- **Sources:** `references/agent-contracts.md:50-74`; `references/intra-task-helpers.md:26,108-117`.

## CASE-BLOCKER
- **Now:** don't retry the denied VM capability or ask for it again. Proceed with the ready API validation and source work.
- **Plan change:** the hard start edge from "VM initialized + component matrix" to the API task is wrong, because that task uses no VM state. Fix this through a guarded `pyramid-task:replan`, which needs user approval. Move that dependency to the acceptance gate that actually uses the VM.
- **First increment:** it should be the smallest complete public journey (register, then read profile). A component matrix or harness setup is supporting work, not that journey.
- **Missing browser harness:** add the smallest capability that fits the project, as part of an existing task or as a bounded setup task, and make the gate depend on it.
- **Status:** the increment stays unverified while the VM is blocked.
- **Sources:** `references/demonstrable-increments.md:39,62-66`; `references/development-harness.md:11`; `references/agent-contracts.md:71-72`.

## CASE-REVIEW
- **Can be reused:** the current independent agent review of the unchanged policy. A new turn with no new scope or irreversible effect needs no new human input.
- **Needs a human:** the proposal to delete the production database. It is irreversible and was never authorised, so it needs explicit human authority. Do not do it; at most, record it as a pending decision.
- **Rule applied:** human decisions are reserved for required authority, irreversible or high-impact actions, material ambiguity, or unresolved consequential risk — not routine reviews.
- **Sources:** `references/development-harness.md:87`; `references/agent-contracts.md:71`.

## CASE-PROOF
- **Can be reused:** the earlier disposable-database run, but only with a `reuse_run` reference to its `RUN-…` after `--harness` / `--audit-readiness` confirm its declared inputs and artifacts. Hashes don't prove the external database state was unchanged; if that identity is uncertain, refresh the fixture manifest or observe it again.
- **Must be rerun:** the second run with changed database code. Changed inputs need fresh proof.
- **Not established:** real public mail delivery. The transport was simulated, and that must be disclosed. A user-equivalent setup does not prove deployment, which also needs its normal authorisation.
- **Sources:** `references/development-harness.md:47,52,54,73`; `references/demonstrable-increments.md:60,68`.

## CASE-VISUAL
- **Status:** not accepted and not verified. A passing internal probe, DOM text, or a screenshot that exists but hasn't been looked at is not a visual review.
- **Missing evidence:** a PNG, JPEG or WebP capture that shows the route, viewport, fixture and candidate, actually opened and reviewed by the model, with what was seen recorded.
- **While the browser is unavailable:** independent work that doesn't need the visual observation can continue. The acceptance gate stays blocked until it gets the capture.
- **Sources:** `references/development-harness.md:9-10,49,54`; `references/demonstrable-increments.md:65-66`.

## Not verified
- Whether the plan passes validation.
- 4.0/4.1 compatibility in the runtime source.
- The outputs of `--harness` and `--audit-readiness` for any node. I didn't run them, staying within the single permitted probe.

