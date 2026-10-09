# Standalone Pyramid proof efficiency acceptance

Owner direction recorded on 2026-10-09: use ast-grep as the preferred optional
dependency, retain a Python fallback for JavaScript, TypeScript and Rust, and
publish measured fallback accuracy when ast-grep is absent. This document records
the agreed design and acceptance requirements for the implementation in the requested `codex/proof-efficiency` worktree.
Owner refinement on 2026-10-09 after reviewing equal small-corpus provider scores:
Python is the default without executable discovery; ast-grep is an explicitly
requested optional provider, never an installation dependency. `auto` remains an
explicit option and must retain diagnosed fallback. The owner subsequently
authorized merge to main and publication of 4.2.0, separately from installed-plugin
updates. The isolated worktree has its own local-canonical development intent.
This document is a requirement, not passing evidence.

## Intended behavior

The Python runtime analyzes declared proof inputs, task write scopes, prerequisite
relations, invalidation reasons and reusable evidence. Source dependency extractors
provide additional facts with source locations and explicit limitations. Both
ast-grep and the Python fallback use the same result contract. Agent review decides
semantic sufficiency and proposed scope changes; existing guarded mutations own
formal contract changes.

The first implementation supports JS, JSX, TS, TSX and Rust. Python may use its
standard-library AST, but Python support does not substitute for these languages.
Extraction is read-only and does not execute customer source or build scripts.
Unknown relationships retain conservative proof coverage. Evidence identity remains
file-based; analyzer output alone cannot waive an inspection or prove acceptance.

## Operation without ast-grep

Acceptance must run the production analysis entry in a fresh subprocess where
neither `ast-grep` nor a verified ast-grep `sg` executable is discoverable. Construct
an isolated search path rather than changing the host installation. Use a fresh
derived cache so an earlier ast-grep result cannot qualify the fallback.

The run must select the Python fallback, analyze every required language, and
record provider selection, executable discovery, inputs, configuration and results.
Use explicit `auto` for this absence scenario now that the ordinary default is
Python; also prove the default does not probe or launch an available executable.
A forced-provider test is useful additional coverage, but does not replace this
actual absence scenario. Missing, incompatible, timed-out and failed ast-grep
invocations are separate tested cases with retained diagnostics.

## Reference corpus

Use two complementary sets:

- Versioned fixtures with independently authored expected dependencies, misleading
  comments/string contents, supported syntax and deliberately unresolved constructs.
- Held-out source snapshots representing real JS/JSX, TS/TSX and Rust projects.
  Review their reference dependencies independently of either extractor and retain
  source revision/hash, file counts, dependency counts and annotation limitations.

Freeze corpus membership, supported syntax and scoring rules before the
qualification run. ast-grep output is a comparison, not the ground truth. Preserve
each mismatch with its source location and disposition; tuning on qualification
files requires a new held-out set. Repository additions or exclusions must be
visible in the report.

Required syntax families include static imports, re-exports, literal `require`
and dynamic imports for JS; type imports and resolution configuration for TS;
and `mod`, `use`, path attributes and literal include macros for Rust. Include
multiline declarations, comments, string/raw-string contents, nested modules,
ambiguous resolution and malformed source. Dynamic paths, conditional compilation,
macro-generated relationships and build-generated inputs require explicit unknown
reporting when unresolved. Rust `use` statements must resolve through the module
structure, not be treated automatically as file paths.

## Accuracy measurements

Measure extraction and resolution separately. Extraction compares dependency
references and their source locations; resolution compares typed project-relative
file edges. The reference manifest defines canonical identifiers and deduplication
for both stages. Correctly extracting a reference does not establish correct file
resolution.

For each stage and each of JS, JSX, TS, TSX and Rust, publish:

| Measurement | Definition |
| --- | --- |
| TP | Predicted references/edges that match the independent reference set |
| FP | Predicted references/edges absent from the reference set |
| FN | Expected references/edges absent from the prediction |
| Precision | TP / (TP + FP) |
| Recall | TP / (TP + FN) |
| Unresolved | Count, reason and locations of reported unresolved constructs/references |
| Coverage | Scanned, skipped, unsupported and failed files; supported syntax families |

Publish per-language and per-syntax-family counts before any aggregate. A zero
denominator is `not-applicable`, not 100%. Unresolved dependencies with known
reference edges remain FN in end-to-end resolution recall. Report supported-subset
recall additionally with its explicit denominator; it must not replace the
end-to-end figure. Cases whose true target cannot be annotated have a separate
unknown ledger with construct-detection counts and reasons, not invented edges.
Abstention, unsupported syntax and scan failure must remain visible.

## Acceptance conditions

1. The absent-tool run produces actual fallback measurements for every required
   language, with TP/FP/FN, precision, recall, unresolved counts and corpus size.
   Missing language results are incomplete acceptance; measured values are never
   replaced by forecasts or synthetic passing observations.
2. The declared basic-syntax fixture suite has zero FP and FN in extraction and
   resolvable file edges. Unresolved challenge cases report their uncertainty;
   every expected challenge signal is detected. This fixture target is not a claim
   of 100% accuracy on arbitrary repositories.
3. Held-out measurements include failures and stage/language/syntax breakdowns.
   Real-corpus release thresholds remain to be set and must be frozen before
   qualification. Record target, measured result and any gap separately.
4. Unknown relationships, parser failures and unavailable analysis cannot authorize
   removing a proof input or skipping a required check. Related uncertainty blocks
   that scope-reduction proposal while independent authorized work can continue.
5. Source, configuration, analyzer/rule version and provider changes invalidate
   affected derived analysis. Added/deleted files and changed imports are covered.
   Cached analysis is a projection, not a second canonical authority.
6. On the same corpus, compare fallback and ast-grep accuracy and duration. Report
   the fallback's own reference-based scores, not only agreement with ast-grep.
   For proof-efficiency claims, separately measure repeated checks, stack starts
   and actual elapsed time against a declared baseline; scan speed is not proof
   of development-time savings.

## Qualification deliverables

Retain the corpus/reference manifest and hashes, per-case outputs and mismatches,
the absent-tool subprocess log, machine-readable metrics and a concise human
report. Record interpreter/platform, source revision, analyzer/rule/configuration
identity, provider, cache state, commands, actual results and limitations. Evidence
is staged outside canonical inputs and ingested through the normal proof workflow.

Qualification results are recorded separately in `qualification.md` and the
source-bound `proof-output/proof-efficiency/` artifacts. The small public pilot
qualifies measured advisory output only; broader production accuracy targets
and development-time savings remain unqualified.
