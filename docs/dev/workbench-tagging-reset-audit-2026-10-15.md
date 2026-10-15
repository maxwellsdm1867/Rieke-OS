# Workbench tagging and view-reset audit

Branch: `codex/workbench-tagging-continuity`, isolated from the 0.1.15 publication
branch. Base: `e95186c7c2cf05de5ff69998e3fad2c119bb532c`. This work does not change
the release version or publish, install, merge or replace 0.1.15.

## Observed problem and reproduction

The installed app inspected on 2026-10-15 was version 0.1.14, source
`4de896f2e0b4ea966b5a428c3d2314f93fba935f`. Its Workbench filter panel showed
All cell types, All source groups and All epochs. The date branch was collapsed.
No tags, scientific selections, recordings or protocol membership were modified
in the user's project during investigation. Opening the date branch exposed its
three cell branches.

On a disposable SQL-double fixture, changing only the shared annotation revision
changed the queue and cumulative candidate UUID while the complete recipe epoch
membership stayed equal. The existing renderer replacement-candidate test confirms
that such replacement discards local selection and list/design navigation.
The new regression using actual SharedAnnotations epoch and cell tag saves fails
on the publication baseline at the candidate UUID assertion and passes on this
branch. This establishes the mechanism without claiming a native tag-save replay
on the user's database.

## Fix and audit findings

| Boundary | Unnecessary reset found | Result on this branch |
| --- | --- | --- |
| Cumulative preparation | General tag revision creates a new immutable candidate for identical contents | Versioned content identity reuses the verified candidate; full fresh authority still closes the operation |
| Legacy cumulative candidates | Switching only to a new content key would replace the first existing review after upgrade | Prefer the actor's current equivalent sealed candidate; preserve its original bytes and provenance |
| Selected view | Pause and context refresh discard the selected-view owner | Keep view intent, renew the exact UUID manifest, retain old token only with old inert context; visible retry on failure |
| Highlighted epochs | Every command-authority revision clears UUID highlights | Keep highlights for the identical annotation-independent cohort/view; commands still require fresh authority |
| Column tree | Authority change reloads root and loses path/scroll | Freshly reread the prior path/offsets; restore scroll only after current pages validate |
| Hierarchy tree | Authority change collapses expanded siblings | Reread the expanded pages with a fresh first revision; retained rows and actions stay inert until complete |
| Review details | Any refresh closes the details dialog | Close on project/protocol/candidate/actor change, while preserving all action readiness checks |
| Focus locator | A transient read failure clears the focused UUID | Retain the locator for explicit retry; fresh missing-membership responses and HTTP 404 still clear focus |

The full queue, candidate scope, draft version, source, binding, predicate annotation
and shared annotation witnesses remain current-action requirements. Reuse does not
copy merge consent, previews, pending operations, or author drafts across candidates.
Old operation replay stays exact. Missing/unknown content fields, incorrect sealed
membership or baseline identity cannot authorize reuse. The current-draft lookup
test includes 200 older candidates and verifies only its recipe is deserialized.
That is a bounded read-count test, not a large-history latency measurement.

## Boundaries and remaining audit follow-ups

- Actual changes to project, actor, cohort, filter, split order or confirmed
  membership still invalidate incompatible state. Cancelled selection commands,
  stale manifests and superseded request completions never become current again.
- Tag-dependent filters and annotation-dependent grouping still require current
  membership/group validation. Their value text alone cannot prove an unchanged
  visible UUID set. This branch does not freeze a tag-filter result across later
  tag changes; that would need an explicit bounded result-snapshot contract.
- Main Inspect and Search Predicate were inspected for related reset paths.
  Main's per-cell page identity still includes the read revision, and Search's
  presentation identity includes the preview revision. They can do extra reloads
  or resets after refresh. This branch's semantic continuity is deliberately
  limited to a verified frozen Workbench cohort, not applied to unproven live
  query results. These are follow-up audit findings, not claimed fixes.
- Revision-bound branch-command markers remain separate from selected UUIDs.
  Preserving a painted branch command must not implicitly replay a selection.

## Independent review and evidence

Independent design review approved separating candidate content from live authority
before implementation. Source review found and corrected two issues: an initially
hidden selected-view retry control and overly broad highlight retention for
tag-dependent filters. Final review found no remaining blocking issue in the
nine changed production owners, including effect cleanup, A-B-A rejection,
scope/loading gates, legacy reuse and immutable receipts. Lifecycle fingerprints
were updated only for those reviewed modules. A new explicit-revision regression also exposed a legacy frozen-column response gap: target and continuation-root revisions are now checked before adoption or attestation. The inherited publication workflow test received an exact-file/AST loader record after independent review; no loader or guard behavior changed.

Focused checks cover actual epoch/cell tag mutations, stale read/write rejection,
legacy and corrupt candidate reuse, manifest renewal/abort/failure, held preparation,
expanded rows, selections/highlights/focus/scroll, hierarchy siblings and column
paths, transient errors and confirmed absence. Evidence is retained locally in
`/Users/maxwellsdm/Documents/Codex/disco-workbench-tagging-evidence-2026-10-15`.
Full source checks and exact-commit core/million-query results are recorded with
the final handoff. Browser paint, native installed-app behavior, packaging and
release qualification remain separate.
