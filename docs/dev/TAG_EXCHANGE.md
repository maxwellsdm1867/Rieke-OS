# Authored cell and epoch tags

RiekeOS shared annotations are separate from protocol inclusion/review and from raw acquisition keywords. Each tag belongs to an exact `(target_kind, target_uuid, profile_uuid)`; the text is case-sensitive. Cell tags inherit through the recorded cell UUID, without creating per-epoch tag rows. Profile names are local attribution, not authenticated identities.

Portable JSON uses `format: rieke-tag-exchange`, `version: 1`, `project_uuid`, and `entries`. Each entry contains `target_kind` (`cell` or `epoch`), `target_uuid`, optional `source_sha256`, and `tags: [{tag, profile_uuid, author_name}]`. Exports include empty entries so MATLAB can add tags to known exported targets. UUIDs are canonical lowercase strings. Labels such as “Cell1”, dates, numeric indices, tree order, and array positions are never identifiers.

Import is explicit preview followed by apply. The preview token binds normalized additions, current author/target revisions, current project, and source identities. Apply repeats validation under the shared annotation lock, checks the token, and performs one transaction with the audit event. It is additive: absent entries/tags never delete existing annotations. The selected importer profile is logged separately from the authors claimed by the file. Conflicting existing profile UUID/name pairs fail before apply. Unknown targets, wrong cell/epoch kinds, duplicate entries/tags, foreign source checksums, and stale revisions fail closed. A different origin project is shown as a warning and is allowed only when the exact acquisition UUIDs (and any supplied source hashes) match the current project. No raw files or protocol masks are modified.

Requests are bounded to 8 MiB, 2,000 author-target operations, 100 author profiles, and 100 tags per author/target. Registry reads are batched. Larger jobs must be split explicitly. Portable JSON is the lossless exchange format.

## Samarjit compatibility

The legacy DataJoint `next-app/api/helpers/query.py` `push_tags`/`pull_tags` format is an acquisition UUID hierarchy from experiment through animal, preparation, cell, epoch group, epoch block, and epoch. Each node has `tags: [[author_name, tag], ...]`.

Import resolves tagged cell/epoch nodes by exact registered UUID. Tagged unsupported levels fail explicitly; they are not silently dropped. Legacy author names receive deterministic imported profile UUIDs and are labelled as claims. Export reconstructs the actual hierarchy from SHA-verified imported metadata, including empty `tags` arrays at ancestors because the legacy traversal requires that key. It rejects unavailable ancestry and multiple profile UUIDs with the same author name, which the legacy format cannot distinguish. Samarjit does not preserve Rieke profile UUIDs or revisions. Its own pull/reset implementation deletes old SQL tags; Rieke imports intentionally do not perform those deletions.

## MATLAB

New EpicTree bundles include `annotations.json` and the same document in `recordings.mat` metadata. Helpers are copied into the bundle:

```matlab
doc = readWorkspaceTags('recordings.mat');
% Choose the exact epoch.h5_uuid or epoch.cellInfo.h5_uuid from the loaded tree.
doc = workspaceTag(doc, 'epoch', epoch.h5_uuid, 'good response', profileUuid, 'Scientist A');
writeWorkspaceTags(doc, 'matlab-tags.json');
```

The helper only edits targets already in that exported document, validates kind and UUID, and refuses overwrite when writing. Upload the returned JSON in RiekeOS, preview the exact additions, then apply. `readWorkspaceTags` also accepts portable JSON. Native GUI tagging uses the same document/helpers. Neither helper changes raw H5, tree selection, or SQL directly.

`.ugm` remains an inclusion mask keyed by epoch UUID. It is not an authored-tag format. Saving or importing a mask does not rewrite tags. MATLAB `.tags` preserves direct epoch tags and cell `.tags` preserves cell tags with author/profile/scope; protocol tags keep their separate `protocol` scope and blank author where no author was recorded. Full annotation/revision evidence is retained in `workspace_annotations_json`.

## SQLite handoffs

The existing v2 `epoch_tags` table continues to mean protocol-specific curation tags. Additive optional v2 tables `shared_annotations` and `annotation_revisions` retain exact target kind/UUID, author profile/name, tag text, and revisions including emptied tag sets. `example_queries.shared_tags` joins inherited cell and direct epoch tags without conflating them. Compressed `frozen_records` retains the complete per-epoch annotation snapshot. These tables have the same immutable-export triggers as existing handoff tables; later edits in RiekeOS do not change an old export.

## Validation

`python/tests/test_workspace_tag_exchange.py` covers exact identity with repeated cell labels, shuffled/subset entries, wrong kind/unknown/duplicate/source rejection, additive authorship, stale preview, real-store transaction rollback on audit failure, bounded registry reads, legacy hierarchy/checksum handling, and SQLite/MAT frozen annotations. `tests/test_workspace_tag_exchange.m` runs through the MATLAB MCP tool and covers JSON/MAT read, native edits, shuffled order, subset, duplicates, and wrong-kind/foreign identities. An additional disposable Python→native MATLAB→Python preview/apply roundtrip was run successfully; no production annotations were changed.
