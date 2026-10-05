# Project preferences and query presets

[projectPreferences.js](projectPreferences.js) exposes `createProjectPreferenceClient` and storage keys.
[useProjectPreference.js](useProjectPreference.js) owns its React subscription, shared per-project client
map and draft-saver registration. [projectSearchPresets.js](projectSearchPresets.js) owns versioned saved
query payloads/portable recipes; [searchPresets.js](searchPresets.js) owns recent-search identity and
display summaries. [ui/SearchPresets.jsx](ui/SearchPresets.jsx) presents entries and explicit callbacks.
The persistence, query-policy and UI entries remain independently callable.

## Contracts and dependencies

Hydrate before writing. Project identity, response format/version and per-field
revisions remain mandatory. Browser storage is a cache and one-time legacy source;
a field is acknowledged only after a saved receipt. Missing portable preferences
must not silently adopt another browser's values. Updates serialize, preserve
visible unsaved edits and refuse flush with unsaved errors. An optimistic-conflict
retry reads the current receipt and reapplies the change once. Refresh must not
overwrite unsaved local edits. Keep the hook's current client-map lifetime,
subscription cleanup, focus/storage refresh and pre-effect visible-scope gate.

A query preset stores predicates/layout, never a frozen epoch selection. Imported
v1 recipes are at most 1 MiB and target the current catalog. Typed predicates retain
numbers/strings/booleans/null and exact safe-number restrictions; imported values
and node/depth/list limits stay unchanged. Saved receipts require preset identity
and positive safe version. Recent-search identity uses the existing typed-query
owner, preserves pins and strips epoch payloads. Backend predicate evaluation and
scientific membership remain outside this folder.

Pure keys/recipes are in-process; storage/events are local-substitutable; preference
and preset endpoints are remote but owned. The deletion test favors KEEP for the
client, React binding and recipe helpers: combining them would impose subscriptions
and persistence preconditions on pure query callers. Removing the client would
spread hydrate/CAS/unsaved-state rules. No new facade or singleton is introduced.

## Executable public examples

The colocated client tests use a controlled versioned backend and storage, including
conflicts, legacy migration and unsaved edits. Recipe/history tests exercise the
same public functions as callers and refuse frozen membership.

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/project-preferences/*.test.js src/scopedPredicateLifecycle.test.js src/requested-summaries/requestedSummariesLifecycle.test.js
```

## Change and evidence procedure

Use the named file entries directly. Each keeps its existing exports and caller
contract; no barrel, forwarding layer or private demotion is introduced. The goal
is a clear interface with progressive disclosure of the responsibilities below,
not fewer exports or fewer lines. Co-location improves locality; moving these files
does not by itself establish deeper behavior or a performance improvement.

Read the relevant entry and executable public examples before editing. Preserve
identity, scientific meaning, errors, ordering and lifetime. Review any proposed
contract or runtime behavior change before implementation. Keep the existing tests
and their public interfaces; do not import test support into production. Root
integration owns catalog/ledger/navigation updates and aggregate frontend checks.
Run the listed commands from `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset,
only in the coordinated test lane. Native/packaged behavior, actual ingestion,
backend durability and performance remain separately qualified; these examples
use owned synthetic values and do not authorize deferred/native fixtures.
