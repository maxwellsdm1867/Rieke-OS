# Current experiment: one headed, foreground A/A pair

This isolated branch is diagnostic infrastructure. Never merge its replacement
`everyday-million.yml` into main or the release branch. Application source remains
clean `61881e87e2fe07f1d317ec92e42827243cfec9fa` in a separate worktree; the workflow
checkout supplies only the diagnostic harness. Nothing is published or qualified.

The workflow has one macos-15 job, a 15-minute wall limit, manual dispatch only,
and no Linux job. It executes exactly one same-source A/A pair: B0,C0,C1,B1,B2,C2,
including each role's first trace. Two independent browsers and three fresh page
contexts per role remain unchanged. No source comparison, repeated pair, warmup,
sleep, discarded sample or automatic retry is present.

## Changed environment, unchanged observation

The browser uses `headless:false`. Pinned Playwright chooses its full Chromium
binary rather than headless shell. Receipts explicitly record
`playwright-chromium-headed`, `headless:false`, browser version, actual executable
path/SHA256 and process arguments. No new Chromium flags or executable override
are used. The existing viewport and DPR remain fixed.

Before setup and trace click intent, `page.bringToFront()` activates the tab. A
five-second total admission deadline covers activation, bounded DOM focus/visibility
checking and a read-only OS foreground query. No action clock has started. The
original `armAction` then owns dispatch and all frame observations exactly as before.
After observation, another read-only check verifies the same OS owner; it never
activates a window after intent. No frames are requested or driven by the focus
helper. Failure to acquire/retain the condition fails the sample, never retries it.

Playwright emulates DOM focus, so `document.hasFocus()` alone is insufficient.
`frontmost-app.swift` reads `NSWorkspace.shared.frontmostApplication` and reports
PID/isActive using AppKit. It uses no NSApplication event loop, activation,
Accessibility, System Events, shell UI automation or permissions workaround.
The helper is compiled once during CI setup; its source/executable hashes are saved.
The foreground PID must exactly match the browser owner PID before and after each
action, with visible and DOM-focused page state. Existing bounded passive frame
records must also retain visibility/DOM focus throughout. OS ownership is bracketed,
not continuously polled during the timed interval; that limitation is explicit.

The original page-owned click/RAF, geometry, source, request-count and exact cursor
oracles, Python receipt validator and comparator threshold function are byte-identical
to618. The existing ordinary qualification comparator rejects the headed distribution.
The diagnostic independently checks the fixed pair's source/schedule/PID bindings,
full scientific receipt validation and foreground evidence, then computes symmetric
A/A results with the unchanged six metrics/thresholds. Either direction failing is
`environment_admission: invalid` and a nonzero job exit, not a green qualification.
Even a passing A/A result is only evidence for reviewing a headed qualification
condition with strict controls; it cannot waive the original headless CI failures.

Evidence includes every sample, passive frame history, foreground checks, process
arguments, immutable source/harness identities and failure captures. Artifact names
are diagnostic-only. Existing owner cleanup handles failures/signals; missing or
incomplete cleanup/evidence cannot pass. A hard runner termination may prevent
upload and remains missing evidence.

## Validation and history

178 lightweight Node logger/scheduler/oracle/focus checks and18 existing Python
receipt/refusal/lifetime checks passed. Swift source parsed; CI performs its actual
AppKit compile. Combined YAML, shell and embedded Python syntax passed, including
execution of the real dependency loop under macOS Bash3 with mocks. No browser,
server, GUI helper or benchmark was launched locally for this implementation.

Earlier commits832dab4/299fe17 contain the completed headless frame and Linux GC
attribution diagnostics. Original combined run39537973091's macOS setup failed
before sampling due to Bash3 empty-array expansion under `set -u`; its single
Linux profile succeeded. A separately authorized macOS-only setup repair ran the
original two headless pairs in39538289672. Both failed qualification runs and all
those diagnostic results remain retained. This headed experiment changes the
environment; it does not repeat Linux or either headless pair.
