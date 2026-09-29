# New-client validation matrix

This is a coverage ledger, not a claim that all controls work. Inventory is based
on the current React components in `workspace-app/src/components` and `App.jsx`.
The statuses below reconcile the executed browser, HTTP, database, artifact and
unit evidence. Source inspection, a build or a unit test alone does not prove a
browser interaction. `PARTIAL` means the stated main path has evidence but one
or more explicitly named variants remain unexercised; it is not a known failure.

Record status as `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, or `NOT APPLICABLE (reason)`, with a
linked log/screenshot/test result and the tested commit, installation path,
browser, project, and timestamp. A row with several controls passes only after
all listed controls and required cases have evidence. Split a row when only part
passes. `Browser + API` means both interaction and resulting persisted state must
be checked; a successful HTTP request alone does not certify the button.

## Test setup and release gate

Use the newly installed application in a path containing spaces and a separate,
disposable validation workspace. Preserve the user's original H5 files. Perform
lifecycle/curation changes only in the validation project. Use controlled copies
for missing/modified-source tests. Keep an untouched baseline export for
comparisons. Do not put credentials, full personal source paths, raw recordings,
or private project exports in published evidence.

- [x] Record tested baseline and runtime versions (F1); final commit/tree identity must be captured when packaging is frozen.
- [x] Record independent source inventory and expected import successes/rejections (F1, W3).
- [x] Compare original and final source checksums (F1, F2).
- [x] Complete the install → new project → import → browse → curate → export → restart path (R1/B1/B2/Q-UI browser plus F2 API persistence).
- [x] Classify every row below, including partial, unexercised and excluded branches.
- [x] Resolve failures and rerun affected flows on the final candidate (F3, final R1/W3, full suites).
- [x] Release prerequisites pass; source archive scanned (G3). Parent owns final commit/archive regeneration/checksum and publication. Do not claim every UI variant passed.

The supplied data contains 8 original Symphony recordings and 54 legacy
`.auisql.h5` cache files. The user explicitly excludes companion `.auisql.h5`/`asqul.h5` caches from this validation request. Cache-input cases are NOT APPLICABLE by user instruction; original Symphony imports and invalid/nonexistent ordinary `.h5` paths remain required. The known empty-cell import regression must be
retested with the real source: retain source hierarchy cells without inventing
epochs or changing source values.


## Current release gate (reconciled 2026-09-28 PDT)

**All required release gates pass, including the source-archive content scan.**
The standalone workflow, scientific-data audit, main browser controls and final
archive have evidence below. Parent will regenerate the archive after recording
this ledger and the final commit, then checksum the published asset. A partially
covered row does not erase its passing evidence or certify its untested variants.

| Gate | Required outcome | Current evidence / remaining work |
| --- | --- | --- |
| Standalone install and project creation | Clean installation, path containing spaces, native DB, usable new project | PASS: R1 actual launcher/project creation; F1 doctor; F2 fresh project with Docker trap. |
| Original-H5 integrity at scale | All 8 sources, complete hierarchy, unchanged originals, valid metadata/trace links | PASS: F1 867,468 independent checks, 14,908 epochs, no discrepancies; all 27 cells including 2 empty, 43 groups, 454 blocks, 16,273 responses, 14,908 stimuli. |
| Search and working datasets | Typed predicates, save/version, create/update compatible protocol, conflicts | PASS: Q-UI plus F2; C1 shared connection repair stress and browser retest. |
| Main inspection / QC | Navigate exact epochs, source-matched traces, honest measured summaries | PASS: B2 browser; F1 78 exact trace windows; F2 independently checks 15 onset anchors and 11 trial responses. |
| Exports and durability | Actual downloads, exact membership, usable formats, immutable prior exports, restart persistence | PASS: R1/Q-UI browser downloads; F2 JSON/SQLite/MAT/UGM inspection and native SQL restart. MATLAB execution remains outside tested configuration. |
| G1 — actionable failure and recovery | Invalid/nonexistent imports and missing-source recovery give truthful guidance and recover after restoration | PASS after repair: W3 browser nonexistent path now says Request rejected with timer frozen at 0s; missing-source fail-closed behavior and explicit metadata-refresh recovery verified after exact-byte restoration. Local rieke-missing-receipt.json and rieke-import-rejected-fixed.png. |
| G2 — remaining primary controls | Browser review, masks, bulk curation/tags and dataset-only tags | PASS: R1 review/clear, dataset-only tag save/removal (API tags=[]), exact bulk exclusion/clear, actual JSON/UGM mask imports, two-target bulk tags and actual mask download. API/artifact portions pass independently in F2. |
| G3 — final package freeze | Rebuild/sync latest changes, rerun affected tests, record final revision/checksums, confirm no remaining main workflow failure | Software/browser validation PASS: F3 final candidate 20 checkpoints, all 3 named HTTP formats, R1 actual default-named SQLite download; root 522 Python / 193 frontend tests and build pass. Source archive scan PASS: 508 files, 1.445 MB ZIP, clean integrity, no MAT/H5/database/runtime/dependency payloads; install/start executable modes preserved and naming module byte-exact. Parent regenerates/checksums the final asset after commit; no circular repository hash embedded. |

Remaining **variants**, not secretly marked passed: pointer reorder/pan/resize,
narrow viewport, clipboard denial, pagination beyond available fixtures,
every alternative navigation button, delayed-response navigation during save,
second-project query-file import, and every malformed-file pairing in browser.
Relevant API/unit coverage is cited per row and below. Overview date/type filters
and Clear, export-review Escape and reuse-query now
have W3 browser evidence. Separate Cancel and repeated-submit variants remain
unexercised; do not claim every interaction permutation was tested.
The user excluded companion cache files; they are not a release test requirement.
Linked figures is visibly Planned; unavailable spike/RF reconstruction is not
advertised as validated. Windows and MATLAB desktop execution have no evidence
from this Apple Silicon macOS run and must not be represented as validated.

### Evidence keys added during reconciliation

- **R1 — root browser observations:** fresh install in a path with spaces; chose
  absolute workspace parent; created/opened two native projects; original 972-epoch
  path import succeeded after fix; empty first-recording guide expanded/collapsed;
  metadata refresh displays 14,908 epochs after 8-source API stress; focused exclusion
  persisted; authored cell/epoch tags in compact panel; both tag format downloads
  and idempotent reimport; three 589-epoch exports downloaded; reviewed-only export
  disabled at 0 reviewed; Previous exports shows 3; actual IAB mask JSON download has
  590 decisions. Recorded in the active task's browser-tool history, not a synthetic
  local browser receipt. No broader interaction is inferred from this summary.
- **F1 — final candidate, source audit and doctor:** baseline `40a8deb` plus
  working fixes (not a frozen release commit), installed application
  `<temporary>/Rieke release candidate …/Rieke OS`; native validation project
  `a1ebe185-13fd-4975-b960-ba824aee2669`, origin 56681. Runtime: Python 3.11.13,
  DataJoint 2.2.2, MySQL 8.4.2 arm64, Node 22.21.1, npm 10.9.4, Vite 8.3.1.
  Seven doctor checks pass. Owned API restart preserves origin/counts.
  [Independent audit script](../../packaging/verify_catalog_source.py) reads
  original H5 directly and SQL in a read-only snapshot; 867,468 checks, 33.253 s,
  zero discrepancies; 78 HTTP trace windows match exact raw quantities/rates/units.
  Local receipts `rieke-release-candidate-final-audit.json`,
  `rieke-final-candidate-restart.json`, `rieke-final-candidate-doctor.txt` are kept
  outside the distribution. Raw traces and stimulus-generator details remain in
  original H5; SQL stores hierarchy/metadata/locators. Waveform comparisons are
  sampled; derived frame times/stimulus reconstruction are not audited here.
- **F2 — fresh standalone candidate workflow:**
  [Reproducible harness](../../packaging/verify_workflows.py), original 972-epoch
  recording, new disposable native project `05e922bf-19e9-4073-936c-0b6fe159f153`.
  All 20 checkpoint groups pass: query/preset/version/protocol, tree layout, JSON
  masks, dataset curation, shared tags/attribution/conflicts, independent raw trace
  and QC arithmetic, JSON/SQLite/MAT/UGM exact 589 export membership, subset UGM import,
  duplicates, query/source propagation, restart persistence, unchanged original SHA
  and zero Docker invocations. Local receipt
  `rieke-final-candidate-workflows-receipt.json`; complete evidence directory
  `rieke-workflows-l2dgpsno`. This is HTTP/artifact evidence, not browser click proof.
- **C1 — connection-race regression:** unguarded candidate-recipe reads repaired;
  both HTTP concurrency regressions fail before/pass after repair. Real native
  stress 48 requests / 8 threads yields 32 HTTP 200 and 16 expected stale 409, no 500/packet
  errors. Local receipt `rieke-concurrency-native.json`; Q-UI browser retest also
  passed. Earlier ledger references to this failure are historical, resolved.
- **W3 — workflow-agent additional browser run:** project
  `24c3264e-5a0e-4b7f-86a0-c04ebd25486a` on 58459; actual H5 file chooser upload,
  duplicate cleanup, invalid/nonexistent file paths, source propagation 5→6 and
  controlled missing owned copy fail closed tested. Both error/recovery-message issues were repaired and browser-retested; G1 passes. No original source file was altered.

Unit/API coverage for remaining variants is concrete: `test_workspace_predicates.py`
checks nesting, missing/null, Boolean/noncoercion, invalid/resource limits;
`test_workspace_matlab_masks.py` checks logical flags, foreign/duplicate/missing
UUIDs, versions and external links; `test_workspace_annotations.py` checks
cross-cell bulk targets, author removal, optimistic conflicts and atomic rollback;
`test_workspace_tag_exchange.py` checks invalid identity/author/source and additive
legacy format behavior; `test_workspace_refresh_cache.py` checks missing/modified
sources and metadata tampering without publishing invalid cache.
Frontend `predicateState.test.js`, `tagExchange.test.js`, `export-policy.test.js`
and `exportReuse.test.js` cover typed drafts, UUID scope, empty export prevention
and explicit reuse routing. These support, but do not replace, browser evidence.

## Launcher and application shell

| ID | Exact control / case | Preconditions and action | Expected result / oracle | Validation | Status / evidence |
| --- | --- | --- | --- | --- | --- |
| L01 | `./install.sh`, `./start.sh` | Fresh extracted source in a path with spaces, no app runtime; follow quick start | Install exits successfully; localhost launcher loads without Docker; installed runtime passes doctor | Shell + Browser | PASS — F1 shell: fresh installation in a path with spaces, seven doctor checks; R1 browser launcher opened; F2 clean launch/native DB with Docker trap never invoked. |
| L02 | Choose folder → Use this workspace | Enter a new absolute parent path outside application | Marker created and displayed root matches; no unrelated files replaced | Browser + filesystem | PASS — R1 browser: chose new absolute workspace parent and used Use this workspace; subsequent projects created under that parent. |
| L03 | Choose folder → Cancel; invalid root | Open root editor, cancel; separately try application/project root and invalid path | Cancel changes nothing; unsupported root rejected visibly | Browser + API | PARTIAL — L02 path selection passed; cancellation and invalid-root browser variants not exercised. Workspace/project validation has unit coverage; do not infer its dialogs. |
| L04 | Add project → Create & open project | Name supplied, optional folder blank | Unique child directory, native DB starts, correct project opens | Browser + API | PASS — R1 browser: Add project created/opened New client stress test on 54515 and Validated standalone on 55262; F2 independently creates/opens a fresh native project. |
| L05 | Project name / Project folder / Back to projects | Empty name, nonempty existing directory; then cancel | Invalid creation blocked, existing contents preserved, no accidental project | Browser + filesystem | PARTIAL — B1: blank-name disabled and Close project setup passed; nonempty-directory rejection not exercised here |
| L06 | Open project / Continue {name} / project list | Two existing projects, choose each | Correct URL and project identity; records and author selection isolated | Browser + API | PARTIAL — R1 created/opened two distinct projects with separate identities; final candidate reopened at 56681. Switching between two existing project rows and author isolation in that browser not separately recorded. |
| L07 | Show sidebar / Hide sidebar; Back to previous workspace / Forward to next workspace | Visit overview, protocol, search, files; navigate back and forward | Expected route/focus restored; sidebar toggle does not modify data | Browser | PARTIAL — B1: hide/show, stores→files→activity, Back/Forward passed; search/protocol focus restoration not exercised here |
| L08 | Search data; Search project metadata and UUIDs | Search known cell and epoch UUID, typed field expression, no match | Correct identity navigated; predicate uses correct type; no-result state clear; Escape/Close search works | Browser + API | PARTIAL — Q-UI field/predicate search passed; W3 known epoch UUID search opened the correct missing-source epoch. Full global-search no-match/Escape/known-cell variants not separately recorded. |
| L09 | Refresh metadata / Metadata refresh status / Check status / Close metadata refresh status | Imported project with saved working dataset | Current status shown; refresh verifies metadata without silently changing protocol membership | Browser + API | PASS — B1: browser refresh/status/check/close and API verification; 6 reused, 0 rebuilt, 13,936 epochs; bindings remain v1 |
| L10 | Restart and reopen same project | Save curation, preset, export; stop/restart app services through supported lifecycle | Durable records remain; exact identities and counts match pre-restart snapshot | Browser + API + DB | PARTIAL — F2 API/native restart preserves masks, profiles/tags, preset, exports and972-epochs; F1 candidate restart preserves 56681origin and14,908 epochs. Browser-specific author preference restoration remains a separate check. |

## Overview, sources, and import

| ID | Exact control / case | Preconditions and action | Expected result / oracle | Validation | Status / evidence |
| --- | --- | --- | --- | --- | --- |
| O01 | First recording? Start here / Add data store | Empty project; expand/collapse guide and follow action | Guidance readable; import opens; empty state never implies imported data | Browser | PASS — R1 browser: empty first-recording guide expanded and collapsed; Add data store/import path used successfully. |
| O02 | Cell type and recording-date buttons / Clear | Imported multiple cells/dates | Overview cells filter correctly and Clear restores; totals retain defined scope | Browser + independent metadata | PASS — W3 browser ON-midget filter 3→2 cells; combined date/type intersection 0 shows No cells; Clear restores 3. Nov 13 date alone shows 1 unknown-type cell/1 epoch; Clear restores 3. Scope intersections explicit. |
| O03 | Cell rows / protocol rows / QC & typing | Click source cell, experimental protocol, typing protocol | Correct cell QC or protocol opens; names/counts correspond to source | Browser + API | PARTIAL — B1 source-linked protocol and B2 cell QC/protocol rows navigate correctly; root inspected current protocol. Every overview row variant not individually exercised. |
| O04 | Linked figures → Planned | Overview with data | Clearly nonfunctional planned feature, no false upload/edit affordance | Browser | PASS — B1: rendered Linked figures clearly marked Planned, no action control |
| I01 | Choose H5 file / drag-and-drop | Original Symphony file | Upload finishes, parse/validation/catalog finish, import is available; sources unchanged | Browser + API + source comparison | PARTIAL — W3 actual file chooser uploaded an original one-epoch H5 copy; API confirmed source count 2 / epoch count 973. Drag-and-drop alternative not separately exercised; all original hashes preserved in F1/F2. |
| I02 | Import from path | Each of 8 original Symphony files, sequentially | Each terminal result recorded; counts/UUIDs/values validated independently | Browser + API + DB | PASS — R1 browser path import of972-epoch original succeeded after empty-cell fix; F1 all 8 original sources imported via HTTP and independently audited against SQL/H5,14,908 epochs. Browser was not used to click all 8 imports. |
| I03 | Choose H5 file / Import from path: duplicate | Same bytes again, including renamed copy | Duplicate recognized; no extra catalog rows, source state retained | Browser + API + DB | PARTIAL — W3 browser same-file duplicate reports Skipped, API duplicate status and staging removal, unchanged counts; F2 duplicate idempotency passes. Renamed-identical-file variant not separately run. |
| I04 | Import from path: invalid/nonexistent ordinary `.h5` input | Invalid recording and nonexistent ordinary H5 path | Informative rejection, no partial registration or orphan scientific rows | Browser + API + DB | PASS — W3 malformed ordinary H5 fails parsing without partial registration; nonexistent path returns 400/no job. Repaired browser displays Request rejected and frozen 0s timer; screenshot rieke-import-rejected-fixed.png. |
| I04-cache | Companion `.auisql.h5` / `asqul.h5` input | Excluded from requested test scope | No test required | — | NOT APPLICABLE — explicitly excluded by user |
| I05 | Import history / Import evidence & diagnostic details / Refresh jobs | Completed and failed jobs | Accurate terminal status, timestamps, diagnostic details; failed result not called successful | Browser + API | PARTIAL — W3 completed/Skipped duplicate/failed parse diagnostics and repaired rejected-path banner truthful; F2 terminal jobs accurate. Every equivalent evidence disclosure/timestamp control not individually recorded. |
| I06 | Import progress / View data stores / Inspect data stores | In-progress and completed job | Navigation preserves progress; imports cannot silently overlap; source visible only with correct state | Browser + API | PARTIAL — R1/W3 imported and inspected registered sources; F2 jobs complete accurately. Navigate-away during import and overlapping-submit browser variants not separately recorded. |
| I07 | Empty source cell regression | Original recording with source cell that has zero epochs | Import succeeds; all source cell UUIDs retained; recorded epoch count unchanged | API + independent DB/H5 | PASS — F1 direct original H5 ↔ SQL: all 27 cells retained, including2 without epochs;43 groups, 454 blocks14,908 epochs. Empty-block preservation also verified;867,468 checks, zero discrepancies. |
| S01 | Check sources / source search / Current, Archived, All / pagination | Registered sources, enough rows for paging or fixture | Availability updates; search and tabs scoped accurately; pages do not lose rows | Browser + API | PARTIAL — B1: Check sources, search, Current/Archived/All passed; only 6 sources, >50 paging not exercised |
| S02 | Source row / detail navigation / linked protocol / saved export | Source with protocols and exports | Correct source details, exact linked protocol/export; back navigation works | Browser + API | PARTIAL — B1: source detail, Single Spot link and Back restoration passed; no source exports existed to test download |
| S03 | Manage → Freeze registration / Unfreeze | Mutable source | Confirm/cancel honored; frozen participation/archive controls disabled; epoch curation remains usable | Browser + API | PARTIAL — B1: cancel, freeze, disabled participation/archive, unfreeze passed; curation while frozen not exercised |
| S04 | Manage → Archive registration / Restore to current list | Unfrozen source | Visibility changes only; query participation, raw files, datasets, exports retained | Browser + API + DB | PARTIAL — B1: archive/restore browser+API passed, source remained query-included; no baseline exports existed to test retention |
| S05 | Exclude from queries / Include in queries / Reason / Cancel | Source used by search and saved protocol | New query eligibility changes only after confirmation; old working dataset retained pending propagation | Browser + API | PARTIAL — B1 browser exclude/include/cancel/state restoration passed; F2 independent query/protocol propagation changes 590→0→590 with exact sets. Additional browser variants tracked in W3. |
| S06 | Propagate changes → Details / Apply update / Refresh proposal / Back to data store | Source eligibility changed; saved protocol affected | Diff exact; confirmed application updates correct dataset once; stale proposal rejected; earlier export unchanged | Browser + API + independent membership | PARTIAL — W3 browser new-source Details shows5→6 epochs,2→3 cells,+1; Apply yields Up to date/version 2 and exact added UUID via API. F2 stale proposal rejection and590→0→590 propagation pass; Refresh proposal variant not separately recorded. |
| S07 | Recorded event details / linked history / Show more | Source with history and several links | Lazy details load; links and pagination stay on selected source | Browser + API | PARTIAL — B1: source-linked timeline and Refresh source activity passed; >50 events/Show more links not exercised |
| S08 | Missing or modified H5 | Controlled copy referenced, then move/alter only that copy | Source check and trace/export surface problem; no misleading old trace or silent mutation | API + Browser | PARTIAL — W3 controlled owned-upload rename shows File missing and trace/export fail closed, export count unchanged6. Restored exact source SHA; repaired guidance and explicit Refresh metadata recover 10 samples. Modified-byte detection covered by refresh-cache unit tests, not a separate altered-file browser test. |

## Search predicates and saved queries

| ID | Exact control / case | Preconditions and action | Expected result / oracle | Validation | Status / evidence |
| --- | --- | --- | --- | --- | --- |
| Q01 | Search predicate / New predicate / Choose field / Find predicate field / Predicate field group / Show more | Imported metadata | Recorded fields and typed examples available; keyboard and pointer choose same field | Browser + API | PARTIAL — Q-UI browser field search/category and typed field selection passed; Show more and every pointer/keyboard variant not individually recorded. |
| Q02 | Condition operator / Condition value / Choose a recorded value | String, number, boolean, null, list, missing-field examples | Predicate types preserved; match set agrees with independent evaluation | Browser + API + Unit | PARTIAL — Q-UI browser strings/numbers, recorded-null 972, missing 0 and array [800,600] matching 972 validated; predicate units cover Boolean noncoercion. Supplied catalog has no recorded Boolean field example for browser execution. |
| Q03 | Condition / Add condition below / Remove condition / Group / Remove nested group | Multi-condition draft | Correct logical structure and depth limits; deleting never executes query automatically | Browser + Unit | PARTIAL — Q-UI browser add/remove conditions and groups passed; depth/resource limits covered by predicate units, not browser stress. |
| Q04 | Root group logic / Nested group logic / Condition options / Negate condition (NOT) / Value type | All/Any/None and negation fixtures | Matching rules accurate; invalid values visibly blocked; missing distinct from null | Browser + API + Unit | PARTIAL — Q-UI browser All/None/NOT, emptyAny, invalid-number rejection and null/missing distinctions passed; typed/nesting units cover additional shapes. |
| Q05 | Preview matches / Exact predicate / View matching epochs | Valid, zero-match, invalid draft; edit after preview | Counts and displayed stale preview truthful; result UUIDs match predicate | Browser + API + independent membership | PASS — Q-UI preview/counts5,3,967,140,0 and matching results exercised; F2 API checks exact membership and rejects unknown fields; zero-result export disabled. |
| Q06 | Cancel / Close predicate editor / Escape | Unsaved draft | Dialog closes without applying unintended dataset changes | Browser + API | PASS — Q-UI Cancel and Escape close unsaved predicate editor without applying a protocol update. |
| Q07 | Suggested predicates / saved-search row / Edit {name} / Find a search preset | Existing project and device searches | Run uses current catalog; edit opens correct predicate; filtering scope clear | Browser + API | PARTIAL — Q-UI suggested predicate, saved search/edit and field selection exercised; exhaustive project/device shortcut filtering variants not separately recorded. |
| Q08 | More → Save query preset / Save new search / Save existing search | Run search; save; update same conditions and changed conditions | Durable preset; version/duplicate semantics correct; no protocol mutation | Browser + API + DB | PASS — Q-UI browser preset create/update/history; F2 version1→2 persistence and stale-edit rejection with immutable revisions. |
| Q09 | Pin {name} / Unpin {name} / Refresh project saved searches / history | Saved preset; reopen project/browser | Project pins/history persist; device shortcut distinction accurate | Browser + API | PARTIAL — Q-UI browser pin/history passed; F2 preset persists through SQL/server restart. Unpin and every device-shortcut reload variant not individually recorded. |
| Q10 | Download {name} query JSON / Import query | Export saved preset; import into same and second data-loaded project | Draft opens for review; no raw data/frozen membership copied; invalid JSON rejected | Browser + API | PARTIAL — Q-UI actual downloaded query JSON reimported in same project; malformed JSON rejected visibly. Cross-project query-file import not exercised; does not certify cross-project migration. |
| Q11 | More → Save selection revision / Saved query revisions / Save current revision / Save tree revision | Search result; then change draft/tree | Exact membership snapshot retained; unsaved changes flagged; stale source save rejected | Browser + API + independent membership | PARTIAL — Q-UI browser saves selection revision; F2 exact immutable membership and parent revisions verified. Save tree revision/stale-source browser variants not separately recorded. |
| Q12 | Result Export → Export directly / Export result | Saved nonempty search result | One-off artifact membership equals candidate, does not create or mutate protocol/pin | Browser + API + artifact inspection | PASS — Q-UI direct SQLite and MATLAB downloads contain5 candidate epochs, independently inspected; candidate scope avoids creating/updating protocol. |
| Q13 | Result Export → Create pinned protocol | One acquisition Protocol ID; also mixed-protocol/zero-match cases | Valid selection creates independent protocol; incompatible cases blocked visibly | Browser + API | PASS — Q-UI created5-epoch pinned protocol; mixed-protocol creation and zero-result export blocked. Shared-connection race fixed; C1 native48 requests / 8 threads and Q-UI retest passed. |
| Q14 | Result Export → Update pinned protocol / Target protocol / Show changes / Hide changes / Update pinned protocol | Compatible target; narrower and incompatible candidate | Exact diff, removal acknowledgment required, stale/incompatible apply blocked, correct destination updated | Browser + API + DB | PASS — Q-UI narrowed 5→3 with exact diff/show-hide/removal acknowledgement; incompatible destination disabled. F2 API compare/apply 590→1→590 and stale-binding rejection. |

## Protocol, tree, epoch navigation, and traces

| ID | Exact control / case | Preconditions and action | Expected result / oracle | Validation | Status / evidence |
| --- | --- | --- | --- | --- | --- |
| P01 | Protocol Overview / Inspect epochs / Go to epochs / Open inspection | Protocol with multiple cells | All entry points open same protocol; focused cell and global scope shown truthfully | Browser + API | PARTIAL — B1/B2 and R1 enter protocol inspection and QC and return correctly; every equivalent entry-point button not individually recorded. |
| P02 | Filter by cell type / Filter by source group / Clear filters | At least two values | Visible membership/filter/export scope agree; clearing restores | Browser + API | PARTIAL — Q-UI narrowed query membership verified and R1 focused-cell mask tested; protocol cell-type/source-group filter buttons and Clear not separately recorded. |
| P03 | Refresh & compare / Review update / new-data proposal | Saved protocol plus new eligible source | Diff accurate; no auto-apply; reviewed update changes intended membership only | Browser + API | PARTIAL — B1 proposal preview never silently applied; W3 browser reviewed/applied new-source5→6 update; F2 independent propagation verified. Protocol-specific Refresh & compare entry-point variants not individually recorded. |
| P04 | Browse epochs / Design tree / Epochs / Split tree / More → Show epoch list or Hide epoch list | Open protocol inspection | Views switch without losing saved curation; hidden list recoverable | Browser | PASS — B2: Browse/Design/Epochs/Split tree and More Hide/Show epoch list work; focus remains inspectable |
| P05 | Add a split / Find a split field / categories / Show 40 more fields / Close split chooser | Large field catalog | All available fields reachable; selection correct; keyboard/Escape works | Browser + Unit | PARTIAL — B2: chooser/search/Enter add passed; exhaustive categories, Show40more and Escape variants not exercised |
| P06 | Reorder {field}, level {n} / Show move controls / Move {field} earlier or later / Remove {field} grouping | Three splits; drag and keyboard variants | Identical order by both methods; persistent layout matches visible order; cancellation safe | Browser + API | PARTIAL — B2: Alt+Up, Show move controls, Move later, remove and reload persistence passed; pointer reorder/cancel not exercised; API layer covered by workflow suite |
| P07 | Quick tree layout / Date → Cell → Epoch group → Block / Flat list / Use suggested protocol layout | Applicable protocol | Correct grouping with unchanged leaf membership; unsupported fields disabled | Browser + API | PARTIAL — B2: Flat list, acquisition preset and Quick tree layout passed with 1,649 leaves; suggested-layout button not exercised |
| P08 | EpicTreeGUI code / Copy EpicTree code | Current preview; stale preview | Current matching command copied, stale command disabled; clipboard failure visible | Browser | PARTIAL — B2: current generated command displayed and Copy reported success; clipboard rejection/stale-click cases not induced |
| P09 | Tree expand/collapse, paging, epoch focus | Large multilevel tree with off-page selected epoch | No missing/repeated leaf UUIDs; focus matches trace; collapsed selection preserved | Browser + API + Unit | PARTIAL — B2: date→cell→block expansion, epoch focus, Collapse all passed; exhaustive off-page UUID coverage not inferred |
| P10 | Previous epoch / Next epoch / W / S / Tab / Shift+Tab | Middle, first, last epochs; active text field | Correct boundaries/focus; typed input retains normal key behavior; pending save handled safely | Browser + Unit | PARTIAL — B2: epoch1 boundary, S/W and Tab/ShiftTab1↔2 passed; last-epoch and pending-tag-save cases not induced |
| P11 | Details / Tags / Cell QC / Back to filtered tree (when present) | Focused epoch/cell; navigate between scopes | Correct metadata/tag/typing context; return restores intended scope | Browser + API | PARTIAL — B2: Details show/hide and Cell QC/Back work; tag mutations and filtered-tree return covered separately |
| P12 | Resize tree/metadata pane; narrow browser viewport | Inspector and tree views | Handles and overlays usable; controls not clipped; saved dimensions safe after reload | Browser | PARTIAL — B2: keyboard pane resize270↔280 and 320↔330 passed, original values restored; narrow viewport/pointer resize not exercised |
| P13 | Response stream | Epoch with two streams; then switch epoch rapidly | Selected device/units/rate/UUID match source; stale response never plotted | Browser + API + H5 | PARTIAL — B2: Amp1 mV↔Frame Monitor V switch passed; monitor sample150 independently equals5.8875V; delayed-response race not induced |
| P14 | Drag to zoom / Pan / Zoom in / Zoom out / Reset | Trace loaded | Window bounds correct; Y scale labeled; no resampling/filtering falsely implied | Browser + API + H5 | PARTIAL — B2: pointer drag zoom, Zoom in/out, Reset, Pan toggle and keyboard pan passed; pointer-pan movement not confirmed |
| P15 | Previous window / Next window / Start sample / Sample count / Show window | Long trace; invalid and boundary values | Exact bounded samples/time coordinates; invalid request rejected; source values match | Browser + API + H5 | PARTIAL — B2: exact100–299sample window, next/previous windows and end-boundary disabled states passed; invalid-entry case not induced |
| P16 | Exact sample index for cursor / plot arrow, Shift+arrow, +/−, Home | Trace loaded and plot focused | Cursor value and units equal raw source sample; controls stay within bounds | Browser + H5 | PASS — B2 exact H5 cursor150/151, Arrow/ShiftArrow/Home; follow-up keyboard+/−7,500-sample window 0–7499→1875–5624→0–7499 verified. |
| P17 | Retry trace / loading/error display | Controlled unavailable source or server interruption | Error clear; retry recovers same requested identity; old trace not shown as current | Browser + API | PASS — W3 missing owned-source copy shows error/Retry and export fail closed; after exact-byte restoration, clear metadata-refresh guidance and explicit Refresh recover 10 samples. Receipt rieke-missing-receipt.json. |
| P18 | Organize protocols / Pin or Unpin / Tuck away or Show / Move up or down / drag / Done | Several protocols | Order/sections persist on device; scientific datasets unchanged | Browser + API | PARTIAL — B2: organize, pin/unpin, tuck/show, move up/down, Done passed and original ordering restored; pointer drag not exercised |

## Cell quality workbench

| ID | Exact control / case | Preconditions and action | Expected result / oracle | Validation | Status / evidence |
| --- | --- | --- | --- | --- | --- |
| V01 | Back to workspace / Refresh cell quality / Copy cell UUID / Temperature & recording conditions | Cell with source metadata | Correct return and copied UUID; recorded temperature/resistance values preserved; missing data not inferred | Browser + API + H5 | PARTIAL — B2: Back/refresh/Copy action/temperature/resistance panels passed; copied clipboard bytes not independently read |
| V02 | Characterization protocol buttons / trial rows / Previous / Next / Tags / Show metadata / Hide metadata / Epoch details | Cell with several QC protocol families and >40 trials or fixture | Correct trial/stream/metadata identity; unrecorded family disabled; paging/focus/tag scope accurate | Browser + API + H5 | PARTIAL — B2: SingleSpot↔InjectedNoise,462-trial pages1–40↔41–80, metadata show/hide and unavailable-family disabled states passed; tag editing handled separately |
| V03 | Measure block onsets / Hide measurements / Method, exclusions & provenance | Recording with valid baseline windows plus missing/ineligible examples | Statistics match independently calculated samples; exclusions explicit; no resting-voltage claim | Browser + API + independent H5 calculation | PASS — B2 browser Measure/Hide/method panels; real cell13 onset anchors labeled estimates; independent arithmetic covered by successful workflow API receipt |
| V04 | Compare conditions in this block / Hide comparison / View trial / Method & coverage details / Response timing & measurement method | Repeated conditions with source timing/units | Means and used/total trial coverage correct; View trial opens correct UUID; raw-signal summaries not mislabeled firing rate or sensitivity | Browser + API + independent H5 calculation | PASS — B2 browser Compare/Hide/View trial/method/timing panels; invalid timing returns unavailable; independent raw-sample arithmetic covered by workflow receipt |
| V05 | Analysis availability & reconstruction / Cell provenance | Supported and unavailable analysis capabilities | Availability/reason truthful; no actionable-looking dead analysis control or invented scientific result | Browser + API | PASS — B2: available/unvalidated/unavailable capabilities and source-provenance disclosure truthful; no fictitious analysis buttons |

## Curation, masks, profiles, and tags

| ID | Exact control / case | Preconditions and action | Expected result / oracle | Validation | Status / evidence |
| --- | --- | --- | --- | --- | --- |
| C01 | Include focused epoch / Exclude focused epoch | No checkboxes selected | Only focused protocol epoch changes; saved on refresh/reopen; source untouched | Browser + API + DB | PASS — R1 browser focused Exclude persisted false; focused Include confirmed true through API, then restored excluded. F2 full-mask and exact589/590 export membership independently confirm semantics; originals unchanged. |
| C02 | Epoch checkboxes / Include {n} selected / Exclude {n} selected / Clear | Select across cells/collapsed branches; focus unselected epoch | Exactly checked UUIDs changed; Clear changes targets only; export scope independent | Browser + API + independent membership | PARTIAL — R1 browser checked only epochs 2+3; Exclude 2 selected changed excluded count 1→3; complete mask restore returned 1 excluded. Focused first epoch not accidentally targeted; targets cleared. Across-cell/collapsed-branch variants not separately browser exercised. |
| C03 | Optional review marker / Mark focused epoch reviewed / Clear focused epoch review marker / Mark {n} selected reviewed | Included and excluded epochs | Review independent of inclusion/tags; export restriction only when chosen | Browser + API | PARTIAL — R1 browser marked included epoch 2 reviewed, API confirmed approved=true; Clear review restored unreviewed. Reviewed-only export disabled at zero reviewed. F2 stale-save rejection passed; multi-selected review variant not separately recorded. |
| C04 | More → Selection masks / Save JSON mask | Protocol filtered to one cell; some exclusions | File covers full protocol, not visible subset; identities and flags exact | Browser + artifact inspection | PASS — R1 actual IAB download recording-mask-62a39455.json contains590 full-protocol decisions. Final attachment endpoint regression passes. Chrome automation emitted no download event despite200attachment; actual IAB artifact is the browser evidence. |
| C05 | Import JSON mask | Saved matching mask; modify decisions then restore | All protocol inclusion flags restored; tags/review unchanged; mismatch/partial/foreign mask rejected atomically | Browser + API + DB | PARTIAL — R1 actual JSON file chooser imported590-decision baseline and restored exact flags (one excluded), matching baseline bytes; F2 stale import rejection passed. Foreign/partial/mismatched-file browser variants not all exercised. |
| C06 | Import MATLAB UGM / Match completed MATLAB export / Choose UGM file / Apply MATLAB mask | Completed MATLAB export and UUID-based v1.1 UGM | Only matched export epochs updated; ambiguity requires explicit match; foreign/old/invalid UGM rejected | Browser + API + artifact inspection | PARTIAL — R1 actual file chooser selected589-export selection.ugm, automatic match and Apply returned589 by UUID; all 590 protocol flags stayed identical and nonexported excluded first epoch preserved. F2 rejects wrong export; malformed/legacy cases unit covered. MATLAB desktop execution not claimed. |
| T01 | Choose tag author profile / New author name / Create profile / existing profile / Close tag author | Fresh browser/project and two profiles | Explicit author selection; blank rejected; remembered per project; closing permits browsing | Browser + API | PARTIAL — B1 close-without-author allows browsing; R1 author selected for tagged edits; F2 creates profile and persists through restart. Blank-name/create/existing-profile browser variants not all individually recorded. |
| T02 | Add an epoch tag… / Add a cell tag… / Add tag / Enter | Select intended scope/author | Exact direct scope and attribution; cell tags inherited on linked epochs without duplicating direct tags | Browser + API + DB | PASS — R1 browser added cell and epoch tags in compact visually verified panel; F2 SQL/API attribution and inherited cell tag verified; authored tag scope distinct. |
| T03 | Tag selected epochs / Tag {n} epochs / selected target clearing | Multiple target UUIDs including other cells | Exact selected set tagged; max bulk size enforced; no accidental whole-cell promotion | Browser + API + DB | PARTIAL — R1 browser checked epochs 2+3, Tag selected epochs added client-bulk to exactly those 2; API first 3 epochs confirms first untagged; targets cleared. Cross-cell and maximum-size variants covered by annotation regression, not separately browser exercised. |
| T04 | Tag suggestions / remove tag / tag-based search | Same tag by two authors, cell and epoch scopes | Correct author/scope removed; other author's tag preserved; search membership correct | Browser + API | PARTIAL — R1 browser removed clientcheck epoch tag and clientcell cell tag, API confirmed both; F2 exact tagged-epoch predicate and stale-author conflict checks pass. Two-author preservation/removal unit covered; every suggestion-browser variant not individually recorded. |
| T05 | Dataset-only tags: add/remove | Protocol epoch also in another protocol | Only target dataset curation changes; shared tags remain independent | Browser + API + DB | PARTIAL — R1 Dataset-only tags disclosure, client-dataset save and exact protocol tag confirmed; focused Remove completion confirmed API tags=[] and review=false. F2 persistence and distinct shared scope pass; second-protocol browser isolation variant not separately exercised. |
| T06 | Import tags / Choose tag JSON / Cancel / Import tags / Done | Rieke and Samarjit fixture; unknown UUID, bad JSON; no author | Preview accurate; cancel no write; author required; valid additions preserve existing tags and authors | Browser + API + DB | PARTIAL — R1 browser reimports exported tags idempotently; F2 additive preview/apply/conflict behavior passes. Invalid UUID/author/document and rollback cases unit covered; every Cancel/no-author browser variant not exercised. |
| T07 | Export tags / Which tags / File format / Download tags | Project, focused cell, focused epoch; both formats | Download scopes and attribution exact; reimport idempotent; masks/dataset-only tags not falsely included | Browser + API + artifact inspection | PARTIAL — R1 actual browser downloads both Rieke and Samarjit formats and reimports idempotently; F2 independent export carries correct cell/epoch tags. Each project/cell/epoch scope-selector variant not individually browser exercised. |
| T08 | Profile/selection/navigation during pending save | Slow response or controlled delay | No cross-epoch/cross-author mutation; pending UI truthful; failure leaves recoverable draft | Browser + API + Unit | PARTIAL — API optimistic revisions and atomic conflicting-batch rollback verified; deliberate slow-response profile/navigation browser race not induced. No claim of manual race coverage. |

## Export, logs, and project files

| ID | Exact control / case | Preconditions and action | Expected result / oracle | Validation | Status / evidence |
| --- | --- | --- | --- | --- | --- |
| E01 | Export / Export name / Export membership / Save & export {n} epochs | Protocol with inclusions, exclusions, reviewed/unreviewed; focus and checkboxes differ | Scope/count accurate; included vs reviewed-only exact membership; empty export blocked | Browser + API + artifact inspection | PARTIAL — R1 browser all 3 formats export589 included epochs; reviewed-only disabled at zero; F2 independently compares exact UUID sets. Reviewed-only nonzero subset and repeated-submit variants not all browser exercised. |
| E02 | Wheeler SQL database / Download SQLite database | Protocol and one-off candidate exports | SQLite readable; metadata, UUIDs, inclusion, provenance/H5 references correct; raw waveform omission clear | Browser + independent SQLite audit | PASS — R1 browser protocol SQLite 589 download and Q-UI candidate SQLite 5 download; F2 independently checks integrity, foreignkeys, exact membership, shared annotations and raw H5 references. |
| E03 | EpicTreeGUI / Download MATLAB bundle | Protocol and one-off candidate exports | Bundle opens; expected MAT, launcher, query, mask contents; membership/paths correct | Browser + artifact audit; MATLAB runtime if available | PARTIAL — R1 browser protocol MATLAB 589 bundle and Q-UI candidate MATLAB 5 bundle downloaded; F2 inspectsMAT metadata, frozen JSON and UGM exact membership. MATLAB desktop execution not performed and not claimed. |
| E04 | Advanced formats → Reference JSON / Download JSON | Nonempty selection | Valid reference package; membership and query correct; no claim it imports as a mask | Browser + artifact inspection | PASS — R1 browser Reference JSON 589 download; F2 parses exact included UUID set and keepsreference package distinct from mask. |
| E05 | Close export options / Cancel / Escape / repeated submit while busy | Unsaved export or export running | Safe close behavior, no unintended duplicate export, clear success/failure | Browser + API | PARTIAL — W3 browser Escape closes both candidate and protocol export-review dialogs without exporting; API export count remains 6. Repeated submit while busy and separate Cancel-button variant not induced. |
| E06 | Export log / Refresh / Saved export download / Export record & provenance | Multiple formats and versions | Correct downloadable artifacts, exact counts, identity and provenance | Browser + API + artifact inspection | PARTIAL — R1 Previous exports shows 3 formats and actual downloads complete; F2 list/immutable artifact/provenance checked. Every Export log refresh/details equivalent button not individually browser recorded. |
| E07 | Reuse query / Review & export again / Previous exports | Earlier export then source/curation changes | Opens correct saved query for explicit review; never rewrites prior artifact or auto-exports | Browser + API + checksum comparison | PASS — W3 candidate Review & export again reopens current 6 vs old 5 for explicit review; changed SingleSpot Reuse query blocks with original-preservation message; protocol Reference JSON reuse retains selected format/current 588 vs old 589. Escape creates nothing; all 6 artifact SHA values match saved records and earlier direct SQLite/MAT bytes unchanged. |
| E08 | Export name / export date / downloaded filename | Protocol and candidate exports; default and custom labels; existing export | Default label uses protocol and export date; chosen label determines new download filename; saved naming immutable; older exports unaffected | Browser + API + artifact headers | PASS — R1 actual default Variable_Mean_Noise_current_injection_2026-09-28 and 589-epoch SQLite download with that exact filename, no added ID/spaces; screenshot rieke-export-name-date.png. F3 all 3 HTTP formats verify chosen custom name/date and frozen recipe. Downloaded SQLite integrity and exact 589 membership also pass; focused API tests cover candidate/default/legacy naming. Unexercised interaction variants remain disclosed above. |
| A01 | Activity & logs / Refresh / Filter history by action / Search this history page | Imports/tags/masks/exports/lifecycle events exist | Expected audit evidence found with correct actor, inputs, outcome; page-only search labeled | Browser + API + DB | PARTIAL — B1: Refresh, frozen-action filter, UUID search and exact lifecycle audit passed; other event families left to their executors |
| A02 | Event row / Complete event · changes, inputs, outputs and versions / Older / Newer / Open for review | Several event pages and suggestions | Exact event loaded; paging complete; review link not a silent mutation | Browser + API | PARTIAL — B1: event/complete details and Older/Newer passed; Open for review not exercised |
| F01 | Files & database / Refresh / H5 data stores | Populated project | Correct managed root/database state; navigation reaches sources | Browser + API | PASS — B1: correct root/running database, page Refresh, Project files and H5 data stores navigation passed |
| F02 | App code location · separate from project data / Physical database storage | Native DB project | Locations accurate; credentials not exposed through listing; managed DB contents restricted | Browser + API | PASS — B1: app/source locations separate; SQL directory restricted and HTTP400 on direct browse; credentials not exposed in metadata listing |
| F03 | Storage section buttons / folder rows / Up one directory / breadcrumbs / Previous files page / Next files page | Nested managed files and >100 listing fixture | Paths bounded to managed root; pagination exact; read-only behavior | Browser + API | PARTIAL — B1: all9 sections, nested folder/up/root passed; API traversal rejected; >100-entry paging not exercised |
| F04 | Referenced recordings / Source identity | Uploaded and external sources | SHA/path/availability and managed/external labels accurate | Browser + independent source inventory | PARTIAL — B1: six external references available; uploaded source and expanded SHA display not exercised here |

## Controls requiring special attention

- **Linked figures** is explicitly marked **Planned**. Confirm the rendered badge;
  do not count it as working figure attachment functionality.
- **Choose folder** is a path-entry editor, not an operating-system directory
  picker. Confirm the absolute-path instructions are visible.
- **Checkbox selection**, **focused cell**, **protocol inclusion**, **query
  membership**, and **export scope** are distinct. A click that “looks right” is
  insufficient; compare exact epoch UUID sets after mutations and in artifacts.
- **Save query preset** saves a reusable method. It does not freeze membership or
  update a protocol. Device shortcuts and project saved searches persist in
  different places.
- **Archive registration** changes visibility; **Exclude from queries** changes
  eligibility; **Propagate changes** updates saved datasets. Verify all three
  independently and check old exports remain unchanged.
- **Import JSON mask**, **Import tags**, **Import query**, and **Import MATLAB UGM**
  accept different formats. Confirm rejection of each wrong-file pairing; avoid
  implying general cross-project migration.
- **Refresh metadata** and **Refresh & compare** do not apply protocol updates.
- **Backups** is reserved storage, not a backup-creation button. **Storage moves**
  is an audit filter, not proof a migration UI is implemented.
- Retry controls, pagination beyond the first page, disabled controls, collapsed
  panels, keyboard-only operation, dialog cancellation, stale revisions, and
  asynchronous errors need explicit cases rather than being inferred from happy
  paths.

## Evidence ledger

Append results here or link per-row artifacts. Use small, redacted summaries;
keep detailed local scientific checks outside the source distribution when they
contain private data.

| Date / commit | Row IDs | Executor / environment | Observed result | Evidence | Remaining limits |
| --- | --- | --- | --- | --- | --- |
| 2026-09-28 PDT / 40a8deb + working fixes | L05,L07,L09,O04,S01,S03–S06,A01–A02,F01–F04 | B1: onboarding-guidance agent, Chrome, baseline project on localhost:54515 | Executed browser cases and read-only API checks detailed below | CUA tab 2115893397; audit event 3f736741-6b84-469c-a8a1-1ceb99f60e5f; local API receipts | Baseline package only; partial rows specify untested branches |
| 2026-09-28 / local pre-release | Q05, Q08–Q11, Q13, P06, C01, C03–C06, T01–T02, T04–T07, E01–E04, E06–E07 | Workflow subagent / disposable native macOS HTTP project | API/artifact portions passed on a 972-epoch original H5, including a 590-epoch query and 589-epoch exports: version conflicts, inclusion masks, author attribution, tag exchange stale previews, independent JSON/SQLite/MAT/UGM reads, wrong-export UGM rejection, immutable download bytes | `packaging/verify_workflows.py`; local receipt `rieke-workflows-92h8lnk1` | Browser interactions and all listed edge-case variants remain separate; no MATLAB execution claimed. Overall run failed later on overview audit-event SQL sort memory, reported for repair. |
| 2026-09-28 / local pre-release | V03, V04 | Workflow subagent / original H5 independently read with h5py | All 15 returned onset anchors and 11 measured condition/trial responses agree with independent raw-sample arithmetic; three additional HTTP trace windows agree exactly | Local `qc-baselines.json`, `qc-summary-*.json` in receipt directory above; reproducible script | API calculations verified; browser buttons and MATLAB pipeline interpretations are not inferred. |
| 2026-09-28 / local pre-release | Q14, S05–S06 | Workflow subagent / same disposable native project | Follow-up HTTP test passed query compare/apply 590→1→590 with stale binding rejection, then exclude propagation 590→0 and include propagation 0→590 with stale preview rejection | `verify_propagation` in `packaging/verify_workflows.py`; same local project as above | Confirmation dialogs/browser controls remain separate; overall fresh-run receipt awaits audit sort-memory repair. |

### B1 — baseline browser controls, 21:33–21:40 PDT

Environment: baseline disposable `New client stress test`, project UUID
`de43e8cb-285f-4aef-a155-73d9da55854c`, six imported sources/13,936 epochs.
Independent Chrome tab `2115893397`; parent final-package tab untouched.
All source-file content remained read-only. Application source at `40a8deb` with
in-progress fixes; this does **not** replace final-package retesting.

- Closed the optional Tag author dialog without selecting an author; browsing
  remained available. Opened Add project, observed empty-name Create & open
  project disabled, and closed the dialog without creating anything.
- Filtered Data stores to `2025-11-13_F.h5`. Cancelled the initial Freeze dialog,
  then froze with reason `UI validation reversible lifecycle`. UI showed Frozen,
  disabled Exclude from queries and Archive registration, then successful
  Unfreeze restored them. Audit event `3f736741-6b84-469c-a8a1-1ceb99f60e5f`
  records frozen false→true, version0→1, and that exact reason.
- Archived the registration: Current 6→5, Archived 0→1, All 6. Archived tab showed
  Available/Archived **and still Included in queries**. Restored registration:
  Current 6, Archived 0, All 6. Confirmed each action's completion result.
- Excluded from queries, reviewed the proposal and expanded Details. Single Spot
  version1 showed current1→proposed55 epochs (+55/−1), correctly explaining that
  propagation reruns the full query across all eligible sources. Left via Back
  to data store without applying; restored Include in queries.
- Final read-only `/api/data-stores` receipt: active6, archived 0, frozen 0,
  query_excluded 0, total 6. Tested registration version6 with archived=false,
  frozen=false, query_excluded=false. No propagation applied. `/api/overview`
  still shows all five protocol bindings at version1, including Single Spot1
  epoch, Variable Mean Noise1,640 and current injection1,649.
- Files & database: nine section buttons work; parsed recording folder exposes
  seven file metadata rows; Up one directory and Project data breadcrumb work;
  empty folders labeled explicitly; pagination disabled appropriately at <=12
  items. Main database displays MySQL as Restricted, without an open control.
  App code location and Physical database storage disclosures work. API browse
  of `database/mysql` and `../` both returns 400. `native.json` appears as filename
  metadata only, with no content/download action.
- Activity: action filter Data store frozen returns one event; expanded event
  and Complete event disclose the expected versioned change. Searching its UUID
  prefix returns one match. All actions + Older and Newer navigate history pages;
  Refresh works. Page search correctly did not match an arbitrary reason string
  (its placeholder promises author/tag/actor/event-ID search, not all payloads).
- Hide sidebar/Show sidebar work. Application Back returns activity→files and
  Forward returns to activity. Metadata refresh/status/Check status/close work;
  completion reports six reused, zero rebuilt, 13,936 epochs, five protocols,
  2.01s. Read-only metadata status confirms completion at
  `2026-09-29T04:38:35.053124+00:00` and source-cache reuse.
- Captured restored-source screenshot in the CUA tool result (not published;
  no private paths included in that view). Current 6/Archived 0/All 6, zero frozen,
  Available and Included in queries are visible. No blocking functional failure
  found in these executed paths. Minor existing display observations: native
  database runtime says Not reported despite running status; one overview
  duration formatted as 5m60s. Neither was treated as an integrity failure.
| 2026-09-28 / local pre-release, audit pagination fix | Q05,Q08–Q11,Q13–Q14,P06,C01,C03–C06,T01–T02,T04–T07,E01–E04,E06–E07,S05–S06,V03–V04 | Workflow subagent / clean disposable native Apple Silicon project | Expanded reproducible HTTP/artifact suite PASSED end-to-end: 972 imported epochs, 590-member query, 589 included epochs independently checked in JSON/SQLite/MATLAB bundles; 15 onset anchors and 11 trial means matched H5 arithmetic; conflict handling, duplicate import, propagation, immutable artifacts, SQL/server restart persistence, unchanged source hash and zero Docker invocations | `packaging/verify_workflows.py`; successful local receipt `rieke-workflows-085fojyh/receipt.json` (20 checks). Previously failing unchanged project also recovered on patched server without DB tuning. | API/artifact coverage only; matrix browser controls, unexecuted variants and MATLAB execution retain their own status. |

B1 follow-up at 21:41 PDT: opened the filtered source detail, saw its Single Spot
one-epoch link and zero exports, opened that protocol and used application Back
to restore the source detail. Source timeline shows all six reversible lifecycle
actions; Refresh source activity works. Project files navigates to Files &
database; page Refresh works; H5 data stores returns to the selected source.
This completes F01 but does not certify a source export-download control without
an existing export fixture.

### B2 — real-cell QC, trace, tree and sidebar browser controls

Executed after B1 in independent Chrome tab `2115893401`, baseline port54515;
parent project/tab untouched. No source files, curation, authored tags, or
protocol membership changed. Changed only tree/pane/sidebar presentation;
restored the protocol layout to `date,cell,block` and original sidebar ordering.

- Cell `5b00807d-74fd-4004-936a-8c35a2af446a` (2025-11-10 Cell1) exposes one
  SingleSpot trial and462 injected-noise trials. Unrecorded QC families are
  disabled. Noise paging reaches41–80 and returns1–40, with Previous disabled
  at the first page. Metadata show/hide and workbench return/refresh work.
- SingleSpot shows pre mean−56.1340175mV, stim mean−53.5861925mV, delta2.547825mV,
 250ms pre/stim/tail. Compare conditions shows one trial/one used; View trial
  retains correct trial; method panels clearly describe raw-signal means.
  Injected-noise epochs lacking timing show unavailable, not fabricated means.
- Measure block onsets renders13 observations, range−59.803 to−54.861mV;
  method flags/sensitivity windows and unavailable interpolant are explicit.
  Hide measurements/comparison work. Independently reproduced arithmetic is
  in the workflow-agent successful receipt, not inferred solely from this UI.
- Temperature0 is preserved as a recorded value. Resistance disclosure says no
  measured resistance; compensation0 is explicitly an amplifier setting.
  Analysis availability marks spike/RF adapter unvalidated and interpolant
  unavailable. Cell provenance exposes the actual source SHA and cell type.
- Amp1 injected-noise epoch `2b4a0570-b4a8-44f4-a5ef-262907b9ed43`: Show window
  start100/count200 renders samples100–299 at 0.01–0.0299s. Cursor150 displays
  −66.5125mV, Right151 displays−66.68125mV. Independent read-only h5py source
  access confirms both quantities exactly. ShiftRight pans to200–399; Home
  restores0–4999. Zoom in/out, next/previous windows, bounds, Reset and pointer
  drag-to-zoom work; full-rate/no-filtering labels remain visible.
- SingleSpot epoch `aa4f427e-6a20-4de8-9491-d6faa7ce0f00`: stream selector switches
  Amp1(mV) to Frame Monitor(V); cursor150 displays5.8875V, independently equal
  to source H5. Restored Amp1. No delayed-response fault was injected.
- Protocol `933b5a53-cca9-540c-b86a-6bbec5137140`: first epoch has Previous
  disabled. S/Tab advance to epoch 2; W/ShiftTab return to1. Tree and metadata
  splitters respond to arrow keys (270→280 and 320→330), restored afterward.
- Added Frequency cutoff using split-search+Enter. AltUp moved level4→3;
  Show move controls / Move later returned it to4. Browser reload and reopen
  retained all four levels. Remove grouping, Flat list and acquisition preset
  work; total membership remains1,649. Generated EpicTree command shows correct
  date/cell/group/block layout and Copy reports success. Restored date/cell/block.
- Split tree expands date→cell→block→ten epoch leaves; selecting epoch 2 displays
  that epoch. Collapse all and More→Hide epoch list→Show epoch list work.
- Sidebar Organize protocols, Pin/Unpin, Tuck away/Show, Move up/down, Done all
  announce correct positions. Restored current-injection protocol to Protocols
  position2. No scientific dataset or shared annotation mutations occurred.
- No blocking functional bug found in these executed controls. Pointer pan,
  pointer reorder, narrow viewport, clipboard-failure handling, and induced
  trace-error retry are explicitly unverified variants, not silently certified.
| 2026-09-28 / local pre-release | Q01–Q14 | Q-UI: workflow agent, isolated Chrome tab 2115893404, own native project | Browser exercised field search/category, typed string/numeric conditions, add/remove condition/group, All/None/NOT and empty Any, invalid-number blocking, preview counts (5 / 3 / 967 / 140 / 0), Cancel/Escape, project preset create/update/history/pin, real downloaded query JSON import, saved selection revision, direct SQLite export/download (5 epochs, independent integrity and candidate-scope check), new pinned protocol (5), narrowed update (3) with exact diff/show-hide and required removal acknowledgement, incompatible update disabled and mixed-protocol creation rejected, zero-result export disabled | Local screenshot `/tmp/rieke-query-browser-updated.png`; browser-created protocol `4d69097b-f47a-53b4-a8ce-91c9c2898b54`; query preset `60cab3d3-3c74-434c-afa8-eb528ffc6a44` | One intermittent shared-DB packet-sequence/ASCII failure surfaced during mixed-protocol options, reported for repair; retry recovered, not counted as resolved. Boolean/list/null UI variants, invalid query-file and second-project import remain unverified. |
| 2026-09-28 / local pre-release | Q02,Q04,Q10,Q12 | Q-UI follow-up | Recorded-null predicate matched 972, missing matched 0; array equality `[800,600]` matched 972; malformed JSON import showed explicit valid-query-file error; actual direct MATLAB export/download contained 5 matching epochs with `explorer_candidate` scope | Native Chrome file chooser plus downloaded JSON, SQLite and ZIP inspected independently | Catalog has no recorded Boolean fields; second-project query import not exercised. Concurrency fix retest pending. |

### R1 follow-up — masks and exact bulk targets

On parent browser project 55262, checked only epochs 2 and 3 and clicked Exclude 2
selected: independently read mask excluded count changed1→3. Actual file chooser
Import JSON mask restored the 590-decision downloaded baseline exactly, including
one excluded epoch. Tag selected epochs added `client-bulk` to exactly epochs 2
and 3; API inspection of the first 3 epochs confirmed first remained untagged;
cleared the selected targets afterward. Actual MATLAB `selection.ugm` from the
589-epoch export was picked, automatically matched and applied: receipt reports
589 UUIDs, all 590 protocol inclusion decisions remain identical and nonexported
excluded first epoch stays excluded. This supplies browser evidence for C02,
C05, C06 and T03; it does not turn malformed-file or cross-cell variants into
manual browser tests.

R1 review follow-up: Mark focused reviewed on included epoch 2 yielded approved=true
in the protocol API; Clear review returned it to unreviewed. Dataset-only tags
disclosure and `client-dataset` save yielded the exact protocol tag. Focused-only
removal completed and the API confirms an empty dataset-only tag list. Browser
JSON, SQLite and MATLAB downloads have the same exact 589-UUID membership; MAT
reads successfully, with independent identity verification from F2. New export
name/date changes were not covered by that earlier run; the final R1/F3 evidence
below now verifies them.

### W3 final recovery evidence — G1 closed

Actual file chooser upload added one epoch and one source (973 epochs, 2 sources);
duplicate job `ee1dc9eb-b749-4171-b149-f175472521bf` reports duplicate with staging
removed and unchanged catalog counts. Malformed ordinary H5 job
`893a0df6-acc0-4190-9528-db9850d14bc4` failed without partial registration.
Nonexistent path now visibly reports Request rejected with elapsed time frozen
at 0 seconds, after the error-message fix; screenshot
`rieke-import-rejected-fixed.png` is retained locally. For the controlled owned
upload, File missing, trace Retry failure and export rejection were all visible;
restored bytes have the original SHA and export count remains 6. Updated readiness
guidance and an explicit Refresh metadata recover 10 trace samples, recorded in
local `rieke-missing-receipt.json`. Mixed-protocol create UI after the SQL lock fix
shows 956 members split 590+366 with creation disabled and no server error.
The repair passed 190 frontend and 43 focused backend tests plus build. These
fixes were included in F3’s final candidate sync and subsequent full suites.

G2 completion: root confirmed dataset-only tag removal with API tags=[] and
review=false. Required main curation, masks and tagging interactions now have
browser evidence. O02 filters/Clear, E05 Escape and E07 reuse are now covered by the W3 follow-up
below; new export name/date browser proof is recorded in the final R1 follow-up below.

### W3 follow-up — overview filters and export reuse

Overview ON-midget filtering changed 3→2 cells; combining the Nov 13 date with that
type gives an explicit zero-cell state, Clear restores 3 cells, Nov 13 alone shows
one unknown-type cell with one epoch, and Clear restores the complete scope.
Candidate Review & export again opens a review dialog showing the current 6
versus original 5 members after source addition; Escape closes without exporting.
An old SingleSpot query is rejected for reuse with explicit original-preservation
guidance after the query changed. Workflow-selection Reference JSON reuse opens
the correct format and current 588 included versus old 589; Escape creates nothing.
The export list remains 6 records; all 6 download SHA values equal saved records, and
prior direct SQLite/MAT bytes equal the earlier downloaded artifacts. This covers
O02, E05's Escape path and E07, not a double-submit fault injection.

### F3 — version 0.1.1 final standalone repeat with download-name assertions

All tracked and new nonignored application source files were copied into the
separately installed candidate; managed runtime, project data and original H5
files were not copied from the development checkout. The importer SHA-256 before
and after this sync is identical:
`9845663fef7c3792dcac107627195fe1917f740159940ec68ec72f1385c14028`.
The previous eight-source independent import audit therefore applies to the
unchanged importer; export/readiness changes received fresh workflow testing.

The enhanced `packaging/verify_workflows.py` completed all 20 checkpoint groups
again in a new candidate-runtime project
`cdab231c-a51e-4b40-8996-780a409990c7`, using the original 972-epoch recording.
Each actual HTTP download was asserted to have exactly
`Client_validation_export_2026-09-28.json`, `.sqlite`, or `.zip` as its filename,
with no UUID suffix. The immutable recipe independently contains the chosen
name and `download_naming={version:1,date:2026-09-28}`. Existing exact 589-UUID
artifact, mask/tag/query, duplicate, propagation and restart checks all pass;
source SHA is unchanged and the Docker trap was never invoked.
Local receipt: `rieke-v011-named-workflows-receipt.json`; detailed evidence
directory: `rieke-workflows-ho2b9xgl`, including `download-headers.json`.
A preceding unmodified 20-checkpoint repeat also passed (`rieke-workflows-olv4nyry`).
This supplies final HTTP/artifact naming proof; root browser naming proof is
recorded below. G3’s final source-archive scan also passes, as recorded below.

### R1 final browser/software validation

On the parent IAB tab 4 / project 55262, the new export default is exactly
`Variable_Mean_Noise_current_injection_2026-09-28`. Save 589 and the actual browser
download produced `Variable_Mean_Noise_current_injection_2026-09-28.sqlite`,
without an appended UUID or spaces. Screenshot `rieke-export-name-date.png` is
retained locally. F3 independently checked custom naming across all three HTTP
formats; the browser result above proves the default-name user path.

Focused Include was confirmed true through the API, then exclusion restored.
Browser removal of epoch tag `clientcheck` and cell tag `clientcell` both passed
with API confirmation. A subsequent positive reimport dialog was closed by the
user: do not count it as completed. Earlier actual idempotent browser tag reimport
remains passing, and positive additive reimport is covered by F2's API workflow.

Root final suites pass: 522 Python tests, 193 frontend tests and the latest build.
The candidate runtime passed the complete 20-checkpoint workflow with the final
naming assertions. Scientific fixtures were removed from the new distribution's
tracked file set while local copies were retained. Historical Git objects are
a separate consideration; the final source archive scan below passes.
No unresolved main workflow or scientific integrity bug remains in the recorded
validation. Parent owns the final commit, archive regeneration/checksum and
publication decision. This ledger does not certify every unexercised UI variant
or unsupported runtime listed above.

### G3 closed — shareable source archive checked

Parent’s final source-archive check passed: 508 files, 1.445 MB ZIP, clean ZIP
integrity, no MAT/H5 recordings, databases, runtime or dependency directories,
executable install/start scripts preserved, and the latest naming module
byte-identical to the tested source. Local evidence is
`rieke-final-archive-check.json`. Parent will regenerate the archive after this
ledger update and final commit, then record the asset checksum externally.
No repository tree/archive hash is embedded here, avoiding a circular hash claim.
There are no remaining required release blockers in this ledger. Untested
variants and unsupported environments remain explicitly disclosed above.


## 0.1.2 root and path follow-up

The complete root workflow passed through the browser: select a separate
workspace with spaces and Unicode, create a named project folder, open its native
database, and import one original H5. All three services (chooser, API and native
MySQL) were then stopped and restarted. The project UUID, canonical folder,
browser origin, one-epoch catalog and original source checksum were unchanged.
Launching the installed application again **without** an explicit workspace flag
also selected the remembered root and original project.

Invalid nested roots return a visible error before creating files or changing
preferences. Root switching leaves each workspace's projects in place. HTTP
regressions cover relative import paths and upload-directory symlinks. Native
reproductions cover copied credentials, copied API records, moved populated
projects, and protocol/candidate export symlinks; all now fail closed. The full
20-checkpoint workflow passes with these guards, as do all 539 Python tests.
Frontend behavior is unchanged from the 193-test validated build.

Reproduce the root guards with `test_workspace_root_boundaries.py`,
`test_workspace_path_api.py`, `test_workspace_native_database.py`,
`test_workspace_project_servers.py`, and `test_workspace_export_paths.py`.
Local receipts: `rieke-path-browser-restart-receipt.json`,
`rieke-remembered-root-receipt.json`, `rieke-path-fixed-receipt.json`,
`rieke-export-path-fixed-receipt.json`, and `rieke-paths-final-workflows-receipt.json`.
The earlier eight-source audit remains applicable: the importer's hash is
unchanged. Automatic relocation of imported projects remains unsupported;
restore their original location rather than manually rebasing database/source
references. No user project or original recording was moved by these tests.
