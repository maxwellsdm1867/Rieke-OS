# Attested tree ancestors

This module owns bounded reuse of nonterminal ancestor JSON under a fresh server
witness. Public entries are [treeBranchReadCache.js](treeBranchReadCache.js)
(`TREE_BRANCH_LIMITS`, `reusableTreeBody`, `createTreeBranchReadCache`),
[treeBranchReads.jsx](treeBranchReads.jsx) (`TreeBranchReadOwner`,
`useTreeBranchReads`) and [columnTreeReads.js](columnTreeReads.js)
(`loadColumnTreePages`). Import these entries directly; helpers remain lexical.
There is no facade, private test edge or duplicate React context.

The cache factory accepts positive safe-integer entries, bytes, inflight,
retainMs and leaseMs bounds, plus an optional clock. Defaults are 24 entries,
4 MiB charged JSON, eight physical requests, 120-second retention and ten-second
leases. Its public interface is client, activate, retire, attest, read,
assertCurrent, isActive, isCurrent and stats. The QueryClient owns payloads and
requests; the ledger tracks size and recency. These bounds do not measure total
renderer heap or mounted DOM.

Activate an exact project UUID/path, actor, revision and activation scope before
attesting. Only a complete current backend witness can yield a lease; generation
identity includes metadata, nullable typed, source, annotation, binding and
publication. Shared [canonical identity](../search-activation/pageReadCache.js) preserves typed
identity, including negative zero. Never replace it with JSON.stringify. Reuse
admits only unfiltered recorded-field nonterminal protocol branches with the
existing strict body and response validation. Frozen/candidate, terminal, anchor,
filtered and unknown-key requests cannot borrow authority. Delivered JSON is
immutable; oversized responses can be delivered without retention.

Retire clears storage and revokes leases/observers. Abort-ignoring physical work
keeps its capacity slot until completion. Subscriber cancellation is independent;
the last subscriber aborts transport/removes storage. HTTP 409 invalidates the
owner generation. Preserve AbortError `Tree read intent retired`,
StaleTreeReadError `Tree read witness expired; reload the current tree`, existing
capacity/identity errors, and explicit retry. No implicit focus/reconnect retry,
scientific write or authority renewal follows from cached data.

The React owner holds one cache per mounted provider, including an explicitly
provided real cache. Annotation-profile loading/error prevents scope availability;
no selected profile retains the existing browse-only actor. Layout effects own
activation and retirement. Browser focus, online, pageshow, pagehide, visibility
transitions and initial/changed desktop status revoke; identical repeated status
does not. Cleanup retires cache and removes subscriptions. Null scope deliberately
has active() true, available false and attest() null. Consumers must preserve their
separate availability and publication fences.

Column orchestration always fetches the target fresh; live continuation recovery
fetches the root first. Only live tree-pages may attest for optional ancestor reuse.
Frozen contexts retain their endpoint. Parent pages preserve order and match the
current revision/witness. Signal, current intent, owner and lease gate completion;
supersession throws AbortError `Tree navigation superseded`. Selection, tag
mutation, scientific grouping, shared page-cache identity and gesture ownership
remain outside this module.

## Executable public example and checks

The first [cache test](treeBranchReadCache.test.js), “only a current complete
backend witness permits exact nonterminal ancestor reuse”, contains the complete
owned scope/body/page fixture: activate, attest, read, then fresh attest/read yields
one immutable response from one load. Reuse that valid fixture instead of inventing
an incomplete witness. Its afterEach retires every cache. An injected owned DTO
provides test data and does not establish native scientific authority.

[Provider tests](treeBranchReads.test.js) mount the actual profile/provider/cache
and inspect public leases and event registration. Keep their HTTP/browser/status
controls and global restoration. [Inspector authority](../inspectorTreeAuthority.test.js)
remains a cross-owner integration suite. Preserve the cache suite's two real
component fixtures and all SSR roots, exact import interceptors and provider
allowlists when changing paths.

With RIEKE_TEST_DOM_MODULE unset, from workspace-app:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/tree-ancestors/treeBranchReadCache.test.js src/tree-ancestors/treeBranchReads.test.js src/columnTreeNavigation.test.js src/inspectorTreeAuthority.test.js src/workbenchSessionLifecycle.test.js src/presentationSessionsApp.test.js src/presentationSessionsIntegration.test.js src/workflowResponsiveness.test.js src/inspectorNavigationLifecycle.test.js src/inspectorCurationLifecycle.test.js src/selectionMaskDownload.test.js
```

Review contract/dependency/lifetime changes before implementation. Root integration
owns the architecture catalog's exact public export/import rules, P03 PagedTree
cache deny, ledger, navigation and adopted contract. Follow the root architecture
guard explicit-base plan/mapped checks and coordinated frontend closure. Preserve
empty private-test edges and keep test-support imports out of production.

The FE04-attested-tree-ancestor-cache ledger's correctness.navigation and
ui.mounted.inspector.return links are indirect flow evidence, not isolated cache
measurements. Preserve historical benchmark suite identity and receipts. Ancestor
round-trip cost, lease churn, physical cancellation cost, heap and native release
acceptance remain unmeasured; relocation grants no performance or release claim.


## Dependency and locality review

React/TanStack state, shared page identity, request shaping and ancestor navigation
are in-process dependencies. Browser events are local-substitutable through the
existing JSDOM adapter. Owned HTTP reads and desktop status cross remote-owned
seams; existing load/status adapters supply controlled test results. Profile
readiness remains an upstream authority input. There is no true-external service
dependency requiring a new mock port. Browser/desktop events are lifetime notifications.
Injected clocks, real caches and load functions are existing public test seams.
Keep these categories distinct: a transport adapter or event cannot grant witness
or scientific authority. Tests exercise the public entries with owned values;
lexical cache internals remain hidden.

Deleting this folder requires removing ancestor reuse/provider composition from
App and its tree consumers, and addressing their existing read-owner interactions.
It must not require deleting page-read identity, selection, profile or mutation
owners: those remain independent. The folder groups the three pieces necessary
for safe ancestor reuse and its local evidence; cross-owner Inspector tests remain
outside. This relocation improves discovery/locality only. It does not simplify
the public API or prove a deeper abstraction; future interface changes require
separate review of caller knowledge and coupling.
