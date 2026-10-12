# Linked SQLite and managed recordings

This opt-in internal-analysis format supplements full SQLite, MATLAB and JSON.
Scientific selection, acceptance, freshness and publication authority are unchanged.

## Linked export contract

The caller freezes its package under existing locks and checks, then
`prepare_linked_package` binds existing checksummed import metadata. Metadata must
be in that project's imports folder; H5 must belong to the managed library or a legacy project under the same
workspace. Downloads and disposable caches are not durable dependencies.

`validate_sqlite_package` shares the existing recipe, UUID membership, fingerprint,
source-pointer, hierarchy and decision checks between writers. The linked writer
also proves the referenced metadata reproduces the complete frozen details exactly.
The existing typed tree implementation freezes groups and membership at each level.
Acquisition groups and analysis groups remain distinct tables.

The database stores the recipe, small hierarchy/stream records, frozen decisions,
shared annotations, grouping and checksummed source locators. Heavy metadata is
read from existing import files. Table seals detect edits, not malicious resealing.

The lazy `linked-sqlite` materializer returns a staged ZIP path, not a publication
receipt. Only this new format skips duplicate `recordings.json` staging. Existing
formats and caller-owned validation/commit/retry/failure handling stay unchanged.
The ZIP contains SQLite, a standalone Python loader, README and requirements.
Python 3.11+ stdlib handles SQL/metadata; NumPy and h5py handle recorded samples.
No running Disco, DataJoint or MySQL is required. Loader SQL functions
`epoch_metadata(uuid)` and `epoch_parameters(uuid)` fetch checked metadata lazily.
Ordinary SQLite clients can query stored tables directly.

Metadata hashes and epoch fingerprints must match. H5 reads verify checksums,
UUID hierarchy, units/rate/layout and at most 20,000 full-rate samples per call.
Generated stimuli remain metadata, not synthesized waveforms. Changed or missing
inputs fail closed. Explicit file maps/project/workspace roots relocate identical
bytes without changing cohort identity. Keep a reader open to reuse verification.
Automatic annotation return is not supported by this reference format.

## Managed recording contract

New GUI and CLI imports with real project manifests retain H5 under
`<project-parent>/recordings/<sha256>/<original-filename>`. One library belongs to
that parent folder, not to a consuming project. `.disco-library.json` binds its
UUID; an existing nonempty unmarked directory is never adopted. Legacy callers
without project manifests retain their original project-contained copy behavior.
Parse-only runs do not claim retention; external originals are preserved.

The version-2 `.disco-recordings.json` indexes relative paths, library/project owner
identity and conservative project UUID/directory consumers. Version-1 project-owned
entries remain readable and reusable; new library ownership upgrades the index to
version 2 without rewriting older entries. Older app versions that only understand
version 1 must not import into a workspace after this upgrade. An advisory lock
serializes reuse, publication and acquisition deletion. Existing import manifests
bootstrap legacy lookup; both candidate and input bytes are verified. Filename
equality is insufficient. Changed bytes, wrong library identity and symlinks refuse
reuse. Copying uses an exclusive staging file, checksum verification and fsync,
then atomically publishes its checksum directory before recording references. A
published copy survives registry failure and is verified/reused on retry. Unpublished
staging from a killed process can remain; there is no automatic garbage collection.

Caller-owned upload staging is removed after retention; watched inbox staging is
removed only after confirmed import and only if legacy dependency checks allow it.
External originals are never automatically removed. A successful import receipt
(or a duplicate with freshly verified managed bytes) can offer deletion of the
original **outside Disco**. Managed-source inputs, uncertain completion, missing or
changed copies and reconciliation-required jobs do not offer that instruction.
Historical receipts describe the verified import event, not a live backup guarantee.

References are conservative: failed imports and detached projects may keep them.
Deleting a data store or project never deletes central library bytes. Legacy
project-owned deletion retains its dependency fences and recovery ordering. This
change does not migrate existing references or add library garbage collection.
Separate scientific catalogs and identity checks remain unchanged.

New import manifests also store the library UUID and relative recording location.
Project relocation resolves the new adjacent library only on matching identity;
existing relocation then checks full recording/metadata hashes before updating
current SQL/local locators. Portable transfer materializes referenced H5s inside
the destination and clears the library locator on restore. Historical provenance
and exported recipes are not rewritten. Arbitrary manual H5 renames/deletions
cannot be intercepted; use the whole master folder or a prepared portable copy.

## Validation

Standalone-loader SQLite/H5 tests, HTTP publication/download tests, shared-recording
retention/deletion tests and frontend choices use owned fixtures. Existing full
exports, import and recovery tests remain regression detectors. Size measurements
must identify the fixture; these tests do not qualify native SQL durability,
installed-app behavior or release promotion. The application profile explicitly
stages the loader, linked writer and recording registry.
