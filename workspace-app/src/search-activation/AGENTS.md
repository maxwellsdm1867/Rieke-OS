# Search activation

This folder owns bounded global-search reads, their App-shell activation lifetime,
and the search dialog. Existing file exports remain the public interface; there
is no barrel or new runtime wrapper. The [ledger](../../../docs/architecture/core-module-ledger.json)
record `search-read-activation` and [stable ports](../../../docs/architecture/stable-ports.md)
provide the wider ownership map.

## Public entries and ownership

- [pageReadCache.js](pageReadCache.js): `createPageReadCache`, limits/version,
  typed `canonicalReadIdentity`, `pageReadKey`, `searchReadDescriptor` and
  `validSearchResponse`. Tree callers also use typed canonical identity; that
  reuse grants neither search activation nor tree ancestor authority.
- [navigationReadCache.jsx](navigationReadCache.jsx): `NavigationReadProvider`,
  `WorkspaceReadCacheOwner` and `useSearchSnapshot`. App mounts the owner above
  the dialog lifetime; React, shared api and annotation profile are dependencies.
- [GlobalSearch.jsx](GlobalSearch.jsx): default dialog entry with its adjacent CSS.
  Callers supply epoch/cell/predicate callbacks; choosing requires `canChoose`.
- [metadataSearch.js](metadataSearch.js): `parseMetadataSearch` and
  `matchesMetadataSearch` retain exact typed comparison for MetadataPanel.
  The shared metadata-values owner supplies safe value/registry interpretation.

GET `/search` with exactly q and limit=20 is the only reusable network read.
Project UUID, open identity, actor/profile namespace, activation, request and
revision are distinct. Missing and null, number and string, negative zero and
zero remain distinct in typed identities. Results preserve order and immutable
values. No candidate fallback or mutation receipt is introduced.

The cache keeps 16 entries/32 MiB charged UTF-8 bytes, at most four physically
outstanding reads, 30 seconds fresh and 300 seconds retained. Subscriber abort
can detach while abort-ignoring physical work still consumes capacity. Scope
retirement rejects subscribers and fences late completion; 409 revokes retained
scope. Other errors may display stale inert content. Action-time identity,
membership, generation and freshness checks prevent selection of stale results.
Focus, online, pageshow, visible-document and desktop-status changes revoke
activation. Provisional profile namespaces remain distinct from tree readiness.

## Executable examples and checks

[pageReadCache.test.js](pageReadCache.test.js) exercises the public factory with
`searchReadDescriptor(scope, query, revision)`, `activate(scope)` and
`read(descriptor, {load, signal})`; its allowlist, identity, concurrent subscriber,
capacity and retirement cases are runnable consumer examples.
[globalSearchCache.test.js](globalSearchCache.test.js) mounts the actual dialog
and owner through the shared harness, including abort-ignoring requests, profile
changes and action-time checks. [navigationReadStrictMode.test.js](navigationReadStrictMode.test.js)
uses actual ReactDOM replay/remount. [metadataSearch.test.js](metadataSearch.test.js)
covers typed predicate matching. No test-only exports are added.

From `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/search-activation/*.test.js src/globalSearchBaseline.test.js
```

Preserve each existing export and the CSS import. Cross-owner typed identity
consumers remain public callers. New cache resources require their own allowlist,
validation and authority/lifetime review. Shared catalog, navigation and benchmark
path integration is coordinated at the parent wave; recursive tests need no new
runner. The [benchmark registry](../../../benchmarks/registry.json) and
[guide](../../../docs/dev/benchmarks.md) remain canonical. Source tests do not
qualify native transport, packaged UI, heap usage or performance.
