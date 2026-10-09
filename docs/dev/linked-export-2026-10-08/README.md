# Linked export and shared recordings acceptance

Implemented in the isolated export-save-location source checkout. The installed
Disco app and user projects were not changed. Live GitHub main was verified as
`34c9c3a0644707383905075421b457513efb336a` on 2026-10-08.

## Evidence

- 24 new standalone SQLite/H5, real HTTP publication and managed-reference tests passed.
- Final regression run: 120 tests, 118 passed, two skipped (opt-in native deletion and unavailable source parser packaging fixture).
- Native deletion was then run separately with the installed read-only Python/parser/MySQL runtime against an owned disposable project: one passed. Initial missing-parser/config/IPython setup failures are retained in the external evidence directory; no installed files were edited.
- Full frontend suite: 919 passed. Production frontend build passed.
- Architecture metadata/Python/JavaScript guard passed. Reviewed owner hashes changed for the explicitly modified implementations; reviewed AST selectors and guard logic did not change.
- Real rendered UI against an owned SQL-double/H5 fixture: open protocol, Export, choose Linked SQLite, Save & export; success and ZIP download displayed. See [screenshot](ui-linked-export.png). This is not installed-app qualification.
- [Size result](size-results.json): every exported epoch's metadata matched full SQLite exactly; first/last real H5 trace windows and frozen top-level membership matched. Repeated linked exports retained one original metadata file and one H5. The ZIP includes the standalone loader and examples.

Raw logs, measurement scripts and fixtures are retained at
`/Users/maxwellsdm/Documents/Codex/disco-linked-acceptance-2026-10-08`.
Final clean core/matched-million receipts are collected after this source commit;
retain their exact source identity separately. No release promotion or package
installation follows from these source checks.

## Limits

Linked exports require unchanged accessible managed metadata and H5. They do not
replace the full export or project transfer for sharing. Existing imports are not
automatically migrated. Cross-project reuse is limited to sibling managed projects;
external originals are retained and failed/detached consumer references are
conservative, with no automatic garbage collection. Manual file deletion cannot
be intercepted. Annotation return is unsupported for linked exports.
