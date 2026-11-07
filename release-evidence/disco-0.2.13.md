# Disco 0.2.13 testing release

This unsigned Apple silicon testing release combines the latest reviewed local
Cell QC presentation with import and epoch/protocol interaction repairs.

- Imports retain visible transfer/job progress; stalled monitor recovery no longer
  leaves the queue waiting indefinitely. Uncertain uploads are not automatically retried.
- Command/Shift epoch selection retains its range origin across temporary reads.
  Counted Include/Exclude and bulk tag add/remove target explicit selected epochs.
- Protocol creation, renaming and saved-query changes refresh their visible state.
  Search previews renew after structural changes while apply authority stays exact.
- Cell QC shows recorded date, cell and rig above Cell type, Bath temperature and
  Pipette solution, with recorded additions when present and an expansion hint.
- Metadata field names and field IDs have separate copy controls.
- Pinned protocols can remove selected epochs in list/tree views and restore them
  with Undo. The neutral selected toolbar counts the distinct cells and epochs in the
  selection, without addition signs. It includes full-view/cell selection and a named,
  counted removal confirmation. Removing membership leaves recordings, other pins and existing exports
  intact; future exports follow the updated membership. Workbench keeps one
  Deselect all action in its main selection toolbar, including tree-selection reset.

The existing cell-specific Overview, recorded cell-type icons, individually paged
QC protocols, temperature/solution displays, exact-epoch UUID entry and prepared
H5 reader are retained. The final Cell QC branch is integrated through 72eabc1;
import/interaction integration comes from the locally tested 0.2.11 source 70a9bdb.

Publication is contingent on the exact-source full regression and million-row
workflows plus the selected complete native candidate checks. Their immutable
receipts and any retained failures are attached by the gated publisher. Local
0.2.11 evidence alone does not qualify these combined bytes.

Version 0.2.13 supersedes the unpublished local 0.2.12 installation (source
`d26af9cde0fe0603e6bcc4bd217ddef229c01b3f`). The installed local version keeps its
artifact identity; GitHub-built update bytes use this new version. No scientific metadata is retyped, and the rig filename
fallback is display-only. This is unsigned/unnotarized testing software, not
production, Intel or universal macOS runtime qualification.

## Earlier unpublished candidate


Source `96fbace23130deca0289f52c13cc1c4b3dfb9a96` was not published.
[Full regression](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/42418475974)
failed a fixture that copied a protocol definition without giving it a matching
managed file. The production integrity refusal remained correct.
[Browser qualification](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/42418477659)
stopped during compatibility preflight: two visible Deselect all controls made
the unscoped Workbench locator ambiguous. Million-row browser measurements were
not started. Local native removal/Undo and toolbar checks passed but do not
replace these failed gates.

The follow-up candidate removes the duplicate incoming action, scopes the harness
to the existing named Workbench region, and fixes the independent protocol fixture.
Comparison cases, correctness oracles and thresholds stay unchanged; the earlier source commit and failed receipts remain available.

The scientist explicitly requested keeping version 0.2.13. Before replacing the
unpublished candidate tag, the release was verified absent and the superseded
build was cancelled. The earlier source remains in Git history and its CI runs;
no published release, installed 0.2.13 app, or release asset was overwritten.

## Published and installed result

Published [desktop-test-v0.2.13](https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.2.13)
contains clean source `18e86dedd5d59918831807a926ac540b4c30f670`.
The later evidence-only commit does not change the archive or installed source.

- [Full regression 42420252228](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/42420252228)
  passed, including 1,661 frontend tests, 2,578 Python tests (55 conditional skips),
  architecture checks, native project lifecycle, and mapped desktop checks.
- [Fixed core and everyday million 42420254653](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/42420254653)
  passed its backend, browser workflow, macOS trace, and aggregate comparisons.
  Pinned baseline `a16c915` and preceding candidate `96fbace` used the same current
  harness; all retained comparison receipts report no review-required flags.
- [Desktop candidate 42420236274](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/42420236274)
  passed all five native suites: launch/persistence, updater, database, packaging,
  and extended UI. Each suite verified the same saved archive.
- [Gated publication 42425145766](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/42425145766)
  rechecked the exact source, archive, signature, runtime manifest, and native
  closure, then published those bytes without rebuilding.

Before CI qualification, the final source was clicked through in an isolated
native fixture: automatic import/review, cell/epoch selection counts, a single
Workbench Deselect all action, list/tree selection reset, hidden singleton toolbar,
multiple-selection toolbar, removal confirmation/cancellation, removal, and Undo.
The restored count and trace were checked. Earlier palette and independent native
reviews remain attributed to their exact earlier source commits.

The actual installed 0.2.12 app found 0.2.13 through App Updates, downloaded the
GitHub ZIP, verified it, and restarted into the published managed generation.
The project, protocol, incoming Workbench review, pending counts, focused epoch,
trace window and metadata pane returned. Sidebar visibility was restored manually.
No research-data edits were used for this check.

The runtime manager intentionally kept its compatible canonical launcher at the
prior bundle version. After the in-app update completed, the supported installer
aligned `~/Applications/Disco.app` with the already activated published generation,
without closing the active session, and retained 0.2.12 for rollback. The installed
and running runtime-manifest, ASAR and native-helper hashes match the publication
audit. The downloaded ZIP SHA-256 is
`8bf3364130a295387dfe2e5c60180f13d0edb4ad60cd84a6dece335f3faf5a1c`.

Cleanup removed 37 remaining task-owned disposable paths, in addition to three
earlier preview replacements and two obsolete 0.2.11 bundles retired during the
update/promotion: 42 artifacts in this release phase. Two owned baseline worktrees
were archived. The final cleanup's measured free-space increase was
4,838,817,792 bytes (4.51 GiB); this is an observed APFS change, not a sum of folder
sizes. The cleanup helper completed successfully. Current 0.2.13, verified 0.2.12
rollback copies, source, raw evidence, shared frontend dependencies and the small
reusable license cache are retained.

See [the compact qualification record](disco-0.2.13-qualification.json).
Raw JSON, logs and native fixture receipts remain locally under
`benchmarks/results/release-0.2.13-18e86de/`; research identifiers are kept only in
ignored local receipts. Earlier failed/cancelled runs remain preserved above.
