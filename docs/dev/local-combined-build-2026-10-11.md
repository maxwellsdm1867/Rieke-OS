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
promotion. A separate app bundle is built; installation requires the user's
separate choice in this chat. Existing app and scientific projects are preserved.

The existing pinned runtime is staged into an independent APFS copy, then the
normal runtime refresh/build, manifests, native imports and package integrity
checks bind it to the current source. Build/test receipts remain under
`benchmarks/results/local-combined-3f392ef/`; final artifact metadata is saved
separately after verification. Historical feature receipts remain attributed to
their original commits, including prior timing-review flags.
