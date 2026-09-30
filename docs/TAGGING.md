# Cell and epoch tags

Tags are project annotations stored in DataJoint. Each annotation has an exact target UUID, a target kind (`cell` or `epoch`), a local author profile, and a revision. Changes are recorded in project activity. Profiles identify the claimed author; they are not authenticated accounts.

In the epoch browser, **Tags** lets you tag the focused epoch, its entire cell, or explicitly selected epochs. The whole-cell action applies to every epoch with that cell UUID, including epochs in other protocols and later imports. It does not use the visible cell label, date, tree position, or current predicate membership. Direct epoch tags and inherited cell tags are shown separately. Choose the author when opening a project or using the profile button at the bottom of the project rail. Tagging and tag import remain disabled until an author is explicitly selected; the OS username is only a suggestion.

Use **Cell tags**, **Epoch tags**, or **Effective tags** in Search predicate. Effective tags combine direct epoch and inherited cell annotations. Acquisition keywords and the older protocol-specific dataset tags remain separate fields. Tag chips can open an exact tag predicate.

## Portable tag JSON

Use **Export tags** to save a portable JSON document containing exact cell and
epoch UUIDs and each tag's author. An external analysis tool can add entries
using those identities. In Rieke OS, choose **Import tags**, select the JSON,
review its additions, and import. Import is additive: matching authored tags are
unchanged, and omitted input entries do not delete saved tags. Removing a tag is
an explicit edit by its author.

The preview validates target kinds, UUIDs, source identities and author
attribution against the project. Unknown or duplicate targets, conflicting
author identities, and stale previews are rejected. Cell labels, dates, row
numbers and tree positions never identify targets. Raw H5 files are unchanged.
Supported legacy hierarchical tag JSON remains a data-import format.

## Tags and inclusion decisions

Inclusion decisions determine the epochs in an analysis selection; authored
tags are separate annotations. Rieke OS supports its portable JSON selection
mask for saving or importing exact epoch decisions. It does not import or watch
MATLAB `.ugm` files or provide an interactive MATLAB companion.

SQLite, MATLAB data and reference JSON exports include a frozen annotation
snapshot. Later edits do not rewrite earlier exports. Historical exports and
previously committed inclusion decisions remain readable.

## Automatic tags from Wheeler and other services

Use **Export log → Local export folder → Copy folder path** to link an external service to this project's single `exports/` directory. All export formats share this root, with one UUID subfolder per export and a root README explaining how results return. There is no need to point the service at acquisition data folders to return tags or selection masks.

SQLite exports now have a writable return area beside the frozen database:

```text
exports/<export_uuid>/
  recordings.sqlite
  annotation-return.json
  annotations/incoming/
  annotations/receipts/
```

Open the export folder shown under **External tags** in the app header. Wheeler reads `recordings.sqlite`, obtains exact epoch/cell UUIDs, and writes additions into `annotations/incoming`. It must not edit the SQLite snapshot. The manifest lists allowed targets, source hashes, and an example message. Existing registered SQLite exports gain the return area automatically when checked.

The included helper submits tags without needing a running app or database connection:

```sh
python3 python/workspace_external_tags.py /path/to/project/exports/EXPORT_UUID \
  --author Wheeler --target-kind epoch --uuid EPOCH_UUID \
  --tag publication:paper-2026-01
```

Repeat `--uuid` and `--tag` for multiple targets/tags. `--profile-uuid` can supply an existing stable author identity; otherwise the helper derives one deterministically from the exact author name. Author names are local attribution claims, not authenticated accounts. Use `--target-kind cell` only when all epochs of that cell, including future ones, should inherit the tag.

The receiving app scans on page open/reload, about every three seconds while visible, and when returning to the window. **External tags** shows only the last check and latest successful import. Its refresh icon checks immediately; an error appears only when attention is needed. Tags appear in the normal annotation UI and tag searches. No dataset reimport or manual tag preview is needed. Closed pages receive queued messages on reopen; no always-running daemon is installed.

Each message needs a fresh `message_uuid` and a filename matching it. Publish complete files atomically; the helper does this for you. Repeated delivery of the same message is safe, and saved receipts prevent an old message from restoring a tag removed later. Submissions only add tags; missing tags or missing folders never remove anything. Receipts and additions share one database transaction. Unsupported/foreign identities are displayed as errors without guessing a match.

This scans the original registered project export folders. If Wheeler works on a copy elsewhere, deliver or synchronize its completed JSON messages into the original export's `annotations/incoming` folder. Downloading a SQLite file alone does not create a communication channel back to the app. External actors can query current tags through the existing annotation API; an old SQLite export retains its historical snapshot.
