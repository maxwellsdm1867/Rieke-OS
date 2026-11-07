# Disco 0.2.12 local testing installation

This unpublished unsigned Apple silicon local installation combines the latest reviewed local
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
  with Undo. The selected toolbar includes full-view/cell selection and a named,
  counted removal confirmation. Removing membership leaves recordings, other pins and existing exports
  intact; future exports follow the updated membership.

The existing cell-specific Overview, recorded cell-type icons, individually paged
QC protocols, temperature/solution displays, exact-epoch UUID entry and prepared
H5 reader are retained. The final Cell QC branch is integrated through 72eabc1;
import/interaction integration comes from the locally tested 0.2.11 source 70a9bdb.

Publication is contingent on the exact-source full regression and million-row
workflows plus the selected complete native candidate checks. Their immutable
receipts and any retained failures are attached by the gated publisher. Local
0.2.11 evidence alone does not qualify these combined bytes.

Version 0.2.12 supersedes the unpublished local 0.2.11 installation; 0.2.11's
identity is not reused. No scientific metadata is retyped, and the rig filename
fallback is display-only. This is unsigned/unnotarized testing software, not
production, Intel or universal macOS runtime qualification.

Installed locally from `d26af9cde0fe0603e6bcc4bd217ddef229c01b3f` on 2026-11-07.
No 0.2.12 GitHub release was published. Follow-up presentation changes and the
GitHub updater qualification use 0.2.13; do not reuse the 0.2.12 artifact identity.
