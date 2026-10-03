# macOS native compatibility evidence

The packaging target is Apple silicon (`arm64`) on macOS 14.0 and later. Intel
support is not promised; an incidental x86_64 slice in a universal library does
not make the full application an Intel build. The available runtime test host is
macOS 27.0.1 arm64. A successful run there does not establish macOS 14 behavior or
all intermediate OS versions.

| OS / architecture | Baseline c72b190 packaged runtime | Repaired runtime | Support statement |
| --- | --- | --- | --- |
| macOS 14.x arm64 | Not run; host unavailable | Pending; host unavailable | Target, not a verified runtime guarantee |
| macOS 15.x arm64 | Not run; host unavailable | Pending; host unavailable | Target, not a verified runtime guarantee |
| macOS 26.x arm64 | Not run; host unavailable | Pending; host unavailable | Target, not a verified runtime guarantee |
| macOS 27.0.1 arm64 | Failed: packaged SciPy native wheel import | 146132c: startup, project restart/quit, injected backend failure/quit, scientific workflows passed | Available runtime test host |
| All listed OS versions, Intel | No build | No build | Unsupported |

The baseline failure concerns the original SciPy wheel's native TLS load behavior.
A successful isolated replacement-wheel import on the current host is narrower
evidence than a repaired full application run. Keep those results separate.

Run the read-only audit against the **assembled application**, after runtime
repair and final packaging, and retain its JSON outside the bundle:

```sh
python3 tools/desktop_native_compatibility.py \
  --bundle 'desktop/dist/mac-arm64/Rieke OS.app' \
  --output /owned/evidence/native-compatibility.json
```

The audit walks the entire supplied bundle, including Electron frameworks and
helpers, Python, MySQL, extensions and scientific libraries. It reads Mach-O
headers and load commands directly without importing packages or executing
bundled programs. Each native file has its relative path, byte size, SHA-256,
slice architectures, actual deployment-version load command, declared minimum
macOS version, SDK declaration, library dependencies and rpaths in the report.
Wheel tags, file names, build-host versions and dependency pins are not substitutes
for version metadata in the installed native bytes. SDK versions are not minimum
OS versions.

Discovery uses file magic regardless of extension. This includes extensionless
executables and `.so`, `.dylib` and `.node` files when they contain Mach-O bytes.
Archives, compressed files, ASAR contents and embedded binary payloads are not
unpacked or scanned internally. Native libraries must be present as regular
unpacked files in the final application for this evidence to cover them; retain
the packaging manifest and native-unpacking configuration alongside the report.

A passing static report requires a regular arm64 slice in every discovered Mach-O
file with a known macOS minimum no later than 14.0. Unknown or malformed native
headers, missing deployment commands, wrong platforms, missing arm64, excessive
resource usage and paths escaping the bundle are blockers. Intel slices remain
visible as evidence; their minimum versions do not qualify or disqualify the
arm64 target. Internal symlinks are recorded without traversing their aliases.
Absolute symlinks are rejected because they break relocation. System library
paths under `/usr/lib/` and `/System/Library/` are allowed.

The parser has fixed bounds for traversal, native bytes hashed, slices, load
commands and load-command bytes, plus a wall-clock deadline checked between
operations. It uses no subprocesses. These bounds fail closed; they never turn a
partial scan into a passing report. Run only against a quiescent owned artifact.
The report binds native file bytes, not the entire bundle or a source commit;
retain it with the existing full resource manifest, source/build receipts and
artifact hashes. Do not transplant a report to rebuilt bytes.

This is a static deployment and path-containment check, not proof of complete
dynamic-loader resolution, symbol availability, signing, notarization, installation
or scientific correctness. Inherited `@rpath` resolution and executable-relative
paths still need relocated application tests. A release needs startup/shutdown,
Python scientific imports, MySQL operations and scientific workflows on macOS 14
and the other OS versions it claims. No macOS 14 runtime test has been established
by this audit. Preserve previous failed artifacts and diagnostics separately.

## Retained local repair qualification

The local evidence directory `benchmarks/results/packaging-146132c/` binds the
assembled package to clean source `146132c4ec8072ae1eafc0b58deb6df9b74d02cb`.
It records six packaged UI smoke checks, failed-backend recovery and ordinary
quit, 87 scientific unit tests using the packaged interpreter, and real native
MySQL import/export/restart/portable-transfer checks on a disposable 129-epoch
synthetic source. The independent analytic oracle checks exact trace values.
Original H5 and packaged resource inventories remained unchanged; owned services
exited. This is correctness evidence, not an ingestion-speed benchmark.

The whole-bundle audit corrected in `21d3356` finds 813 Mach-O files with no known
static blockers. The original audit's path-context failures are retained beside
the corrected report. Bare loader paths resolve to the current image;
executable-relative paths use an MH_EXECUTE image's own directory. For libraries,
containment is checked against every inventoried same-architecture executable,
while actual loader selection and dynamic resolution remain unverified. The 284
regular app.asar entries contain no Mach-O magic; nested compressed payloads are
outside that check. Retain `native-compatibility-corrected.json`, the ASAR inventory,
full runtime manifest and source receipt together.

The preserved c72b190 package's actual backend traceback confirms the same
PROPACK Mach-O zero-fill-offset error reproduced with the pristine official
macOS 14 wheel. The repaired macOS 12 wheel keeps SciPy 1.15.0 and NumPy 2.2.6;
post-relocation imports pass. The prior isolated diagnostic quit hang did not
reproduce in the repaired package's failure suite; no shutdown policy was changed.
These results do not qualify later combined commits: run exact-candidate core,
relevant regression, native navigation and packaged startup checks after integration.
