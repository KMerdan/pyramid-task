# Frozen public source pilot v1

Read the manifest and provenance before scoring. Snapshots are unmodified and
must not be executed. They retain their upstream MIT licenses. Gold references
were annotated by reading the declarations and Rust module ownership before
running either extractor. Rust super and the inline test module belong to
lib.rs; unresolved predictions therefore remain resolution false negatives.

This six-file convenience sample is small. It does not qualify automatic scope
contraction or production-wide precision. No held-out tuning is allowed; changes
informed by its mismatches require a new held-out set for a fresh accuracy claim.
