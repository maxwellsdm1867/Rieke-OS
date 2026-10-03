# GlobalSearch native qualification — 2026-10-03

Code tested: checkpoint `3d9f15fffb8c36e24b799656b073fec45552c2cf` and pilot `a616055d2868fea297666c611016eaf1a1079f0b`. Independent source review cleared the bounded navigation pilot before this run. No push or deployment occurred.

## Method and scope

Actual checkpoint/pilot GlobalSearch components ran in the same diagnostic React shell in an owned Electron 44.5.0 window and isolated profile, automated with Playwright 1.63.0 on macOS arm64. The shell used the pilot's actual read owner/cache. An isolated API/MySQL process used an APFS copy-on-write clone of the cleanly stopped disposable fixture; the granted source project was never started. Backend code is unchanged between these commits. Requests were limited to health, bounded search, author-profile and the existing CellQC GET path. The API rejected mutation requests. Live services, user tabs, chooser/demo and original drafts/tags were untouched; no screenshots or personal/scientific identifiers are included in the public receipt.

Both components received the same stable cell-label query, yielding four results from the same native project. Metadata/index startup completed before sampling. Checkpoint was measured first, followed by pilot, with 20 fresh close/reopen samples each. Cold-query observations have n=1 and are not a startup-performance comparison.

Timing begins at captured input/click events. RAF observations test whether the open dialog has visible, enabled results using DOM geometry. “First useful frame” is that first observation; confirmation waits two more RAF callbacks. This does **not** measure compositor presentation, INP, the full App, or a packaged installation. “Blank frame” means an open dialog with no visible result at that RAF observation, not a recorded screenshot.

## Observations

| Fresh close/reopen, n=20 each | Checkpoint | Pilot |
| --- | ---: | ---: |
| Additional search GETs | 20 | 0 |
| First useful-frame median | 312.2 ms | 7.2 ms |
| First useful-frame p95 | 403.9 ms | 8.0 ms |
| Confirmed-frame p95 | 420.5 ms | 25.6 ms |
| Blank RAF observations, total | 803 | 0 |

One initial query required one GET in each version. Its first useful-frame observation was 353.2 ms at the checkpoint and 304.8 ms in the pilot; these single samples establish no cold-start improvement.

Native keyboard checks passed in both versions: ArrowDown focuses the first result, ArrowUp returns to input, Escape closes, Command-K reopens with input focus, and Enter chooses the result. Pilot cached selections each issued a fresh native CellQC GET; destination data was not cached by this pilot. This checked the real GET path in the diagnostic shell, not the full CellQC workflow or scientific mutation authority.

Controlled expired reads kept four compatible rows visible and disabled while refreshing. Injected 503 retained inert content and allowed explicit Retry; injected 409 cleared rows/retained entries without automatic retry. Actor, same-UUID/different-open-identity and reconnect scope transitions hid previous rows and each dispatched one new native search. These were owner-scope transitions on one project, not a full real-project switch.

A separate **real 30s mounted expiry**, without clock injection, issued exactly one refresh GET. It completed after approximately 30.34s from monitoring start, with 41 inert RAF observations and zero blank observations. Results remained visible but could not be selected during revalidation.

## Bounds and recovery

Twenty distinct native search queries filled the retention limit at 16 entries. After returning to the original query, another 100 close/reopen cycles in five batches made zero additional search GETs. Every batch retained **16 entries / 12,678 estimated bytes / zero in-flight reads**.

Post-forced-GC renderer heap ranged from **14.57 to 14.76 MiB**; it increased approximately 0.19 MiB between first and last batch. Electron's renderer working-set metric ranged from **136.61 to 137.39 MiB**. This short, small-payload run supports bounded cache storage and shows no large memory growth; it does not establish a long-duration heap/RSS plateau. Instrumentation, development modules and forced GC affect these observations.

An actual owned API shutdown reproduced the explicit backend-incarnation limitation: **unobserved backend replacement/stoppage leaves locally fresh rows clickable until expiry or an observed lifecycle/reconnect event**. Freshness starts when the response reaches the client; it is not a server-generation witness. Choosing such a cached row still issued a fresh destination GET, which failed while the API was down. An observed reconnect event revoked the rows. After native API restart, explicit Retry and a new fresh destination GET succeeded.

This is acceptable only for search navigation intent because destination reads and scientific mutation authority remain separate. It must not be generalized to membership, decisions, candidates or mutations without server dependency witnesses. The native host did not run the complete packaged desktop supervisor/preload lifecycle; source/unit coverage of desktop status transitions remains separate.

All 390 granted source files passed before/after hash equality. Nine scientific tables per native API run, including annotation, curation, draft, decision, explorer and binding state, passed equality across three runs. Both source and clone had clean shutdown; the last owned API/MySQL processes exited, ports 8831/5187 were released, and the temporary runtime link was removed. The qualification runner recorded no renderer errors and no writes.

## Evidence and remaining limits

Sanitized machine-readable evidence: [cache-navigation-native-qualification-20261003.json](cache-navigation-native-qualification-20261003.json). Private harnesses, raw process logs and source hashes remain outside the repository in the delegated workspace and temporary fixture.

This is one sequential, non-randomized run on one small native fixture and one machine. Full packaged App focus/lifecycle integration, a real second-project switch, large payloads, long-duration memory behavior, compositor/INP measurements and broader navigation remain unqualified. The proposed all-page warm p95 ≤100ms target is still unqualified. No broader “Slack-fast” claim follows from this result.
