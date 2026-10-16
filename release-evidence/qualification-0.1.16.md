# Unpublished 0.1.16 candidate

The immutable `desktop-test-v0.1.16` tag identifies
`f8488b95157be906e5bad63272a1d5a131805c47`. It was not published or installed into
the user's app. Do not move the tag or replace its candidate bytes.

The exact-source [performance run](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/38842303527)
failed the macOS trace comparison. Earlier passing comparisons do not supersede
that failure. Follow-up diagnostics observed delayed animation callbacks on both
unchanged baseline and candidate sources. Browser-mode switching did not establish
a fix. A paired diagnostic prepared both builds before alternating three samples
per source in one browser; its passing result is diagnostic, not release evidence.
The corrected protocol requires fresh ordinary qualification with all existing
correctness checks and median/maximum limits.

The [desktop candidate](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/38842280058)
built successfully and passed database and UI checks, but failed smoke, packaging
and updater verification. Test corrections address:

- Clean-shutdown smoke began while scientific project activation was still a
  pending write. It now waits for current project data and a fresh interactive
  overview; process exit and registry removal remain required.
- The disposable startup-fault copy changed resources without renewing its macOS
  seal. It now has a clone-only ad-hoc seal and releases the failure after the
  observer attaches, before application imports or scientific service startup.
- Rollback verification searched the download cache for the failed candidate,
  while the helper correctly retains it beside the installation for same-volume
  renames. Ownership, containment, exact bundle bytes and profile checks remain.

Subsequent smoke attempts also recorded unavailable public update-feed checks.
These failures remain failures; observing transport status does not waive the
required successful connectivity check. Local diagnostic passes are not exact
hosted-artifact qualification. The next release uses a new version and source.
