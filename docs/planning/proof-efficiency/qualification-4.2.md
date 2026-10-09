# Standalone Pyramid Task 4.2.0 qualification

## Delivered and verified scope

4.2.0 adds optional read-only proof input/overlap/reuse analysis and advisory source
dependency facts. Python standard-library analysis is the default without external
executable discovery. Explicit `ast-grep` or `auto` requests the optional adapter;
missing/incompatible/failed/timed-out tools fall back visibly. No installation
dependency, source execution, automatic input removal, skipped inspection or
proof-enforcement change is introduced. Project format V3 and existing plan/state
schemas are unchanged; two additive analysis schemas define the new JSON outputs.

Repository validator and **197 tests passed** on the source candidate, including:

- Real CLI default analysis ignores an available owned fixture executable; explicit
  `auto` probes it. Default API/benchmark analysis also performs no discovery.
- Real production analysis and benchmark entries work in fresh subprocesses with
  an empty executable search path. Explicit `auto` exercises actual absent-tool
  fallback, rather than merely selecting Python.
- Actual optional ast-grep **0.45.3** was exercised on the same frozen corpora.
- Source edits invalidate proof normally. Actual analysis left all canonical file
  hashes unchanged; scan/provider uncertainty never grants scope-removal authority.
- Ownership, ambiguity, module limits/cycles, supporting source/configuration
  changes, added/deleted files, invalid output and provider failure paths are tested.

## Measured accuracy

Reference and file-edge stages are scored separately against manually authored,
hash-bound gold, not against the other provider. TP/FP/FN use distinct typed
identity sets; known unresolved targets stay FN. Zero denominators are null/N/A.
Unknown targets have a separate expected/detected signal ledger. These are small
convenience samples, without independent annotators or representative sampling.

Both providers have identical reference/file-edge scores on these corpora:

- `basic`: 14 scanned files across JS/JSX/TS/TSX/Rust; 22 reference identities and
  21 file-edge identities, zero FP/FN. All 6 expected uncertainty signals detected.
- `heldout`: six original public pilot files; now regression data after Rust module
  ownership refinement. All 3 formerly missed Rust edges resolve correctly.
- `heldout-v2`: six different public-source files annotated before v2 scoring.
  This frozen sample is rerun for the 4.2 provider-policy change; no new resolver
  tuning used its mismatches. All 18 references are extracted correctly; all 8
  expected uncertainty signals are detected.

| heldout-v2 language | Files | Reference TP/FP/FN | Reference P/R | File-edge TP/FP/FN | Edge P/R |
| --- | ---: | --- | --- | --- | --- |
| JS | 1 | 1/0/0 | 100%/100% | 0/0/0 | N/A/N/A |
| JSX | 1 | 1/0/0 | 100%/100% | 0/0/0 | N/A/N/A |
| TS | 2 | 4/0/0 | 100%/100% | 1/0/0 | 100%/100% |
| TSX | 1 | 3/0/0 | 100%/100% | 0/0/0 | N/A/N/A |
| Rust | 1 | 9/0/0 | 100%/100% | 2/0/2 | 100%/50% |

Rust misses: `rust/src/matcher/text.rs:2` (`crate::Doc`, defined in `source.rs`)
and line 3 (`crate::Node`, defined in `node.rs`) require root symbol re-export
resolution, which is not supported. They remain visible FN in both outputs.
JS/JSX/TSX have no annotated local targets here, so resolution is N/A rather than
100%. The TS alias lacks annotated target/configuration in the partial snapshot;
it remains in the unknown ledger. AST syntax ranges share the file resolver and
do not remove these limitations.

Full per-language/per-syntax-family scores, mismatches, diagnostics, observed input
hashes and provider/rules identities are published in [results-4.2](results-4.2/).
Corpus sources, supporting files, upstream revisions, manifests and complete MIT
licenses are retained under
[`tests/fixtures/dependencies`](../../../plugins/pyramid-task/tests/fixtures/dependencies/).

## Duration and provider choice

| Corpus | Python with actual tool absence | Explicit ast-grep |
| --- | ---: | ---: |
| basic | 0.0120 s | 0.0289 s |
| heldout | 0.0265 s | 0.0423 s |
| heldout-v2 | 0.0296 s | 0.0480 s |

One invocation per provider/corpus; startup and discovery are included. These are
not throughput or development-time measurements. Equal scores on small samples do
not establish equivalent behavior on arbitrary syntax. Python is the default to
avoid an unproven dependency and discovery cost; the explicit optional adapter
remains available for continued comparison.

## Reproduction and limits

Run `make check` after installing `requirements-dev.txt`, with
`PYTHONDONTWRITEBYTECODE=1 PYRAMID_USAGE=off`. The test suite uses owned temporary
projects and an owned loopback HTTP fixture. Run the production benchmark with
`--manifest plugins/pyramid-task/tests/fixtures/dependencies/basic/manifest.json`
and explicit `--provider ast-grep` to compare. Absence tests use an absolute Python
interpreter, empty PATH and explicit `--provider auto`; no host tool is removed.

Package qualification checks matching Codex/Claude manifests and runtime 4.2.0,
repository validation and real CLI/benchmark behavior from an isolated source
snapshot. This is package/source CLI qualification, not installed Codex/Claude
agent behavior. Existing installations are unchanged by publication.

No rendered UI is changed, so visual review is inapplicable. Review is single-agent;
there is no independent human qualification. Broad production accuracy thresholds,
full TypeScript/Rust semantic resolution, transitive dependency closure, automatic
scope contraction and end-to-end workflow savings remain unqualified. Rollback for
new opt-in analysis is to stop invoking it; source fixes are normal subsequent
releases. Do not downgrade a live plan blindly across incompatible proof bindings.
