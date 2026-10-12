# Protocol membership adversarial review

Reviewed source: `f852bbf550b8518d23d91572d5d7f3d3dfc01917`, compared with `bb25b0837c52390f147e35c1619c06d776f96ced`.

Human acceptance criterion: necessary cold build cost is acceptable when reused across subsequent fast, safely versioned operations; avoid redundant work and requests. Two independent read-only reviews were run.

## Standards

Reviewed `bb25b0837c52390f147e35c1619c06d776f96ced...f852bbf550b8518d23d91572d5d7f3d3dfc01917` read-only. No tests or benchmarks were run during the parent's serial measurements.

**Documented-standard violations: no concrete findings.** The reviewed implementation preserves the metadata contract's exact scope/source intersection, canonical-provider fallback, thread-owned query connections, generation checks, and retained native ownership. Membership publication occurs only after commit and closing checks; failed construction removes its unfinished asset. Attached readers retain membership files across LRU eviction. The navigation cache watches complete protocol membership, including filtered-out members, and still retains the project witness for source discovery. Opening/closing response authority remains outside the acceleration cache, consistent with metadata KEEP decisions.

The method fits the user's clarified objective: pay necessary admission/build cost once per immutable binding/source/generation key, then reuse an indexed disk relation without recipe hydration or UUID readmission. Slower cold construction alone is not a defect. Files are session-private, so restart or eviction can require rebuilding; measured warm speed must not be described as a durable restart guarantee. Native/UI qualification remains separate from the bounded source tests and synthetic measurements.

**Judgment call, nonblocking — duplicated admission logic:** `python/disco/metadata/typed_lifecycle.py:116-128` and `python/disco/metadata/typed_query.py:179-192` independently implement UUID admission followed by the same source-eligibility deletion. This is a small Duplicated Code smell: future changes to duplicate/unknown/source semantics could diverge between reusable and arbitrary scopes. Existing equivalence tests cover today's behavior, and extraction is not required for acceptance; if either policy changes, keep one shared admission operation or explicitly extend paired equivalence coverage. The different connection/lifetime owners should remain separate.

This is source review, not fresh execution evidence or packaged-app acceptance.

## Spec

Reviewed `bb25b0837c52390f147e35c1619c06d776f96ced...f852bbf550b8518d23d91572d5d7f3d3dfc01917` by read-only inspection. No application edits, benchmark runs, or test runs.

**No actionable spec findings identified.** No demonstrated missing requirement, scope creep, or incorrectly implemented requirement in this comparison.

The latest instruction—“necessary slower uncached/first build is acceptable if amortized across repeated fast safe versioned reads”—is consistent with this implementation. `MembershipCache.get` performs UUID admission/source restriction only on a miss, then shares the completed immutable table across separate reader connections. Cache hits do not call the recipe factory or rebuild the member table. The direct attached-table relation avoids copying membership into each reader's TEMP table.

Safety inspection covered canonical provider gating; binding/version/native-generation/source keys; binding comparison during cold preparation; opening/closing response and summary fences; serialized builders; failed-build cleanup; and strong handle references retaining files through eviction and reader use. A rebind during construction can leave an old-key cache entry, but the closing fence rejects its response and the next binding uses a different key. I found no stale-result acceptance introduced by this behavior. Existing chronological query ordering and explicit-scope duplicate/unknown-ID behavior remain intact.

For “We do not need each protocol to grow with the whole dataset,” protocol tree caching now watches only its complete cohort, including members hidden by filters. It still performs O(M) member fingerprint checks on warm tree requests. That is deliberate freshness work supporting existing in-place mutation behavior, consistent with “memory membership and freshness check”; it is not the SQL membership re-admission eliminated by the new cache. SQL contains/wide-number dictionary preparation remains cohort-dependent query work, rather than project-wide dictionary work.

Bounded eviction and session restart can require rebuilding; temporary/session storage was explicitly accepted. Cold expense alone is therefore not a review defect. This review does not establish native timing, HTTP request counts, or cold-build acceptability; those require the root agent's separate measurements. Green tests were not treated as proof in this review.

Standards: 0 hard findings, 1 nonblocking duplication concern. Spec: 0 actionable findings.
