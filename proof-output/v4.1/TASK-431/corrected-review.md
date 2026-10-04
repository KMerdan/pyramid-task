# TASK-431 corrected candidate review

Pre-run input identity: a0b64aaf39b52908aa400c693d73796cbf352fabc05f2f796053f667e2d05f5a.
The corrected full suite ran 176 tests in 21.035 seconds and passed. It includes
six actual footprint/filesystem/public-CLI checks, the projection publication
fault-injection regression, and the legitimate amendment staging exclusion.

The earlier 175-test run failed two checks: publication fault injection targeted
the old writer, and the overlap rule incorrectly rejected amendment coverage.
Both failures remain in full-suite-first-failure.txt. The old five-test review
and capture remain preliminary evidence, not this final candidate's proof.

The public CLI compares all fixture file bytes and mtimes before/after. Failed
audit evidence remains failed and referenced. Bounded scans do not follow
symlinks or mutate files; partial scans, excluded directories, logical bytes
and unknown historical/handoff ownership remain explicit. Rooted/specific
input-output overlap rejects capture; whole-repository input can exclude
dedicated staging, and changing real source changes the fingerprint. Normal
queries do not scan the tree. No deletion, GC or extension-based inference.

Review is same-session source/test review, not an installed-host result. The
HTTP test emitted its existing temporary-file ResourceWarning, not a test failure.
