# Shared authority and trace owners retained in place

[StateGenerationAuthority](../../workspace_state_generation.py) remains a shared
native authority for both reads and transaction-locked writes. It is not owned by
metadata's disposable assets. Its schema/trigger/connection incarnation proof,
response_contract scope and assert_current_locked transaction checks remain exact.
Read witnesses cannot cross threads, sockets, connections or autocommit response
lifetimes; failed authority checks break continuity even if counters later match.
Read paths reuse the last complete attestation only while (connection epoch, global
DDL command counters, InnoDB table ids) are unchanged; any change, reconnect or
failure runs the complete attestation again, and transaction/mutation checks always
run it. Every GET/HEAD response holds one lazily opened response contract (through
the workspace lock); responses that read no native token never attest.
Keeping the named file avoids a misleading metadata-only authority or a one-file
folder. The existing [state generation tests](../../tests/test_workspace_state_generation.py)
remain central/native and are not executed by the metadata standard-library lane.

[ProtocolStateReader](../../workspace_protocol_state.py) stays at its existing path.
Its proof spans exact WorkspaceService, CurationStore, SharedAnnotations and native
binding-reader identities; unsupported/custom policies fall back to the full-state
oracle. It preserves exact metadata types/order, membership, binding and generation,
response-end attestation and locked mutation assertions. It owns no transaction.
When WorkspaceService publishes deep-frozen read-model maps, a cached proof is keyed
by the monotonic publication serial, binding header, source scope and index
generation and retains only a digest and member set (no rows); unfrozen maps keep
the exact content comparison. `DISCO_PROTOCOL_STATE_VERIFY=1` re-derives the digest
on every key hit as a debug assertion.
Moving it into metadata or decisions without that distinction would hide its
cross-owner proof rather than simplify callers. The finite-path proposal for
`disco/decisions/protocol_state.py` is explicitly replaced by this KEEP decision.
Its [central tests](../../tests/test_workspace_protocol_state.py) remain source
coverage pointers, not executed native acceptance. Response handles become inactive
on exit; failed responses close affected derived indexes.

The retained protocol HTTP owner offers `GET /api/protocols/:id?projection=browse`
for an unfiltered browsing descriptor. Default protocol responses remain complete
summaries. Canonical `WorkspaceService.protocol_browse` omits counts, rich cell
summaries, export links and annotation aggregates while retaining definition,
binding, effective query, filter choices and source eligibility. Captured reader
and transitive filter/decorate policies qualify this path; custom readers use the
full public protocol response before projection. Native response scopes attest at
close; legacy before/after revision checks refuse mixed descriptors. Fresh bounded
page receipts still own scientific actions. The owned HTTP examples are in
`python/tests/test_workspace_protocol_browse.py`; they do not qualify native SQL
or installed-app latency.

Full `WorkspaceService.protocol` summaries may reuse one response-local query and
one decorated membership when row/cell/protocol maps are plain dictionaries, all
transitive readers retain captured canonical identities, there is no curation
provider, and filters are empty or ordinary
identity/type/group equality filters. Binding readers must be absent or known
read-only for every protocol; a frozen target with an arbitrary foreign fallback
does not qualify. The current protocol's cell membership reuses that query while
other protocols are still read fresh. Counts and total counts remain independent
DTOs. Custom readers/providers and annotation/metadata filters retain the previous
read order and exceptions; `_cell_summary(rows)` keeps its public signature and
bins rows before reading memberships. No state is retained across responses, and
HTTP state/revision checks and native summary authority are unchanged. The focused
`python/tests/test_workspace_protocol_summary.py` examples compare complete
responses and verify query counts without replacing canonical reader methods.
This reduces repeated allocation; it neither changes process garbage collection
nor establishes latency or packaged-app qualification.

Trace reading stays in [WorkspaceService](../../workspace_service.py) and
[recording_workspace](../../recording_workspace.py), with the existing standalone
[export reader](../../query_workspace_export.py) retaining its own verified locator.
The shared read_response_window operation validates source signature and epoch/
response/parent identity, sample count/rate/units, and finite values before returning
an exact bounded window in recorded order. It performs no resampling, decimation,
unit conversion or synthetic fallback. Start/count validation, legitimate empty
end-of-stream slices and context-managed H5 closure remain unchanged. There is no
per-read cancellation token; hash validation can precede a small read.

These composition/source-verification paths are stable and cross-owned. Extracting
one trace function would not remove its provenance obligations and would cross the
paused acquisition/H5/export work. Existing service/source-identity/export-reader
tests retain those qualification scopes. No new native, H5, legacy/Ovation, export,
HTTP or real-data fixture is introduced or executed here.

## Reviewed background execution extension

The [background trace execution contract](../../../docs/architecture/trace-worker-execution.md)
adds bounded CPU execution for exact legacy background windows. Source admission
and `read_response_window` stay at their retained paths with unchanged scientific
checks. Detached plans cross processes; authority witnesses do not. The parent
revalidates before publication. Imported snapshot authority does not opt in. This
extension has its own synthetic-H5/source tests and does not relabel the earlier
module-reorganization receipts or qualify an assembled application.


## Overview recording rig display

The retained HTTP owner adds `recording_rigs` and `recording_rig_missing` to cell
summary DTOs for project and protocol Overview. Rig names come from the already
validated source summary's experiment `metadata.rig`, or recorded
`metadata.properties.rig` when the top-level key is absent. Recorded null/missing
names remain unknown; PATCH/MEA rig type and filenames do not supply rig names.
Multiple source rigs remain explicit rather than choosing one from repeated cell
labels. The exact cell UUID and existing epoch membership determine the sources.

The app indexes source descriptors once per published source-list lifetime.
Cell source IDs are collected during existing response-scoped row passes;
ordinary protocol reads do not build project-wide epoch/cell maps or open H5s.
The protocol Overview v2 ETag includes the relevant source rig token and checks
it again at response close. Source projection bytes, native metadata generation
recipes and scientific consent/decision authority remain unchanged. The inert
project presentation cache positively allowlists these display fields. Fixtures
in `test_workspace_api`, `test_workspace_protocol_overview_cache` and
`test_workspace_presentation_cache` cover native/fallback entries, metadata over
filenames, missing/multiple rigs, replacement and conditional reuse.
