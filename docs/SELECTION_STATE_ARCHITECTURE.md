# Rieke OS selection state

Rieke OS separates focused epochs, temporary bulk-action targets, saved protocol
membership, inclusion decisions, review markers and author-scoped tags. Selecting
an epoch for its trace or clearing bulk targets does not rewrite inclusion.

Protocol inclusion and optional review decisions are persisted with stable epoch
UUIDs and optimistic revision checks in the project database. Saved selections
and exports retain their exact query, source revisions, membership and provenance;
later edits do not rewrite an earlier export.

The supported portable inclusion format is Recording Selection Mask v1 JSON.
Export covers the entire protocol query. Import validates protocol UUID, exact
membership, source hashes and current query state before applying inclusion in
one audited transaction. Tags and review state are preserved separately.

MAT data export serializes data/provenance for standard analysis. Rieke OS has no
MATLAB interactive tree, launcher or UGM import/return workflow. Historical
MATLAB bundles remain downloadable as legacy artifacts.

See [quick start](RIEKE_OS_QUICK_START.md), [tagging](TAGGING.md),
[working datasets](PINNED_PROTOCOLS.md) and [storage](STORAGE_RECOVERY.md).
Implementation: `python/workspace_curation.py`, `python/workspace_explorer.py`,
`python/workspace_api.py`, and the React Inspector/epoch selection modules.
