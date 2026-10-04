# Evidence clarification for focused independent follow-up

The first review's unknowns are retained in independent-review-initial-result.json.
No new runtime defect has been established. Review the actual detailed evidence,
not this coordinator statement alone.

- TASK-411 consumer-growth-4.0.json names the stored hash FORMULA, not a 4.0
  executable. Its CLI calls use 4.1 and its fixture independently computes the
  exact old format. recovery-detailed-result.json instead invokes the real
  frozen 4.0 executable, records every runtime/argument/stdout, including its
  harness output. Do not blur these experiments.
- The detailed recovery trace includes an actual changed-input audit rejection,
  exit 2, unchanged canonical state after refusal, restored archive ID and
  per-file snapshot hashes, per-record before/after history hashes. 4.0 validates
  the bound state structurally but reports proof not ready; that is deliberate
  fail-safe disagreement, not mixed-version support.
- guard-qualified-result.json records both invocation guards and the real resume
  packet, caller hash before/after, old-guard refusal and successful reasoned
  release. guard-caller.py is the initially refactored/reviewed recipe, not a
  claim that an old embedded literal was edited during renewal.
- artifact_footprint closes every remaining scandir iterator in finally at
  pyramid_assurance.py:152-154. Project queries use the normal serialization lock;
  coordination-file creation is not semantic state change. README now states this
  limit and corrects the old skill-count typo.
- Projection replacement is per-file atomic, not power-loss-durable/fsync or an
  atomic multi-view transaction. Graph is published last; readers retain the last
  context-matching graph. Canonical publication and projection failure tests are
  independent boundaries. Derived projections/indexes are rebuildable. See
  test_graph_is_published_only_after_other_projections_complete and live graph
  matching tests; no new crash-durability claim is made.
- A plan may reuse producer evidence for an actually covered consumer criterion;
  the fixture deliberately tests reuse availability, not new consumer semantics.
  Its consumer remains unverified. Agents must still establish new claims and
  parent composition; the runtime cannot judge semantic proof sufficiency.
- native-decisions-readable.md mechanically extracts the COMPLETE four final
  decision texts, avoiding JSON line-length truncation. Original bounded traces
  contain actual probes/usage. Case facts are supplied, not real product runs.
- qualified-test-pre-run.json and qualified-test-result.json record the exact
  command, pre-run current contract/input fingerprint, frozen package digest,
  result and artifact hashes. The 176-test log is not a process attestation beyond
  the actual coordinator execution; the existing ResourceWarning is retained.

The source plugin digest is unchanged by evidence repair or README clarification.
Review this consequential join without requiring unsupported installed-release,
mixed-version, real product/browser or statistical token-gain claims.
