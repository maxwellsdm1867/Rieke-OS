# Tag scope and user attribution

Reviewed 2026-09-28. This records the integration contract, not an implemented migration.

## Reference behavior

Upstream: https://github.com/SamarjitK/datajoint
Local fork: /Users/maxwellsdm/Documents/GitHub/datajoint (origin maxwellsdm1867, upstream SamarjitK).

- next-app/api/schema.py:255: Tags attaches tag text and user to a table/object identity and its H5 UUID.
- next-app/api/helpers/query.py:106–147: tag predicates restrict the selected hierarchy level; joins carry matching cells down to their epochs.
- query.py:357–375: tagging selected cells writes cell records, not duplicated epoch records. Current deletion lacks a user restriction; do not copy that ownership behavior.
- query.py:380–470: hierarchical JSON keyed by H5 UUID retains user/tag pairs. Push exports the current user's tags, pull imports other users, reset reloads all.
- src/app/components/results/CustomTreeItem.js:65: compound chips show tag plus author.
- src/app/components/setup/SetUser.js and api/app.py:189: selectable username; this is attribution, not authenticated identity.
- Local fork query.py:473 and ResultsViewer.js:145: .ugm import translates deselection into the current user's excluded tag. This local extension is not asserted to exist upstream.

## Current Rieke OS gaps

workspace_curation.py stores tags at project + protocol + epoch scope. Bulk selection applies that scope to explicit epoch UUIDs. It is not a durable cell tag. Events record an actor, but current routes use the operating-system USER. The tag list does not retain per-tag authorship. Predicates expose explicitly named protocol tag fields in workspace_tag_predicates.py. No selectable profile or shared cell/epoch annotation layer exists yet.

workspace_matlab_routes.py already validates .ugm against an exact completed export, source metadata, query and curation revisions. Inclusion updates are transactional, preserve tags and non-exported epochs, and log input hashes. Preserve these checks.

## Target semantics

| Entry | Stored target | Effective scope |
|---|---|---|
| Tag cell | project UUID + cell UUID | All epochs linked to that cell, across protocol datasets |
| Tag epoch | project UUID + epoch UUID | That epoch only |
| Tag selected epochs | explicit epoch UUID set | Only those selected epochs |
| Protocol curation | existing protocol + epoch IDs | Existing dataset-specific decisions remain separate |

Cell tags inherit through identity joins, not copied rows. Newly registered epochs linked to the same cell inherit automatically. A future epoch that belongs to a different cell named Cell1 must not inherit. Filtering a view must not silently narrow a cell-level tag to only its visible epochs.

Deleting a cell tag removes its inherited appearance; an independently authored epoch tag of the same text remains. Cell and epoch tags authored by different users remain distinguishable. Tags are annotations, not implicit include/exclude commands.

## Persistence and UI

Add explicit Profile and Annotation bookkeeping tables. Profile: UUID, display name, created/updated timestamps. Annotation: project, target kind, target UUID, author UUID, exact tag text, revision, created/updated timestamps, retired state. Use a unique target/author/tag constraint and append-only change events. Resolve active profiles per client session/request, not a single server-global username. Historical event names must remain interpretable if a profile is renamed.

Keep existing protocol tags in place with their original scope. Do not invent authors for historical tags or automatically promote them to cell annotations. Any explicit migration should preserve original event provenance and mark unknown authorship.

Use the far-left profile control to select/create a local profile. In cell details, show Cell tags and their affected epoch count; in epoch details, show Direct epoch tags and Inherited from cell. Chips show tag, scope and author without repeating long UUIDs. Inherited chips link to the parent cell editor. Suggestions come from persisted project tags; show existing authorship rather than duplicate chips silently.

Search predicate fields must distinguish Cell keywords, Epoch keywords, Effective tags, Author, and existing Protocol tags. Imported acquisition keywords remain identifiable as source metadata. Exact tag matching and text searching are different operators.

Export the annotation snapshot with target IDs, authors, scope, and revisions. Wheeler SQLite and MATLAB handoffs must distinguish inherited cell tags from direct epoch tags and from selection masks. Frozen exports do not change when later annotations change.

Mask imports should offer a preview of included/excluded counts, matched export and affected epochs. Apply only inclusion decisions to the intended protocol/export scope. Do not implement masks by deleting or overwriting user tags.

## Required validation before shipping

- Same Cell1 label on different dates never cross-tags.
- Cell tags appear on all linked epochs across protocol and predicate views, including later-added epochs.
- Direct epoch tags remain on only the intended epoch.
- Removing inherited tags preserves independent tags with identical text.
- Two users' same-text tags remain independently attributable.
- Concurrent edits reject stale revisions and log committed changes once.
- Cell/epoch/effective-tag and author predicates give exact UUID memberships.
- Both exports retain attribution and inheritance while old export snapshots stay unchanged.
- .ugm import preserves all tags, rejects unknown/mismatched/stale IDs and remains idempotent.
- Paged epoch views retrieve inherited annotations in batches; no per-epoch SQL round trips or waveform loads.
