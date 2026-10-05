# Typed query presentation

Start with `ui/PredicateBuilder.jsx` for editable conditions, `ui/PredicateDialog.jsx`
for dialog lifetime, `ui/ScopedPredicateFilter.jsx` / `ui/ProtocolViewFilter.jsx` for
scoped application, and `ui/TreeBuilder.jsx` / `ui/JointGroupingEditor.jsx` for ordered
split recipes. These public entries retain their props and callbacks. Pure public
entries `ui/predicateState.js` and `ui/predicateEditor.js` own typed draft compilation
and editing; `predicateIdentity.js`, `predicateFieldPresentation.js`,
`predicateValueSuggestions.js`, `protocolViewFilter.js` and `jointGrouping.js`
retain identity, labels, suggestions, scoped filters and joint recipe operations.

## Contract

Field IDs are exact recorded registry paths. Compilation preserves string, finite
safe number, boolean, null and JSON array distinctions; invalid numbers, object
list values and unavailable fields/operators refuse with actionable errors.
`exists`, `missing` and `is_null` carry no value. Ordering requires numbers.
Preserve six nested groups, 100 conditions/group and 100 list-value limits.
Joint recipes retain two to six unique nonnested components and their order;
split recipes retain the eight-level maximum. Labels and units are presentation
metadata, never canonical group keys or unit conversion.

Draft edits are in-process and perform no scientific transaction. Dialog and
suggestion reads use remote but owned metadata endpoints through existing request
and resource adapters. Preserve their scoped registry identity, request cancellation
and mounted lifetime. App/callers apply and save; backend evaluation and canonical
grouping remain authoritative. A compiled predicate does not prove completeness.

## Factoring decision

The deletion test distinguishes compiler/editor knowledge from UI lifetime:
deleting these public helpers would repeat validation and recipe rules in callers.
KEEP these file-level interfaces. A combined compiler/filter/dialog controller would
make pure callers learn React lifetime and remote metadata rules. Folder locality
reduces navigation cost; it does not add behavioral depth or justify a new adapter.
In-process transformations and remote but owned reads remain separate, with tests
at each existing public seam. The reader first chooses an editor or compiler entry,
then follows the helper needed for that responsibility; no universal facade is added.

From `workspace-app`, run these executable public examples and retained lifetimes:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/typed-query/*.test.js src/predicateDialogLifecycle.test.js src/scopedPredicateLifecycle.test.js src/scopedPredicateFilter.test.js src/protocolPredicateWorkflow.test.js
```

The colocated predicate tests cover exact typed values/refusal, registry validity,
identity, suggestions and ordered grouping. Mounted tests exercise actual editors
and stale suggestion/application behavior. Ledger: `typed-query-presentation`.

## Maintenance and evidence

Use the named file entries directly; there is no barrel, compatibility forwarding
module, or newly private export. The interface includes accepted types, identity,
ordering, freshness, errors and lifetime; a lower export count is not the goal.
The executable examples above use the same public seam as callers. Preserve the
original tests; this organization does not replace them with implementation tests.

Read this guide and the relevant entry before editing. Agree on changes to
scientific meaning, authority, request identity or lifetime before implementation.
Keep local changes within those contracts, run the scoped examples and retained
composition tests, and obtain independent source review. The integration owner
updates the existing catalog, ledger and path companion and runs the coordinated
import/build checks. Benchmark links in the ledger are historical/indirect;
relocation establishes neither new performance nor native qualification. Browser
layout/paint, native data reads and full backend qualification remain separate.
