# Signed and testing update coordination

The [signed coordinator](updater.cjs), [testing coordinator](testing-updater.cjs)
and [testing validation](testing-update-validation.cjs) retain distinct public
interfaces and trust policy. See [instructions](AGENTS.md) and [desktop navigation](../AGENTS.md).
[Main](../main.cjs) chooses the channel and supplies lifecycle authorization;
[shared root validation](../updater-validation.cjs) also serves installation,
integrity and build tooling, so it remains at root.

| Public entry | Contract and failures |
| --- | --- |
| `createUpdateCoordinator(options)` | Inject app/manifest/updater, validation, prepareQuit/authorizeQuit/revokeQuit, receipt and timer ports. Returns getStatus/check/start/stop/installPrepared. Signed platform/channel admission and candidate validation precede install authority; failed drain or changed candidate returns ready:false and preserves recovery. |
| `createTestingUpdateCoordinator(options)` | Inject app/manifest/distribution/transport, verifyCandidate/revalidateCandidate, lifecycle/helper/identity and timer ports. Returns getStatus/start/check/download/installPrepared/stop/flushReceipts. Metadata notice never consumes explicit download choice; restart hints require fresh provenance and validation. Revalidates after drain and requires helper readiness before quit. |
| `httpsTransport(url, options)`, `releaseList(transport)`, `assetURL(asset, tag, expectedName)` | Existing public transport/feed helpers retain repository/URL boundaries. Errors propagate or coordinator reports Deferred. No authority from an arbitrary URL. |
| `REPOSITORY`, `REPOSITORIES`, `approvedURL(url, kind)`, `validateDescriptor(value,current,hostVersion)` | Official provenance, channel, stable newer version, platform/compatibility and bounded checksums; malformed/foreign input throws. |
| `hashFile(file,algorithm)`, `verifyArchive(file,descriptor)`, `ensurePrivateCache(userData)` | Owned nonsymlink/regular file and private-cache checks, archive size/hash validation; errors reject. |
| `inspectTestingBundle(options)`, `validateTestingCandidate(options)`, `revalidateTestingCandidate(options)` | Existing resource/control-byte, installed interpreter and candidate revalidation boundaries. Unsigned testing verification never authenticates a Developer ID publisher. |

Common local dependencies are root physical-fs and updater-validation. Signed
coordination additionally calls root update-recovery and lazily loads
`electron-updater`; testing calls sibling validation and root testing-install and
install-name. Node path/crypto/util/child_process/https remain as declared in source.
No production __dirname exists in these three entries: cache and bundle locations
come from explicit options/app.getPath. Root helpers keep their own resource bases.

Deferred drain, changed cache and stopped testing handoff retain uncertainty.
The existing stop-during-drain check belongs only to testing coordination; signed
coordination lacks that check and this relocation preserves that distinction.
Never extend the testing fault result to signed behavior. Neither owner owns
scientific process readiness or [strict replacement versus bounded Quit](../close/README.md).

The executable [public examples](tests/public-examples.test.cjs) call real testing
owners with memory-only transport and injected validation/helper ports. They show
metadata without download, deferred drain, post-drain rejection and testing stop
refusal, plus foreign provenance rejection. They use fresh owned filesystem data,
not network, app, signing or native installers. On unsupported hosts three platform
cases remain explicitly skipped/unqualified. Source-only commands from repository root:

```sh
node --test desktop/updates/tests/public-examples.test.cjs desktop/tests/close-packaging.test.cjs desktop/tests/branding.test.cjs
node --test --test-name-pattern='^(fixture teardown waits|source and unsigned builds)' desktop/updates/tests/updater.test.cjs
python3 -B -m unittest python.tests.test_architecture_guard python.tests.test_desktop_release_plan
```

[Original signed tests](tests/updater.test.cjs) preserve actual receipt-rename
completion observation through the physical-fs seam; [testing tests](tests/testing-updater.test.cjs)
preserve flushReceipts cleanup. Their full globs include host archive/interpreter
cases and loopback fixtures; run them only under separately reviewed capability
scope. Electron physical-fs/updater-client and packaged-upgrade callers have updated
paths but are not newly qualified. Their source changes do not authorize execution.

The source packaging checker now checks main plus nine adopted entries. Eight
are direct main requires; testing validation is the testing coordinator's sibling.
Exact default/preview allowlists, relative dependency resolution and negative
faults do not prove electron-builder selection, ASAR or whole transitive closure.
Parent serializes [catalog](../../docs/architecture/adopted-port-checks.json),
[ledger](../../docs/architecture/core-module-ledger.md),
[path companion](../../docs/architecture/core-module-paths.json) and navigation.

Actual signed/native installation, installed helper resolution, shutdown/reopen
and final-app acceptance remain separate gates. See [benchmarks](../../docs/dev/benchmarks.md),
[registry](../../benchmarks/registry.json) and [macOS policy](../../docs/dev/macos-compatibility.md).
No owner benchmark/performance or release qualification is claimed here.
