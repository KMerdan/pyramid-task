# Read-only proof analysis

Use these optional queries when broad inputs or repeated ancestor proof are costly:

```bash
python3 ../../scripts/pyramid.py inspect --project <root> --proof-analysis <node> --json
python3 ../../scripts/pyramid.py inspect --project <root> --proof-analysis <node> --source-dependencies --json
```

The first query uses canonical input matching, counts distinct producer families,
lists consumers and declared write overlap, and reports current proof blockers
and reusable runs. Shared consumers do not multiply producer counts. Overlap
predicts fingerprint churn; it does not prove which dependency is necessary.
Future files and runtime relationships remain unknown. It does not run checks.

The second query extracts references only from matching JS/JSX/TS/TSX/Rust/Python
source files. Python's standard-library analyzer is the default and does not
discover or launch external tools. No ast-grep installation is required. Explicit
`--analysis-provider ast-grep` or `--analysis-provider auto` tries verified
`ast-grep` or its `sg` alias, then falls back to Python. An unrelated Unix `sg`
is rejected. Missing tools,
incompatible executables, probe failures, scan failures and timeouts retain
diagnostics. It does not install tools or execute repository source/build scripts.
`--analysis-provider python` selects the default explicitly. Qualification also
exercises explicit `auto` in a fresh process with neither executable discoverable;
selecting Python alone does not qualify the optional adapter's fallback path.

Both adapters emit `dependency-analysis.schema.json`; proof projection uses
`proof-analysis.schema.json`. Inspect provider/version, scan coverage, diagnostics,
unresolved references and dependencies outside inputs together. An outside edge
can reveal a missing input. A missing edge cannot justify removing one.
`scan.complete` means the selected file scan completed within its bounds, not
that parsing or semantic dependency discovery is complete. No canonical mutation
or automatic scope contraction occurs.

## Supported subset and limits

The fallback is a finite JS/TS/Rust lexer and Python's stdlib AST. It handles
static/type imports, re-exports, literal require/dynamic imports, Rust file
modules, grouped uses, path attributes and literal includes. The AST adapter
supplies syntax ranges and shares normalization/resolution with the fallback;
it is not a TypeScript compiler or Rust name resolver.

Resolution covers unambiguous relative JS/TS files, nearest plain-JSON ts/jsconfig
path aliases, `.js` to TS alternatives and conventional Rust module files/basic
crate/self/super module ownership. A bounded declared Rust module tree resolves
parent modules and inline-module declarations/symbols to their defining files;
plain unreferenced filenames do not establish a Rust module. Inherited/JSONC
configuration, package exports, bundler plugins, Rust symbol re-exports and
custom Cargo entry paths remain unresolved. JSX expressions, computed paths, conditional compilation, macros,
generated inputs and ambiguity retain uncertainty. The lexer does not validate
every malformed program. Complex generics, regex and markup can affect guesses.

Default file/detail limit is 1,000; `--analysis-limit` accepts 1–10,000. Source
files/configs are capped at 1 MiB, selected source totals at 16 MiB, ast output at
8 MiB and its invocation at 10 seconds. Skips/truncation are reported. Traversal
returns one-hop edges. Rust ownership indexing additionally reads at most 256
module files / 4 MiB / 32 levels; supporting file hashes enter identity and
indexing failures make the scan incomplete. Cache is disabled. Identity includes source, observed resolution
candidates, config hashes, provider/version and rules; relevant additions/deletions
or edits change identity. This never replaces proof's file fingerprint.

## Measured accuracy

```bash
python3 ../../scripts/pyramid_benchmark.py --manifest <frozen-manifest.json> --provider python
```

Qualify absence in a fresh subprocess with an empty executable search path and
absolute interpreter and explicit `--provider auto`. Do not change host
installation. Compare explicit `--provider ast-grep` on the same frozen manifest.
Independently annotate gold before scoring. Typed
reference identity is `(source, kind, specifier, line)`; edge identity is
`(source, kind, target, line)`. Deduplicate each stage separately. Columns remain
in output but v1 scoring uses lines. Known unresolved edges are FN. Zero
denominators are JSON null/N/A. Unknown targets have a construct-detection ledger.

Metrics use `dependency-analysis.schema.json#/$defs/metrics`, with per-language
and syntax-family TP/FP/FN, precision/recall and mismatch locations. Frozen corpora
are in `tests/fixtures/dependencies/`. The six-file public pilot from three MIT
projects is not representative sampling. The v1 pilot had 3 Rust ownership FN;
v2 fixes those cases and treats that pilot as regression data. A fresh six-file
`heldout-v2` set still has 2 Rust re-export resolution FN: precision 100%, recall
50% (2 TP / 0 FP / 2 FN). Both providers share this resolver limitation. Other
extraction denominators are small; no local gold edges means N/A resolution. Broad release thresholds
remain unset. These scores qualify advisory reporting only. Tuning using pilot
mismatches requires new held-out sources.

## Agent decisions

Review command scope and true dependencies before proposing an input change.
Keep shared schema/config/generated dependencies affecting the claim. A full
regression suite elsewhere alone cannot justify dropping them. Use guarded
replan/amendment and establish fresh affected proof. Refresh labels do not waive
inspection blockers. Parallel implementation still needs dependency, write scope
and resource coordination. Measure actual check/stack counts and elapsed time
separately before claiming development speedup.
