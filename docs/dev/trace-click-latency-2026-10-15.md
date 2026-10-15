# Workbench click-to-trace investigation

The reported delay reproduces in the installed Disco 0.1.14, clean source
`82d541e8300eb1b6930ff7f1bd35f974a6ca343e`, with Live metadata **off**.
GitHub main was independently checked at
`ea9b5ac40bcd39fb217a0e30c675fa2c1ea938b6`; that infrastructure branch does not
contain the complete installed application, so this fix uses the installed source.

## Actual installed-app observation

The user explicitly authorized timing their open scientific project rather than
restricting this investigation to disposable fixtures. Only epoch browsing was
performed. The app was closed normally and relaunched with a temporary loopback
diagnostic listener. A renderer observer recorded the native click event, the
product's existing fetch/JSON completion, complete canvas draw and two subsequent
animation frames. No synthetic responses or altered product code were used for
these baseline samples. This measures renderer readiness, not compositor scanout.

The open frozen Workbench contained 167 pending epochs across three cells. Three
successive 300,000-sample traces at 10 kHz produced:

| Click | First trace request | Last trace response | Complete draw | Frame observation |
| --- | ---: | ---: | ---: | ---: |
| Epoch 10 | 12.8 ms | 1680.2 ms | 1707.4 ms | 1711.6 ms |
| Epoch 11 | 9.0 ms | 1587.7 ms | 1612.5 ms | 1616.7 ms |
| Epoch 12 | 6.7 ms | 1682.5 ms | 1703.5 ms | 1707.7 ms |

Median click-to-frame observation was **1707.7 ms**. Each click issued fifteen
sequential 20,000-sample requests, typically taking 95–140 ms each. Rendering
after the final response accounted for only 25–31 ms. This is the reported
Live-off path; optional metadata is not its cause.

## Cause and correction

Whole-epoch presentation split the requested waveform into small requests and
waited for all chunks before publishing. In frozen Workbench each request repeats
opening/closing scope, recipe, annotation and registration checks. The backend
already accepts exact 100,000-sample windows. The first candidate used that
existing limit, reducing a 300,000-sample read from fifteen requests to three.
In the same installed app/backend, its native times were 590.8, 576.8 and
526.3 ms (median 576.8 ms). This was an improvement but still exceeded the
user's stated acceptable delay. It is retained as intermediate evidence.

The final source adds an opt-in foreground batch of up to five existing
100,000-sample windows. One opening/closing read scope and one immutable source
plan cover all windows, with final publication/source revalidation. A 300,000-
sample trace therefore needs one HTTP request. Custom trace overrides cannot
be bypassed through batch admission; imported snapshot routes do not use it.
Partial Sample windows and imported snapshot routes retain their 20,000-sample
limits. Identity, source hash, rate, units, contiguous interval, cancellation and
complete-only publication checks remain intact. No samples are dropped or
resampled, and complete arrays are not admitted to the shared cache.

Workbench now encodes its detached trace response after closing its authority
guards, matching the global trace route. This removes JSON encoding from the
shared database lock without skipping the closing scope check.

A separate Live-on waterfall was also found: optional metadata and trace warming
blocked the admitted row's trace. Metadata now loads independently, neighboring
prefetch reads traces without unnecessary full metadata, and required scoped
descriptors still gate access. Navigation and annotation-refresh regression tests
cover the corresponding ownership changes.

Owned-fixture diagnostic evidence is deliberately separate: 300,000 exact samples
through fifteen requests took median 364.45 ms versus 138.39 ms through three;
cumulative context work fell from 187.49 to 36.55 ms. These use SQL doubles and
are not the installed-project numbers above.

## Regression coverage

The previous browser workflow exercised a 10,000-sample main-view trace, fitting
within one request. It did not cover a long frozen Workbench trace. The workflow
now preserves those thirteen actions and adds `trace.inspect/frozen-workbench-300k`.
Its independent oracle checks the scoped URL and revision, source hash, every
sample, exact contiguous coverage, rate/units, and draw after the final response.
The fixture is version 3 and registry suite is 1.0.6; historical receipts cannot
silently compare with this expanded suite. Existing regression thresholds remain.

## Package size

The public 0.1.14 ZIP is 598,463,204 bytes versus 607,572,083 for 0.1.13, a 1.50%
reduction. The uncompressed runtime reduction is almost entirely 1,040 bytecode
cache files (26,198,318 bytes); every corresponding Python source remains. All
875 native library paths and the dependency inventory are retained. Five hashed
frontend assets were replaced by their new-build equivalents. All 40,147 installed
manifest resources passed presence and SHA256 verification. No functional package
repair is indicated. Bytecode cache absence can affect cold imports, but does not
explain the repeated warm-click delay measured here.

The 0.1.13 release additionally offered a separate DMG; 0.1.14 offers the ZIP.
Public assets: [0.1.13](https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.1.13)
and [0.1.14](https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.1.14).

## Evidence limits

Focused source tests and a fourteen-action small browser smoke pass. Their exact
final-source regression receipts and any native candidate comparison are recorded
separately; neither source tests nor fixture timings establish an installed fix.
No release or installed bundle is changed by this investigation's source patch.
