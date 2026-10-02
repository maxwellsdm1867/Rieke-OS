# Priority dictionary A/B

`PrioritySidecar` provides the same public methods as the earlier full-field `TypedBoundedSidecar`: page, preview, membership/iter_membership, groups, detail. The page, exact count, cursor and requested facets are unchanged. All 140 native field definitions remain eligible.

The main database retains a selected typed dictionary. A query on another field materializes that field's distinct native dictionary into a TEMP table with the same typed/equality keys and indexes. Missing/exists avoid dictionary extraction, and proven direct string identity equality goes straight to shared indexed core. Default UUID equality therefore never reads/decodes the one-million UUID dictionary. Dictionary materialization is recorded in `materializations` and included in the first request's measured latency. Returned raw values and full native details retain original types and JSON.

Both native EAV data and the previously proved chronology/core indexes are attached read-only. No schema writes occur in either input. This experiment isolates field-dictionary prioritization; it does not measure fresh core extraction/startup or claim that the full source metadata has disappeared. Build receipts include incremental projection bytes/time, shared core storage bytes, and the full typed sidecar's bytes. Cold dictionaries live only for an instance and are rebuilt after reopening.

Two fair comparisons are needed: (1) full and priority dictionaries with identical requested facet payloads, and (2) independently labeled request only visible facets versus requesting every field. The second changes the payload and must not be presented as a storage/index-only improvement.

`smoke.py` independently checks 33 predicate cases against native field values and compares exact preview output, pagination, scopes, groups and details. It also verifies that a fresh UUID equality lookup triggers no materialization. The fixture contains two complete copies of the actual 2,781-record corpus.

The full EAV epoch/value link table is unchanged and remains the likely cost for broad scientific filters and facet aggregates. Fewer dictionary entries may reduce disk cost without improving these scans. If measured gains are small, retain the simpler all-field implementation.
