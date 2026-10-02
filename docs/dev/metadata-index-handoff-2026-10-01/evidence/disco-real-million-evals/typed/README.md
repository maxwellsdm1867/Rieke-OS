# Previous typed SQLite approach, million-row replay

This is the previous `typed_real.py` experiment with typed core columns, native field-value dictionaries, exact recursive equality, chronological pages, UUID lookup, and parent/protocol indexes. It adds no dependency.

The native source DB is attached immutable/read-only. Original epochs, compressed details, 140 field definitions, exact JSON values, membership postings, source records and lossless ancestor objects stay in that single physical source. TEMP views route the previous API and production detail decoder to those unchanged tables. The auxiliary sidecar is a packaging difference from the 2,781-row clone; its bytes are the additional model cost. Source generation time and source size are separate from typed model build.

Build streams 2,000-row batches; chronology sorts only typed short columns, then assigns ranks. It does not decode epoch detail or materialize all epoch DTOs. Indexes are built after insertion. Both SQLite page caches have 32 MiB bounds and sort temporary files use disk. The command defaults to 300 seconds, 1 GiB peak process RSS and 4 GiB free-disk reserve. Budget interruption yields a failed receipt and retains the partial isolated sidecar for inspection.

The previous validator scanned dictionaries per query. This adaptation records actual JSON representatives covering every observed value kind and array element kind while building. Production `workspace_predicates.validate()` receives those exact type representatives; its acceptance and error behavior is preserved without repeatedly decoding a million distinct UUIDs. All nine core shortcuts are enabled only after an SQL proof of present non-null exact string equality against original field values across every row.

`build_sidecar.py --source BASE --target SIDECAR --receipt JSON` reports extraction, chronology, dictionaries, indexes, core proof, analyze and integrity/count timings separately. It checks source file identity/size/mtime. Full SHA256 preservation is a separate parent-owned phase so source-hashing I/O is not conflated with model compute.

`TypedRealSidecar(sidecar_path, source_path)` retains the previous preview/page/groups/detail/membership API. `iter_membership()` provides a bounded-memory oracle iterator; `membership()` still explicitly returns the previous full list API. Details use the existing production `Decoder`, referencing original source `metadata_objects` through the TEMP view and checking source revision/ancestor UUID ownership unchanged.

`smoke_sidecar.py` is only for small fixtures: it materializes ground truth for independent predicates, chronological pages, all groups and exact full detail comparison. It also checks predicate validation outcomes over all 140 fields including expected rejection of over-large literals. Do not run its Python ground-truth materialization on the million fixture.
