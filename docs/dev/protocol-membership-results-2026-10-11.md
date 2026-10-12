# Versioned protocol membership: implementation and evidence

Application source: `f852bbf550b8518d23d91572d5d7f3d3dfc01917`. Combined before-state: `bb25b0837c52390f147e35c1619c06d776f96ced`. GitHub main was separately verified as `035e295ba01e648005dde24fc4cdbbc4dab412e4`; these local changes are not installed or published.

## Decision

The accepted goal is to pay necessary preparation once, then reuse a safe, versioned membership index. A slower cold build is acceptable when repeated reads benefit. The implementation caches membership itself rather than copying the project database. It does not treat a fast first query as more important than correctness or warm reuse.

Canonical saved protocols receive an immutable SQLite member table keyed by project/protocol binding revision and version, typed/native generation, and exact source eligibility. Later thread-owned readers attach that table read-only. Warm reads do not hydrate the recipe, iterate UUID membership, insert members, hash the whole file, or reconstruct an SQL IN-list. Existing opening/closing response authority checks still decide whether a result may be returned.

Construction is serialized; only a committed, closed file is published. Failed builds are removed. Active readers retain their files through eviction; changes never overwrite a live immutable file. New bindings/generations get new keys. Unexpected file changes fail closed. The session-private cache rebuilds after restart or eviction. Retention is 16 entries/256 MiB, with one larger entry allowed; it never truncates or rejects membership because of that retention budget.

Protocol tree freshness watches the complete cohort, including members hidden by filters. It still checks O(M) member fingerprints, preserving in-place mutation detection, but no longer watches unrelated project epochs. Contains/wide-number evaluation and facets use values reachable from admitted members. Global discovery and custom/unbound policies retain their existing authoritative paths.

## Cold build versus repeated reads

Real sealed SQLite fixture with 20,000 epochs, seven samples per case, and a fresh reader connection for every query. Fixture/index construction is excluded. Full service/HTTP/native behavior is not measured by this lane.

| Membership | One-time membership build | Page with repeated admission | Page with reuse | Summary with repeated admission | Summary with reuse |
|---:|---:|---:|---:|---:|---:|
| 2,000 | 6.44 ms | 6.08 ms | 1.88 ms | 9.56 ms | 5.36 ms |
| 20,000 | 43.37 ms | 46.89 ms | 6.33 ms | 83.53 ms | 42.82 ms |

A separate actual-million-row SQLite diagnostic built the full million-member cache in **3.07 s**. Deep-page reads changed from **3.89 s to 249.1 ms** (about 15.6×). This lane substitutes native/typed seal admission with fixture proof; it is not native qualification. Both cache lanes returned exact results and recorded zero warm recipe reads and zero H5 opens.

## Fixed membership while the project grows

Each project contains the same 2,000-member protocol. Matched sources run serially under the shared benchmark lock. These are direct-call synthetic metadata/SQL diagnostics, with fixture setup excluded.

| Project epochs | Tree warm root, before → after | SQL page, before → after | SQL contains, before → after | SQL facets, before → after |
|---:|---:|---:|---:|---:|
| 20,000 | 0.65 → 0.32 ms | 16.61 → 5.00 ms | 40.08 → 12.76 ms | 69.18 → 7.36 ms |
| 200,000 | 11.49 → 0.31 ms | 146.56 → 5.02 ms | 333.03 → 13.34 ms | 758.70 → 7.94 ms |
| 1,000,000 | 86.22 → 0.31 ms | 815.00 → 5.57 ms | 1666.43 → 13.80 ms | 3929.90 → 8.42 ms |

At one million project epochs, warm tree fingerprint visits fell from 1,000,000 to exactly 2,000, with no scope rebuild on a warm read or unrelated edit. Member edits still rejected the stale revision. Contains-search dictionary visits fell from 1,000,000 to exactly 2,000. No metadata test opened H5.

## Verification and retained failures

- 141 scoped tests passed; architecture guard passed. Tests cover exact scope/facet semantics, separate readers, canonical binding reuse, rebinding, source restrictions, concurrent first use, failed-build cleanup, file-change refusal, and readers surviving eviction.
- The fixed core passed all 10 cases with no validation errors.
- The matched actual-million comparison against the pinned regression source passed with no flags.
- The first comparison against the immediately previous implementation flagged uncached `typed.protocol_deep`: 3,319.47 → 4,759.49 ms. Its exact results passed. The affected admission/page implementation was unchanged. A fresh matched repeat passed with no flags: 3,337.32 → 3,286.18 ms. Both receipts are preserved; the flag was not averaged away.
- Relative to the older pinned source, arbitrary uncached full-million source-restricted admission was about 23% slower while remaining within the comparison policy. Saved protocol reads use the reusable index; unversioned UUID iterators deliberately retain admission. This is not a claim that every cold/global path is faster.
- Earlier overlapping-load matrix timings and the interrupted view-based cache iteration remain unqualified. The final matrix used the canonical shared lock.

## Browser qualification gap

The full thirteen-action comparison did not complete. The harness still reads `[aria-label="Response stream"].value` in its canvas/trace oracle (`benchmarks/workflow/fixture-app.mjs:44` and `browser.mjs:98`). The already-present graphics implementation uses a div containing a single-stream label or buttons (`TraceViewer.jsx:177`). The baseline completed its first six ordinary actions, then waited on that obsolete identity check. The owned browser run was stopped and its partial evidence retained. No candidate UI speedup or complete browser pass is claimed.

Two earlier launcher issues are also preserved: a redundant outer benchmark lock, and an absent Playwright browser. The latter was resolved by selecting installed Chrome 154.0.8037.98 for an isolated headless run. Neither startup attempt established product behavior.

## Adversarial review

Two independent read-only reviewers assessed the full change against the pre-membership implementation and the human acceptance of necessary cold work. Standards: zero documented-standard violations, one nonblocking duplicated-admission-logic concern. Spec: zero actionable findings. Their complete reports are in [the adversarial review](protocol-membership-adversarial-review-2026-10-11.md). Review is source evidence, not native or browser qualification.

## Artifacts and scope

Compact metrics: [results JSON](protocol-membership-results-2026-10-11.json). Design research: [SQL cohort scope](protocol-membership-sql-research-2026-10-11.md) and [immutable membership reuse](protocol-membership-cache-research-2026-10-11.md). Reusable benchmark tools: `tools/benchmark_membership_scaling.py`, `tools/benchmark_membership_sql.py`, and `tools/benchmark_membership_cache.py`.

Raw JSON, logs, partial failures, the supplemental million-cache harness, and review reports are retained at `/private/tmp/disco-membership-evidence`. A SHA-256 evidence manifest accompanies them. The measured application commit remains the one named above; the later results commit changes documentation only. No installed app, user dataset, public release, or remote branch was changed.
