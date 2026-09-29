# Reusable query methods

Rieke OS distinguishes three records:

- A **query preset** is a named method: a typed predicate and ordered tree splits. Running it evaluates the current active project catalog, including eligible newly imported recordings. Saving a preset does not add epochs to a protocol or create an export.
- A **selection revision** records the predicate plus exact epoch UUIDs and metadata fingerprints at that time. This is the evidence used when comparing or applying a working dataset.
- An **export** is a separate, versioned downstream artifact with its original selection and provenance. Running or editing a preset never rewrites an earlier export.

Project presets live in the `recording_workspace.SearchPreset` DataJoint table, scoped by project UUID. Each create/update also inserts an immutable `SearchPresetVersion` and an audit event in the same database transaction. Updates require the current version; a stale editor receives HTTP 409 instead of overwriting another save. Pin state, name, description, predicate, and split settings are persisted in the project database. Recent unsaved searches and legacy device shortcuts remain browser-local conveniences.

The app validates predicate field names, operators, value types, and tree split identifiers against the current catalog. Conditions are structured JSON; arbitrary SQL, Python, MATLAB, and other executable query strings are not accepted. Validation and preset storage do not load response waveforms. Query runs retain the existing paged epoch browser and lazy trace requests.

## HTTP contract

All writes use the application's existing local-origin write guard.

- `GET /api/search-presets?limit=100&offset=0`: project recipes with `total` and `has_more`.
- `POST /api/search-presets`: create from `name`, optional `description`, `predicate`, `splits`, and boolean `pinned`.
- `GET /api/search-presets/<uuid>`: current project recipe.
- `PUT /api/search-presets/<uuid>`: update those same fields, with `expected_version`.
- `GET /api/search-presets/<uuid>/download?version=<version>`: download that exact query version as portable JSON.
- `GET /api/search-presets/<uuid>/versions/<version>`: immutable historical recipe; not a frozen epoch selection.

Example method:

```json
{
  "name": "History noise · cutoff 100",
  "description": "Current history-noise recordings at the recorded cutoff setting.",
  "predicate": {
    "all": [
      {"field": "protocol", "operator": "contains", "value": "History"},
      {"field": "parameters/frequencyCutoff", "operator": "eq", "value": 100}
    ]
  },
  "splits": "date,cell,parameters/frequencyCutoff",
  "pinned": true
}
```

Portable query JSON carries the method, not raw recordings, credentials, a SQL database, or frozen membership. Its `catalog_ref` is relative to the destination managed project. An imported method must be validated against that project's ingested metadata; fields can legitimately differ between labs or parser versions. A zero-match query is not a failed import.

To preserve complete project history, back up the project database as well as the managed files and all referenced raw recordings. Copying the repository or downloading a query recipe alone does not back up scientific data. See the workspace setup guide for reproducible application installation and the managed-project portability boundaries.

## Last-run information

An explicit search run (`POST /api/explore/run`) stores its completion time, matched epoch count, unique matching cell UUID count, actor, and source/tree revision with an audit event. Project presets join this compact record by the normalized predicate. Pinning, renaming, background tree previews, and failed runs do not advance it. These are historical counts; rerunning evaluates current data. Older searches with no count evidence display an unavailable value rather than an inferred cell count.

## Duplicate prevention and versions

Saved-predicate identity ignores AND/OR condition order, redundant conditions, singleton wrappers, and numeric integer/float spelling. Array equality remains ordered and booleans remain distinct from numbers. This normalization does not attempt arbitrary logical theorem proving. Saving the same conditions again reuses the existing entry; changes to its name, description, pin, or tree settings use version-checked updates. A no-op save does not create a version. Changed conditions can explicitly update the selected entry or become a new saved predicate, provided they do not duplicate another entry. Creation and updates are serialized per project to prevent simultaneous duplicate creates. The UI exposes prior versions for review in the predicate editor.
