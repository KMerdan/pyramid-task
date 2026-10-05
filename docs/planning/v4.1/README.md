# Pyramid 4.1 — precise progress, bounded context

Development and qualification are complete; 4.1.0 source was committed and pushed
to `main` as [58559af](https://github.com/KMerdan/pyramid-task/commit/58559afb072f2b9acb4b4d59f3450abc99b7a50b)
on 2026-10-04. See [current context](../../../CONTEXT.md) for the dated status and
installation boundary. This page owns the development decisions and evidence
index, not a second execution ledger.

The sections below retain the original scope and rationale. They are not new
instructions to implement completed tasks. The initial baseline was 4.0.0 at
`3d787c5c2038d61f1146f24ba20188bfd18b6495`; the obsolete 3.7.1 checkout was saved
outside the repository before removal. Publication did not update installed
plugins, adopt another project's plan or deploy a service.

## Completed ladder and evidence

The local intent closed at revision 7, graph version 58. All six work tasks,
three gates, three outcomes and the intent passed verification. Use these bounded
entry points before opening individual traces:

- [Final source qualification](../../../proof-output/v4.1/TASK-432/qualification.md):
  176 tests, repository validation, real versus synthetic checks and package identity.
- [Native-host pilot](../../../proof-output/v4.1/TASK-422/summary.md): actual
  Codex/Claude runs and usage limits; no demonstrated token savings.
- [Independent join review](../../../proof-output/v4.1/TASK-432/join-review.md):
  findings, follow-up checks and remaining qualification limits.
- [Intent audit](../../../proof-output/v4.1/INTENT-410/qualified-audit.json) and
  [final gate audit](../../../proof-output/v4.1/GATE-439/qualified-audit.json):
  the recorded acceptance checks before closure.

These are historical observations bound to their recorded source and inputs.
In particular, the qualification report predates closure and publication; its
uncommitted-source and pending-gate statements are not current repository status.
Later documentation edits do not rewrite or extend those proof claims.

## Intent

An engineer can extend an existing plan, keep authorized development moving,
and reach a verified small outcome with less avoidable requalification and
context loading. The system must retain real authority boundaries, current
candidate proof, independent consequential review, visual feedback when the
claim requires it, and recoverable history.

`candidate-plan.json` is the portable revision-6 schema-2 planning snapshot;
canonical revision 7 added a narrow documentation amendment before closure.
It is not a completed-state backup. The local canonical
`.pyramid` and generated `docs/tasks` are ignored development projections, not
additional checked-in ledgers. `baseline.json`, `assurance.json` and
`plan-review.json` describe the initial planning state, not successful tests or
accepted implementation. Only the canonical runtime owns execution status.

Historical initial validation on 2026-10-04: candidate, baseline, assurance and
review schemas passed; canonical `doctor` was healthy at graph version 1. All
six work tasks were then unstarted. Planned inspections, impact confirmation and
final controls were acceptance blockers at that point; they were subsequently
completed before closure. This is not the current ready frontier.

## Baseline findings and limits (4.0, before implementation)

Two active development sessions supplied contrasting patterns. The Desktop
session repeatedly qualified a risky VM/controller environment; the service
session separated routine agent review from human authorization and reused
unchanged tests. Different project risk, age and proof schemas confound direct
productivity comparisons. Neither observation proves a percentage improvement.

- Confirmed 4.0 runtime mechanism: `replan_project` compared incoming and outgoing
  incident edges. Adding a consumer can stale its unchanged prerequisite.
- Related 4.0 schema-2 mechanism: `pyramid_verification.contracts` included all
  consumers in a primary proof's digest. Adding a consumer can change existing
  producer proof identity even when the producer's procedure and inputs do not.
  Directional graph invalidation alone therefore needs a proof-freshness check.
- Confirmed workflow anti-pattern: a task lease refresh changed a GUARD literal
  inside a reviewed caller, causing a new source hash and repeated qualification.
  The caller belonged to the project; Pyramid does not need a new permission or
  execution-admission subsystem to prevent this pattern.
- The Desktop snapshot had 21,931 resolved drift entries, 21,210 under its harness
  tree, and approximately 93 GiB in that tree. These are local footprint and
  bookkeeping observations, not Git size or evidence that every file is waste.
- The service's real database failure/recovery test and partial review reuse are
  useful patterns. Its external mail transport was simulated, its task remained
  unverified, and repeated unchanged review-policy checks were still overhead.
- STE-inspired clarity and lower token cost are hypotheses. Prompt-format
  research does not establish that this profile benefits current coding hosts.

Raw private session histories, credentials, databases and screenshots are not
copied into this repository. Use the sanitized case families below and current
source to reproduce mechanisms.

## Delivery ladder

| Increment | Engineer-visible result | Work | Acceptance gate |
| --- | --- | --- | --- |
| I1: precise extension | Adding a new consumer preserves an unchanged provider's valid proof; changed composition still stales. A fresh guard does not require editing reviewed procedure source. | TASK-411, TASK-412 | GATE-419, then OUTCOME-410 |
| I2: decisive agent workflow | The skill distinguishes authorization, review and verification; a blocked check does not serialize independent work. The first gate proves a small public journey with only necessary harness capability. | TASK-421, TASK-422 | GATE-429, then OUTCOME-420 |
| I3: bounded, qualified candidate | Engineers can inspect artifact footprint without mutation and use a qualified 4.1 candidate on both hosts, with measured limitations instead of token-saving claims. | TASK-431, TASK-432 | GATE-439, then OUTCOME-430 |

Later gates inherit earlier current proof. Their ordering is acceptance ordering,
not a reason to block independent implementation. Shared source writes remain
serialized. Current runtime conflict analysis, not equal wave numbers, decides
whether tasks may execute in parallel. The original planning turn launched no agents.

## I1: original scope — change only the claim that changed

TASK-411 first reproduces the defect against 4.0.0 in disposable projects. Define
directional edge semantics before editing invalidation. A new consumer does not
change an unchanged provider; adding a contribution can change a parent's
composition. Provider contract, dependency, source, selected path and proof
changes must still invalidate affected claims. Preserve old/new ancestor checks,
stale-guard refusals, failed evidence, atomic publication and history.

Cover schema-1 graph behavior and schema-2 proof identity. Do not preserve a
producer by silently treating a changed contract hash as equivalent. If stored
4.0 proof needs a versioned compatibility rule, document and test that rule
without rewriting historical observations or declaring new consumers verified.
Expose the affected claims/reasons in the existing replan preview if needed;
do not add a second graph engine or state machine.

TASK-412 defines a standard integration recipe for two separate identities:
immutable procedure/source and fresh task/audit authority. A caller receives the
current guard as separately validated invocation data; it does not bake it into
reviewed source. Guard renewal is not renewed host authorization. Helpers remain
advisory until current identity, source, relevant state and evidence are joined;
no blanket exception accepts stale helper output.

## Decision: targeted replanning, not broad redrafting

`DECISION-REPLAN-EFFICIENCY` records the agreed direction on 2026-10-04:

- Assemble a complete candidate by copying the current plan and changing only
  affected stable node IDs/fields. Preserve untouched text and contracts.
- Compare generated content before writing; skip projections whose bytes are
  unchanged. Do not trust an incremental cache in place of current computation.
- Retain complete validation, relevant invalidation, current context/guards,
  recoverable history and guarded canonical publication. Full snapshot
  serialization is compatible with narrow agent authoring.
- Do not use raw line-number edits or add a general patch API/new graph engine
  merely to express this delta. Fewer disk writes do not establish token savings.

This decision was implemented in TASK-421: skills guide targeted candidate
authoring, and the runtime skips byte-identical ready/Markdown projection writes
while retaining complete recomputation and validation. The [projection review](../../../proof-output/v4.1/TASK-421/final-review.md)
and [regression results](../../../proof-output/v4.1/TASK-421/projection-final-tests.txt)
record the actual behavior; fewer writes do not establish token savings.

Historical canonical revision/graph version 2 recorded this decision. The guarded apply
changed no nodes or edges and invalidated no claims or inspections; all six work
tasks were then ready and unstarted. The 4.0 runtime marked the overall assurance
bundle stale on replan. That historical status was retained, not edited away;
planned post-change inspections and controls were completed later.

Development started after that planning snapshot. Revision 3 adds the serialized
state schema to TASK-411's proof inputs; its existing acceptance and write scope
are unchanged. TASK-411 implements directional invalidation and producer-scoped
proof, including explicit guarded compatibility for recorded 4.0 observations.
Current work and acceptance status remain authoritative in `.pyramid`, not this
historical planning narrative. No installed plugin is upgraded by source work.

The first implementation slice, TASK-411, passed its scoped audit on 2026-10-04
at graph version 8. The frozen source passed 168 tests and validation of 17 skills
and 31 schemas. Real disposable CLI/probe cases establish consumer growth and
guarded 4.0-proof compatibility; synthetic contract fixtures are labeled as such.
See the [TASK-411 completion snapshot](../../../proof-output/v4.1/TASK-411/completion.md)
for that early evidence index. It describes a same-session task audit, not
independent joint or installed-host acceptance. TASK-412 and the remaining ladder
were pending at that snapshot; they subsequently passed, including independent
join qualification and final assurance. Source manifests now declare 4.1.0;
installed-host status is a separate observation.

## I2: original scope — controlled operational language, not controlled reasoning

Apply a small original, STE-inspired profile to `create`, `take`, `audit`, the
relevant handoff/replan/helper instructions and generated guidance. Keep one
maintained terminology source; inject only relevant definitions, not a dictionary
or a full handbook into every packet.

1. Give authorization, review, task-ready, audit-ready, implemented, verified and
   blocked distinct meanings. Keep existing JSON names and runtime states.
2. Name the condition, actor, action and limit for consequential decisions.
3. Use one principal action per instruction. Short sentences are a preference,
   not a word-count gate that weakens or expands the task.
4. Use MUST/MUST NOT for real invariants, SHOULD for defaults and MAY for options.
   These words do not override host permissions or higher-priority instructions.
5. Keep observed result, evidence reference and limitation separate. Hashes,
   file existence, simulated transport and model assertions are not execution
   or visual attestations.
6. Keep task ownership guards separate from candidate source fingerprints.
7. Recheck an unchanged policy or authorization only when relevant facts change
   or the user requests it. A new turn is not itself a new scope.
8. Load detailed references only for the current decision. Do not change canonical
   acceptance merely to shorten a prompt or cosmetically reword an active plan.

Example:

> If required browser tooling is unavailable, record visual verification as
> blocked. Continue authorized work that does not depend on that verification.
> Do not pass the affected visual claim.

Creation/replanning must separate implementation, verification and release
dependencies. Require an actual consumed artifact/state/contract to justify a
hard start dependency. Put genuinely necessary missing probes/capture setup
before the acceptance that consumes it, not before unrelated product work.
Do not call a process start, component matrix or VM setup the first usable
increment when the intent promises a complete public journey.

Human decisions remain necessary for new authority, material intent changes,
irreversible/high-impact actions and unresolved consequential risk. Routine
agent checks do not become human sign-off. A failed check stays failed; human
approval cannot substitute for missing technical evidence.

TASK-422 uses existing host execution and small disposable projects, not a new
agent launcher, workflow engine or benchmark service. Six case families exercise:

| Case | Required distinction |
| --- | --- |
| CASE-EXTENSION | New consumer versus changed provider/parent; preserve only the former's unchanged producer proof |
| CASE-GUARD | Renewed task ownership versus changed executable source or host permission |
| CASE-BLOCKER | Blocked risky VM check versus authorized independent source work |
| CASE-REVIEW | Routine independent agent review versus genuinely new human authority |
| CASE-PROOF | Real database results plus simulated transport; reuse unchanged proof, reject stale inputs |
| CASE-VISUAL | Missing capture/review versus a passing internal probe; no fake visual pass |

For each host, compare matched 4.0 and candidate instructions with the same raw
facts, model/settings, tool affordances and permission limits. Randomize order
where practical; repeat materially discordant cases, not every task. Judge actual
decisions and tool effects, not headings, keywords or a model's self-rating.
Preserve raw bounded failures and report sample limitations.

Measure correctly resolved cases, unnecessary user questions, false acceptance,
authority violations, loaded references, tool calls and wall time. Record actual
input/output usage when exposed by the host; label unavailable reasoning,
cached-token or billing data unknown. Bytes and words are only proxies. Report
tokens per correctly resolved case, not percentage savings inferred from file
length. No critical safety/evidence regression is acceptable. Claim lower token
cost only if matched observations establish it; otherwise report the result as
unproven or revise the profile.

## I3: original scope — constrain footprint without losing proof

TASK-431 separates authoritative harness source, generated candidates, temporary
owned runtime resources and retained evidence. Strengthen checks only where the
existing plan/result/proof contract supplies enough evidence to identify an
unsafe overlap. Do not infer file purpose from extension alone, hide source under
an evidence glob, or suppress invalidation for generated behavior inputs.

Add one optional, read-only footprint/retention preview under the existing
`inspect` surface if the current queries cannot answer the question. Return
bounded counts/bytes, declared classes, referenced proof and unknown ownership;
enumerate individual files only on explicit detail. Keep normal packets and
readiness cheap. Scans do not delete, rewrite, archive, relabel or expire evidence.
No automatic GC, Git LFS migration, new database, observer redesign or legacy
history compaction belongs to this release. Separate retention implementation
requires proof that archive, failed/active run and restored-history references
remain recoverable.

TASK-432 joins runtime changes, instructions, usage limitations and footprint
reporting into the 4.1 candidate. Run full regression and actual subprocess tests,
package both manifests with base version 4.1.0, update README/architecture/release
notes and prove both host skill paths in isolated profiles. Source CLI or schema
validation alone does not qualify an installed host adapter. A missing host is a
qualification blocker, not a pass. Do not overwrite a user's installed 4.0.0
plugin to run this qualification.

## Deferred scope and original authority boundary

- No new permissions, weakened VM containment, production or credential access.
- No automatic `/compact`, host hook, persistent scheduler or agent launch system.
- No automatic acceptance, extra routine human signature, or model-only runtime
  claim that a real test or screenshot was performed.
- No full STE dictionary/compliance claim, natural-language parser or styling gate.
- No copied private evidence, raw auth state, broad trace ingestion or model-time
  telemetry inferred from CLI duration.
- No automatic migration/rewording of live plans or replacement of their guards.
- The original planning turn did not authorize commit, push, publication,
  installation or deployment. The owner later authorized commit and push, which
  completed in `58559af`; plugin updates remain the owner's separate operation.

## Research references

- [ASD-STE100 official overview](https://www.asd-ste100.org/about_STE.html)
- [Issue 9 procedural rules](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf)
- [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and
  [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)
- [Prompt formatting sensitivity, ICLR 2024](https://arxiv.org/abs/2310.11324)
- [LLMLingua-2, ACL 2024](https://aclanthology.org/2024.findings-acl.57/)

These motivate a testable design. They do not establish gains for Pyramid or
certify the proposed profile as ASD-STE100 compliant.
