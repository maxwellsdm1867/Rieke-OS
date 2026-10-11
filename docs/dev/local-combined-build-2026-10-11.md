# Combined local Disco build — October 11, 2026

The user requested one local build containing the current icon, selection,
alignment and protocol changes, tracked in Git. The owning checkout is
`/Users/maxwellsdm/.codex/worktrees/full-epoch-qc/Rieke-OS`, branch
`codex/next-version-integration`. The historical primary checkout is not the build
source. GitHub main was verified as `035e295` before integration.

## Integrated source

- `ba16611`: UI-wide fill-only selection, theme contrast, retinal cell icons,
  aligned overview/data-store counts and compact trace controls, including the
  earlier combined updater/navigation work.
- `c4034a1`, merged with ancestry retained in `3f392ef`: collapsible protocol
  sidebar sections; UUID-preserving rename; explicitly reviewed multi-acquisition
  pinned datasets; exact all-member compatibility for updates/exports.

The mixed-protocol workflow never silently trims a selection to fit a destination.
Recorded cell and protocol identity, frozen membership and existing provenance
remain authoritative. Native project data is not a build input.

## Packaging integration correction

The protocol change modifies `validate_protocol_definition` and
`evaluate_protocol_file` in `recording_workspace.py`. The package's byte-pinned
external-loader boundary had not been rebound by that feature commit. Inspection
of the full diff and AST comparison confirms those are the only changed top-level
functions; `load_parser` is unchanged. The source hash is explicitly rebound to
`7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139`.
The allowed loader call list, file allowlist and refusal rules are unchanged.

## Local artifact and evidence

The local candidate retains version 0.1.10 and is distinguished by its exact Git
source commit and artifact digest. This is not a public release or signed/notarized
promotion. The user authorized replacement of the installed local app. The verified bundle
was installed on 2026-10-11; the preceding app bundle is retained for rollback.
Scientific projects and recordings were not build inputs or replacement targets.

The existing pinned runtime is staged into an independent APFS copy, then the
normal runtime refresh/build, manifests, native imports and package integrity
checks bind it to the current source. Build/test receipts remain under
`benchmarks/results/local-combined-3f392ef/`; final artifact metadata is saved
separately after verification. Historical feature receipts remain attributed to
their original commits, including prior timing-review flags.

## Final source, validation and installation

The application is built from clean source `942015be17dfbdc12fe88acf44942774f8f94cad`.
This documentation follows that source and does not change the packaged bytes.

- Artifact directory: `/Users/maxwellsdm/Documents/Codex/Disco-local-2026-10-11-942015b/`.
- Installed app: `/Users/maxwellsdm/Applications/Disco.app`, local 0.1.10.
- Whole-bundle SHA256: `e093173f7f26dd5ed0c3c813f726f9b6cd165856140fc4e74a17c1132eb197a4`.
- Runtime manifest SHA256: `cb3bb7e139222745f74b9e56e109265d6d90245bbe72c8a7cfb156288c9d7e93`.
- ASAR SHA256: `f4b6ab7680b4c867ff8402b2a7de20546f1c94f39abccb2b9a45071d22085cf4`.
- Rollback app: `/Users/maxwellsdm/Applications/.Rieke OS.previous.app`, source
  `31182a40c22da05f904dda6979ac6bcf0d4996b0`. The older rollback bundle was moved to
  `preexisting-rollback.app` within the artifact directory before installation.

The artifact directory contains `build-receipt.json`, `prior-app-identity.json`,
`install-receipt.json`, and `validation-summary.json`. The normal whole-bundle
installer verified the source and staged copy, installed-manifest identity,
compatible formats, process absence, signature policy and final activation. Quit
used the ordinary application action; the backend registry cleared before install.

Validation: 1,046 frontend checks passed; 70 scoped backend checks passed and the
12 suggestion tests passed after correcting their invocation import path; 325
desktop checks passed with one skipped. Architecture and exact-source core gate
passed. Six packaged native smoke checks passed in an isolated profile, including
project creation, orderly exit and automatic project reopening. A static audit of
813 Mach-O binaries found no known blockers; it does not qualify macOS 14 runtime
behavior. Initial failed invocations and successful retries are retained.

All three matched million-row runs passed exact-result/refusal checks. Against the
pinned `34ce2e0` baseline, the initial cell-opening median triggered review
(1,167.88 → 1,545.56 ms); it cleared on repeat (988.18 → 989.47 ms). The repeat's
peak typed-worker RSS was 2,973,679,616 bytes, narrowly above its 2,947,547,136-byte
threshold. The initial memory comparison passed. The matched immediately previous
`ba16611` comparison passed every threshold, including RSS (2,775,597,056 →
2,291,482,624 bytes). These varying results do not establish a new regression or
clear the pinned review; the overall pinned comparison remains **review required**.
This is a local testing installation, not a green performance or release claim.

Raw results are retained under `benchmarks/results/local-combined-3f392ef/` and
`benchmarks/results/local-combined-942015b-{pinned,pinned-repeat,previous}/`.
No public release assets or GitHub branches were updated by this installation.

## Installed-profile startup limitation

Whole-bundle replacement succeeded, but the installed-profile UI did **not** reach
the project chooser. Its authenticated root health reported ready and the exact
942015b identity, with zero project services; the first chooser document stalled.
A process sample found one request thread blocked in `sorted` → `os.listdir` →
`__opendir2` → `open`, consistent with project-directory enumeration. The normal
Quit deadline retained the root ownership record with `drafts_saved: true` and
`Accepted operations remain active`; a normal restart reached recovery after
cleanup timed out. No backend was forcibly terminated, no ownership record was
removed, and no scientific project data was altered to clear this condition.

System Settings displayed Disco's Documents permission enabled. A pending macOS
folder-access dialog is a hypothesis, not a verified diagnosis; the computer-use
provider refuses access to UserNotificationCenter. The user was asked to check
for a system dialog. The process sample is retained in the artifact directory.
The new installed bundle and both earlier app bundles are retained. Installation
success does not establish installed-profile readiness; that check remains open.
