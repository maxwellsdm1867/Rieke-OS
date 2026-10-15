# Direct exact trace reads

This follow-up to `bf5064d` removes unused loading work before displaying a trace. It adds no import sidecar, persistent trace cache, or new UI. The requested target is a complete one-million-sample display within 50 ms; measurement must establish whether loading changes reach it.

Canonical bound Workbench reads ask `ProtocolStateReader.read_revision` for a fresh revision without constructing full curation state that the caller discards. Native metadata and generation checks remain; unsupported authority invokes the existing full-state oracle exactly once. Custom state readers, unbound contexts and explicit mutation guards keep their paths. The closing Workbench context remains independently fresh.

Explicit binary requests to the canonical trace reader share one H5 handle across at most ten bounded 100k windows. Every sample's unit is compared directly instead of sorting repeated unit labels. Detached finite float64 arrays pass directly to little-endian binary encoding, preserving exact bits, including signed zero. Per-window and post-close source signatures and the final workspace/publication witness remain mandatory. Custom readers and JSON requests retain the five-window limit; empty binary requests return the legacy JSON window.

The frontend accepts one bounded million-sample binary response and uses its buffer directly. Larger traces use another bounded request. Scientific identity, frame bounds, finite values, source, units, rate, contiguity and frozen scope are independently checked before publication.

The final single-load iteration adds an optional, bounded native reader for the exact packed float64/S10 gzip64 layout. HDF5 still resolves and admits the dataset; at most four native workers below 500k samples and eight for larger requests inflate independent chunks already read through capped spans. ABI 3 reuses one zlib decoder per worker while requiring each chunk to consume its full input and produce its exact output. Unsupported layouts retain ordinary HDF5. Exact H5 NULLTERM conversion, every unit, finite values, source identity and closing checks remain. The [execution contract](../architecture/trace-worker-execution.md) specifies admission and failure behavior. Package-time compilation uses macOS 14 arm64 flags and signs the helper; no runtime compilation occurs.

An OS-warm, sample-uncached matched comparison measured canonical million-sample reading and encoding at 151.32 ms generic versus 44.48 ms native, with a native range of 43.64–51.55 ms. Actual registered 300k and 600k responses measured 44.76→12.47 ms and 84.26→23.27 ms. These exclude database/frozen authority, HTTP and display; under-50-ms complete display is not established. Raw evidence remains outside the checkout in `evidence/direct-recovery/native-integration/`.

The [browser audit](fused-trace-statistics-2026-10-15.md) removes redundant full-sample scans while retaining exact samples. For visual QC, a manually clipped amplitude range draws the full raw polyline. Its 36 clipped raster cases match an independent full-raw oracle exactly; 36 unclipped cases preserve the preceding renderer. Screen-resolution reduction in unclipped whole views remains an approximation, with original samples available on zoom and cursor inspection.

## Projection compatibility review

Relative to `bf5064d`, removing only trace sample-reading functions, `WorkspaceService.trace_batch`, and the new canonical response/batch identity captures produces an identical whole-file AST. The other three projection owners and resolver are byte-identical. Metadata construction, cache codecs and publication semantics therefore have no changes in the projection owner vector. The exact vector is recorded in `projection_contract_receipts.py`; no wildcard compatibility is granted. The changed scientific read path is separately reviewed and tested.

## Validation boundary

Focused tests cover native revision and fallback behavior, closing mutations, source changes, late invalid units/nonfinite samples, array endianness/strides/extremes/signed zero, custom readers, EOF, and exact one-million-sample transport with one H5 open. Owned compound float64 + S10, gzip/chunk64 diagnostics distinguish read cost, encoding and transfer size. These are not native performance or release qualification. Clean-source core/stress receipts and packaged click measurements remain separately attributed to their measured commit.

A system restart cleared the original temporary staging checkout during packaging. The reviewed implementation was reconstructed into the permanent source checkout and retested; old measurements remain attributed to their original source and environment.

## Prepared display follow-up

Prepared Workbench views now capture an immutable display membership capability. Trace clicks use that capability without current tag, draft, recipe or database reads. Preparation and scientific mutations retain their existing current-authority checks. Source publication, actor, requested epoch fingerprint and recording registration are checked before and after each sample read. The capability is never mutation authority. Selected views require an explicit selection token and capture the complete filtered intersection; an ordinary epoch predicate remains a pending view.

Member and source witnesses share a 64 MiB budget and eight-view limit. A publication change releases obsolete entries. The frontend dispatches prepared reads during layout commit, fences completed and pending reads by their request lifetime, and keeps tag controls paired with their own fresh epoch context. Exact annotations already delivered in a page are reused without a redundant request or disabled flash.

A production React/direct Waitress diagnostic of one million actual H5 samples measured warm click-to-drawing at 80.5 and 79.2 ms (stable frame observations 102.1 and 88.5 ms). First use measured 433.5 ms and is retained separately. The fixture uses canonical source/index checks but SQL doubles and an owned component shell; it is not an installed-app or actual MySQL measurement. The requested 50 ms complete-display target remains unmet. Receipts and fixed source hashes are under `evidence/direct-recovery/capability-fullpath/production-prepared-display-sql-double-1000-167-20261015T070057Z`. The preceding failed build is retained separately.

The prepared-display projection receipt compares against `8c77785`. Only optional diagnostic clocks in `WorkspaceService.trace_batch` differ within the projection-owner files; excluding that method yields an identical AST, and the other owners and resolver are byte-identical. Eleven projection contract tests pass. The earlier native reader receipt remains separately attributed.

The production matrix's one-million-metadata/167-member fixture measured warm drawing at 86.1 and 84.4 ms. The 20,000-member fixture passed identity and exact-byte checks but measured 906.6, 691.0 and 642.2 ms, with inflated sample-reading and transfer times. This anomalous run is retained and does not establish flat full-path latency across cohort sizes. Post-run memory compression is observed; paging or contention during the timed interval is not yet proven. Diagnostic repeats must remain separate evidence.
