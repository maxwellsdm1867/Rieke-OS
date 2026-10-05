# Python named public entries: bounded reader design

Status: DESIGN ONLY, awaiting root review. Source baseline
`50ff9bd77b72c7a4e39444b4f2c653cbb0a27307`. No reader, catalog, application,
fixture, runtime, packaging or benchmark change is included. No tests executed.
The completed organization survey supplies the selected owners; this is not a
resurvey or permission to run native, HTTP, service or scientific fixtures.

## Decision and actual need

Add an explicitly versioned v5 named-file mode to the existing Python policy,
while keeping v4 and the existing P04 initializer mode unchanged. Do not replace
substantive modules with initializer reexports to satisfy the guard. First build
and review an inert-fixture reader increment; actual owner adoption remains a
separate gate. If preserving the existing module usages needs general dataflow or
reflection analysis, retain those owners at their current paths instead.

Concrete proposed owners supplied by workers:

- `disco.backup`: backup_scheduler, recovery_generation, recovery_store,
  state_snapshot. Its initializer must not import `disco.recovery`, whose current
  P04 initializer eagerly reaches Flask.
- `disco.decisions`: annotations, author_preferences, annotation_groups, curation,
  external_tags, tag_exchange.
- `disco.projects`: datastore_deletion, datastores, folder_browser, migration,
  project_database, project_preferences, project_validation, recording_files,
  storage.
- `disco.workbench`: candidate_exports, diff, recipes, suggestions, workbench,
  workbench_exports, workbench_pending.
- `disco.metadata`: cache_lifecycle, disk_index, explore_queries, metadata_objects,
  projection_cache, search, typed_index, typed_lifecycle, typed_query.

These 35 existing named files have independent useful interfaces. Their functions,
classes, constants and intentionally used underscore bindings retain meaning.
Grouping improves discovery; it does not itself improve depth. A package-wide
facade would increase coupling and obscure source-witness identity. In particular,
`workspace_typed_lifecycle.py:48` hashes the actual typed-index/query leaf
`module.__file__`; `workspace_service.py:207-208,497-498` does the same for other
source witnesses. Those must never silently hash an initializer instead.

The codebase-design SKILL.md, DEEPENING.md and improve-codebase-architecture
SKILL.md were read. Deletion test: removing substantive backup/query/decision
modules redistributes behavior to callers; removing a proposed facade removes
only forwarding. The guard remains an in-process AST/source-file checker with
local-substitutable disposable source/Git fixtures. It must not import the remote
owned/scientific modules it checks. No new port or external adapter is justified.

## Schema: two exact record shapes, no implicit migration

Catalog v5 accepts the current v4 owner record verbatim:

```json
{"contract_id":"p04-mutation-recovery","root":"python/disco/recovery",
 "public_module":"disco.recovery","public_entry":"python/disco/recovery/__init__.py",
 "public_exports":[{"name":"register_mutation_recovery","from":"python/disco/recovery/mutation_outcomes.py"}],
 "private_test_edges":[]}
```

Its validation and enforcement remain exactly the old branch. Catalog versions
1–4 retain all old semantics; a v4 catalog containing new fields must fail. v5 adds
one mutually exclusive record shape (illustrative fixture exports below, not a
complete real backup catalog):

```json
{"contract_id":"backup","root":"python/disco/backup",
 "public_entries":[
   {"path":"python/disco/backup/state_snapshot.py",
    "module":"disco.backup.state_snapshot",
    "exports":["TABLES","capture","atomic_write","save"]}
 ],"private_test_edges":[]}
```

Every entry is an exact existing `.py` file immediately beneath its owner root,
not `__init__.py`, a test or another owner's file. `module` must exactly equal its
canonical source-root-relative dotted identity. No wildcard, directory entry,
module alias, duplicate path/identity/export, overlapping owner, symlink or path
escape. Restrict v5's first increment to direct leaf files; nested public packages
are unneeded by all 35 candidates and remain unsupported. Different public
entries may legitimately have the same symbol name.

The root and every ancestor have a regular docstring-only (or empty) initializer.
No namespace packages, imports, assignments, dynamic attributes or facade exports.
Each initializer and production file still needs exactly one ownership allow rule;
existing local test roots, mapping, private-test-edge accounting, path hashes and
all-source classification remain mandatory. All unlisted production files remain
private, including future files. Existing P04 private-test semantics do not change.

`exports` is the finite reviewed module attribute/import allowlist, including
intentional underscore names and imported dependencies needed by existing callers
or tests. No prefix-based privacy inference or source `__all__` is imposed. Each
listed name must actually bind at module scope; annotations without a value and
comprehension locals do not count. The reader checks exact declared access, not
that every lexical helper must be declared public. Adding an unlisted helper is
allowed internally; using it across the seam fails. Extra public capabilities
require a catalog change/review. A name that resolves to a local imported module
or symbol must also respect that target's ownership and public export policy;
listing an alias cannot launder a private dependency. Existing explicit imported
public bindings may be retained when reviewed; undeclared downstream shims still
fail. Imported third-party objects remain external values, not new owned modules.

## Import and attribute behavior

Support these canonical forms without changing the actual Python module object:

```python
import disco.backup.state_snapshot as snapshot
from disco.backup import state_snapshot as snapshot
from disco.backup.state_snapshot import save as save_snapshot
# Standard fully-qualified import is also resolvable as a namespace chain:
import disco.backup.state_snapshot
```

An inert owner/ancestor permits traversal only to exact declared named entries;
it is not a public wildcard. `from disco.backup import private_impl`, star imports,
undeclared submodules, noncanonical aliases/shims and private attributes fail.
Relative imports normalize to the same exact file identity. Same-owner production
may reach its private files; outside production and tests cannot bypass the seam.

Keep declaration and provenance maps explicit: owner-by-path, entry-by-path and
entry-by-canonical-identity. Normalize legacy entries into a lookup only where
that preserves legacy behavior; do not replace their strict initializer checker.
Reuse current lexical binding/expression machinery rather than adding a new
parser, policy engine or import execution. Imported aliases must retain their
original local names, class/function/value identities and singleton module state.

For named entries, distinguish module access from values: declared functions,
classes and constants are ordinary caller values. Natural class construction,
constant operations and declared external dependency attributes are legitimate;
this is not a type/member sandbox. Module traversal and owned-module provenance
remain guarded. Introspection capable of exposing hidden bindings (`__dict__`,
function `__globals__`, class namespace/reflection and getattr/vars on an owned
module) remains refused. Read-only `leaf.__file__` is the one demonstrated module
metadata attribute needed for scientific source witnesses; it must identify the
exact named leaf and cannot be assigned or exported as a module alias.

Do not silently permit arbitrary module forwarding. Existing three witness loops
use a literal tuple of imported module aliases and inspect `module.__file__`.
Bounded support must track that finite tuple/list through its local `for` or
comprehension target, then apply the same leaf-attribute restrictions. Calls taking
those module objects, unknown iterables, collection mutation, escaped closures or
reassignment remain refused. Add positive and escape-negative fixtures before
claiming metadata adoption. If that cannot be expressed with a small extension of
existing lexical bindings, leave metadata at its existing paths; do not rewrite
its source-witness algorithm for folder counts.

## Existing test patches: narrow exception, not opaque module permission

Real examples include recovery-store `patch.object(recovery,'CHECKPOINT_BYTES',1)`
and `patch.object(recovery,'_write_rows',...)`, curation's table-binding patches,
`patch.object(backup.threading,'Thread')`, and migration's Path/subprocess patches.
These preserve existing test seams, not new production interfaces.

In classified test files only, recognize the actual `unittest.mock.patch.object`
call binding (including ordinary import aliases), a statically resolved named
public module and a literal string naming an explicitly declared export. Permit
that exact first-argument module use. Reject a shadowed/spoofed patch, computed
attribute, unlisted name, private module, nested opaque forwarding and every
production occurrence. Existing constructor/instance patches are ordinary object
usage, not a new module exemption. Patches of a declared external dependency such
as `recovery.os.fsync` retain the dependency's external origin; they do not grant
access to other owned files. Do not broadly allow all calls named `patch`.

Qualified string patches (`patch('disco.backup.state_snapshot.atomic_write',...)`)
need analogous literal target validation in classified tests; each target must
resolve to an exact public leaf and declared attributes at every owned module origin. A private target,
legacy shim target or unreviewed computed adopted target fails. This closes a
concrete string route, rather than introducing a generic reflection allowlist.

Some existing test doubles replace `sys.modules` entries (for example
`test_workspace_group_recovery.py:111-115`). Their exact compatibility is an
adoption gate: no broad `sys.modules`, dynamic module-object or reflective escape
is authorized by this design. Preserve those source cases and review whether
existing source-bound loader evidence suffices; otherwise keep that affected
owner flat. Do not retrofit a generic bypass into named mode.

## Dynamic loaders and shims remain closed

No new dynamic adopted import allowance is needed: the metadata worker confirmed
no live importlib/__import__ calls to its nine leaves. Literal import_module,
__import__ (including fromlist/relative variants), loader aliases, private paths,
ancestor loads and public-module shims remain rejected for adopted owners.
Computed/file/embedded loaders retain existing exact whole-file and AST-site
bindings, including changed/unused-site refusal. Named entry lookup must cover
all public leaves and their ancestor names in the existing dynamic checks.
Reviewed loader records are not a general authority to load new adopted code.
Do not drop module-binding shim, lexical shadowing, class-default/decorator,
comprehension or missing-definition regression checks from v4.

## Implementation touchlist and bounded cost

Only after root design review:

1. `tools/architecture_guard.py`: accept catalog v5; validate the new exact record;
   construct entry/namespace lookups; update owned-edge/public-import and lexical
   binding resolution; split legacy initializer checks from named export checks;
   apply existing shim/private/dynamic fences to every declared entry. Add narrowly
   justified test-patch and witness-tuple handling only with their fault fixtures.
2. `tools/architecture_module_policy.py`: accept global version 5 with unchanged
   JavaScript-v3/v4 entry semantics, because the catalog has one version. No new
   frontend feature or schema shape.
3. `python/tests/test_architecture_guard.py`: extend the existing public CLI
   fixture class or a named-entry subclass. Keep all old cases; use stdlib fixture
   bodies and subprocess guard CLI only, never import product/scientific code.
4. Existing tooling guide/adoption docs: document version semantics and limits.
   No shipping catalog/profile/runtime move, no loader-binding reseal, no package
   initializer edits or new framework in this prerequisite commit.

Expected complexity is one record validator and entry lookup refactor plus bounded
syntax cases, not a guard rewrite. The patch/tuple requirements are more than a
mechanical list expansion and must be reviewed explicitly. Split the reader proof
into (A) named entries/identities/inert parents and legacy parity, (B) narrow
existing test-patch/witness forms. If B requires a general dataflow graph, runtime
import introspection, arbitrary allowlisted syntax sites or more than small local
changes to the existing binding resolver, stop and retain the affected modules.
The acceptable alternative is continued coherent guides and flat named files;
folder counts never justify weaker checking or replacement facades.

## Public CLI acceptance and deliberate-fault matrix

All positive/negative checks below use disposable inert sources via existing
`check --language metadata/python`, `plan --base`, and mapped `test` commands.
They are planned, NOT executed in this design.

| Positive contract | Deliberate fault that must fail |
| --- | --- |
| Unchanged v4 P04 catalog and source passes all current cases | New fields under v4, changed P04 initializer behavior, undeclared exports |
| v5 old P04 record behaves identically alongside two named entries | Normalization accidentally permits P04 implementation import/reflection |
| Direct/from-parent/aliased/relative named imports bind same leaf | Duplicate identity, path mismatch, fake parent alias, unresolved/private sibling |
| Two substantive leaves share ordinary export names | Owner-wide export union wrongly allows A's symbol on B |
| Inert namespace imports do not execute scientific dependencies | Parent/root imports Flask, assignment, missing init, namespace package |
| Exact declared function/class/constant/underscore bindings | Missing binding, annotation-only declaration, star export, private alias laundering |
| Standard class/constant use remains possible | Module __dict__, function __globals__, getattr(module,...), opaque forwarded module |
| Explicit public imported binding retains source provenance | Downstream shim or imported private implementation presented as public |
| Local same-owner private use and exact used test exception | Cross-owner private edge, unused exception, production test import |
| Three finite witness tuples retain leaf __file__ identity | Hashing initializer, module in unknown/mutated iterable, hidden attr via iteration |
| Classified test's real patch.object with explicit export | Fake/shadowed patch, production patch, computed/unlisted/private target |
| Literal string patch retains exact qualified entry identity | Private/old shim target, missing entry, computed adopted target |
| Existing loader site hashes still bind exact source/AST | Literal/computed/aliased/relative adopted loader, changed/removed/unused site |
| Existing declaration scopes and mapped local tests remain intact | Default/decorator/class/comprehension escape, symlink, unmapped test, empty plan |

Add mixed-owner CLI fixtures to prove a permissive new named mode cannot weaken
legacy P04 or another owner. Inject inert sentinel modules into disposable runtime
fixture checks only if needed to prove leaf import identity and initializer
non-execution; this is not production/native import qualification. Full application
runtime/packaging/scientific tests remain separate, authorized gates.

## Reader increment A

The first implementation adds only version/schema, exact leaf identities,
namespace/entry import handling, named value provenance and default-private rules.
The shipping catalog remains byte-for-byte unchanged. Named files do not require
`__all__`, and legacy initializer records retain their original validation path.
Classified test-to-test fixture imports are allowed for named owners; production
imports of test sources remain refused. A private constant/function/module cannot
be exposed by adding an imported alias to a named entry's declared exports.

The existing CLI suite and nine named-entry cases cover mixed P04/named owners,
canonical imports, normal class/constants/underscore use, inert initializer faults,
private/shim/loader faults, exact used exceptions, and explicit-base mapped runs.
No product modules are imported. Patch calls and witness iteration remain blocked
until the separately reviewed increment B. Existing v4 negative cases remain in
place; the unknown-version fixture advances from 5 to 6 because 5 is now supported.

## Reader increment B

The second implementation admits only statically resolved, unambiguous real
`unittest.mock.patch`/`patch.object` bindings. A direct named module argument is
allowed only in a classified test and with a literal declared attribute. Literal
string patches through named namespaces follow public binding provenance at every
owned module attribute; ordinary class and external dependency attributes remain
available, while private/reflection targets fail. Direct attribute writes/deletes
and bounded `setattr`/`delattr` mutations of recognized mock bindings (including
aliases) invalidate the real-mock exception. Computed targets to recognized mock patch
calls are conservatively unsupported in v5 while named owners are adopted. This
is an explicit adoption limit, not a guessed resolution. Legacy-only policies
retain their old behavior. Real test execution over inert fixture modules confirms
that patching and restoration retain their module identity.

The witness support is limited to direct literal tuples/lists of module aliases
used by `for` or comprehension iteration. It retains the finite possible module
origins in the existing lexical binding map and allows read-only named-leaf
`__file__`. It does not track stored/mutated collections, arbitrary function
returns, generic object graphs or runtime import effects. Existing source witness
loops fit this form, including mixed retained/adopted module aliases. Private
attributes, reflective access, module forwarding and reassigned loop aliases
remain failures. The checks inspect source only; they do not execute scientific
imports or validate scientific receipts. `sys.modules` doubles and other
unsupported usages remain explicit owner-adoption review gates.
