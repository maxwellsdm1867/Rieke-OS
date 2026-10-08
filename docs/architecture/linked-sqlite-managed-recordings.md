# Linked SQLite and managed recordings

This opt-in internal-analysis format supplements full SQLite, MATLAB and JSON.
Scientific selection, acceptance, freshness and publication authority are unchanged.

## Linked export contract

The caller freezes its package under existing locks and checks, then
`prepare_linked_package` binds existing checksummed import metadata. Metadata must
be in that project's imports folder; H5 must belong to a project under the same
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

Committed GUI and CLI imports retain H5 in a project's raw-uploads folder.
Parse-only runs do not claim retention; external originals are preserved.
Sibling projects reuse identical SHA-256 files. A workspace-local
`.disco-recordings.json` stores relative owner paths, owner UUIDs and consumers.
An advisory lock serializes reuse and acquisition deletion. Existing import
manifests bootstrap lookup; both candidate and input bytes are verified. Filename
equality is insufficient. Caller-owned redundant upload staging can be removed;
unowned originals cannot. Separate scientific catalogs and identity checks remain.

References are conservative: failed imports and detached projects may keep them.
There is no automatic reference garbage collection. Deleting a data store detaches
its catalog but retains recordings used by another project. Recovery ordering is
preserved. Manual filesystem deletion/movement cannot be intercepted. Keep shared
owners available; existing project transfer copies external referenced H5 into the
portable destination. Installing this feature does not migrate existing sources.

## Validation

Standalone-loader SQLite/H5 tests, HTTP publication/download tests, shared-recording
retention/deletion tests and frontend choices use owned fixtures. Existing full
exports, import and recovery tests remain regression detectors. Size measurements
must identify the fixture; these tests do not qualify native SQL durability,
installed-app behavior or release promotion. The application profile explicitly
stages the loader, linked writer and recording registry.
