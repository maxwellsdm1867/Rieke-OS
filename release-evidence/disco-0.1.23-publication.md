# Disco 0.1.23 publication

The unsigned Apple silicon testing release is published at
https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.1.23.
The immutable application source is `7e9572406acf3e5dec66fe35a6bf88fc0091da32`.

Exact-source checks passed on their first attempt:

- Full regression: https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/39698195913
- Million-epoch browser/backend and macOS trace regression: https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/39698198695
- Candidate build and packaged smoke/UI/database checks: https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/39698176413
- Publication and archive verification: https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/39701366638

Published ZIP SHA-256: `0b68f7cb5e4e28712c4ad81498ec57fd2bdd2b6423208014f3eb0aa2acb805ba`.
Runtime manifest SHA-256: `91396c0908501335d8716a9c6d856bec893b8f8795d1b85063d36933e4823871`.

The native App Updates workflow downloaded, verified, installed, and reopened 0.1.23 at
`~/Applications/Disco.app`. The runtime reports the exact source above and
`source_dirty: false`; the existing project reopened with its protocol and counts intact.
Native review-cycle checks and compact local receipts are retained in the release
checkout's `local-verification` directory. Local frontend regression passed 1,552 tests.

A separate public-package qualification run (39701832269) verified archive identity,
runtime resources, and the native database, then stopped before the upgrade test
because its workflow symlinked the candidate output into the qualification checkout.
The test path guard correctly rejected that symlink. A workflow-only follow-up copies
the already verified output physically; application bytes, the tag, and path guards
are unchanged. The corrected public-download audit is run 39703029939:
https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/39703029939.
It cleared physical staging and reached native upgrade/recovery verification.
This additional post-publication audit does not block access to the release.
Run 39702495662 stopped at checkout because an abbreviated qualification SHA
was supplied; run 39703029939 uses the full reviewed SHA.

Earlier first-candidate evidence remains attributed to `4343509` and does not
qualify this final release. No performance gates were relaxed.

At the user's request, GitHub marks 0.1.23 as its Latest regular release. The title
remains **Disco 0.1.23 testing**; unsigned, unnotarized, and non-production warnings
remain. This changes GitHub listing metadata, not the immutable app or its
`unsigned-testing` update descriptor. GitHub's Latest API was verified as 0.1.23.

Cleanup retained the installed 0.1.23 app, source checkouts, compact verification
receipts, and recovery evidence. Seven owned disposable artifacts were removed
(two diagnostic downloads, the superseded updater app backup, installer download,
empty staging directory, and two generated frontend output directories). The final
cleanup operations observed approximately 2.62 GB more free space; this is a
system-wide measurement, not a guaranteed APFS per-folder saving.
