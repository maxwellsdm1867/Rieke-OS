"""Historical display-only membership receipts; never mutation authority or samples.

Prepared under the ordinary frozen-context checks. Reads attest the captured
view's requested source/epoch, not current tags, drafts, bindings or pending set.
"""
from collections import OrderedDict
import hashlib
import uuid

from disco.metadata.disk_index import DiskMetadataIndex
from disco.workbench.recipes import checksum
import workspace_service as trace_service
from workspace_service import WorkspaceService

MAX_MEMBERS = 1000000
MAX_BYTES = 64 * 1024 * 1024
MAX_VIEWS = 8
# Conservative allowance for the bounded entry/public dictionaries, key tuple,
# UUID/hash strings and registry links; bulk proofs are charged separately.
ENTRY_BYTES = 4096
_METHODS = {
    '_ready': WorkspaceService._ready,
    '_input_signature': WorkspaceService._input_signature,
    '_verified_source': WorkspaceService._verified_source,
    'capture_trace_read': WorkspaceService.capture_trace_read,
    'validate_trace_read': WorkspaceService.validate_trace_read,
    'trace': WorkspaceService.trace,
    'trace_batch': WorkspaceService.trace_batch,
}
_CANONICAL_SAMPLE_READER = trace_service.read_response_window
_CANONICAL_WINDOW_READER = trace_service._response_window_reader
_INDEX_METHODS = {
    '_check': DiskMetadataIndex._check,
    '_connect': DiskMetadataIndex._connect,
    'trace_record': DiskMetadataIndex.trace_record,
}


class TraceViewConflict(ValueError):
    pass


def _source_fingerprint(records, identity):
    """Look up one manifest proof in compact SHA256/SHA256 records."""
    key = bytes.fromhex(identity)
    if len(key) != 32:
        raise TraceViewConflict('Invalid captured recording identity')
    lo, hi = 0, len(records) // 64
    while lo < hi:
        mid = (lo + hi) // 2
        if records[mid * 64:mid * 64 + 32] < key:
            lo = mid + 1
        else:
            hi = mid
    offset = lo * 64
    if records[offset:offset + 32] != key:
        raise TraceViewConflict('Recording is outside this captured display view')
    return records[offset + 32:offset + 64].hex()


def _member(records, identity):
    key = uuid.UUID(identity).bytes
    lo, hi = 0, len(records) // 48
    while lo < hi:
        mid = (lo + hi) // 2
        found = records[mid * 48:mid * 48 + 16]
        if found < key:
            lo = mid + 1
        else:
            hi = mid
    offset = lo * 48
    if records[offset:offset + 16] != key:
        raise TraceViewConflict('Epoch is outside this captured display view')
    return records[offset + 16:offset + 48].hex()


class TraceViews:
    def __init__(self, service, policy=None):
        self.service = service
        self.policy = policy
        self.entries = OrderedDict()
        self.keys = {}
        self.bytes = 0
        self.publication = None

    def _canonical(self):
        service = self.service
        index = getattr(service, 'disk_index', None)
        return (type(service) is WorkspaceService and type(index) is DiskMetadataIndex and
                (self.policy is None or self.policy()) and
                trace_service.read_response_window is _CANONICAL_SAMPLE_READER and
                trace_service._response_window_reader is _CANONICAL_WINDOW_READER and
                all(getattr(getattr(service, name, None), '__func__', getattr(service, name, None)) is method
                    for name, method in _METHODS.items()) and
                all(getattr(getattr(index, name, None), '__func__', None) is method
                    for name, method in _INDEX_METHODS.items()))

    def _sync_publication(self):
        service = self.service
        owner = (service.project['project_uuid'], getattr(service, '_explore_publication', None),
                 id(getattr(service, 'disk_index', None)), id(service.rows),
                 id(service._fingerprints), id(service.manifests),
                 id(getattr(service, '_metadata_readiness', None)))
        if owner != self.publication:
            # Revoked publications must not retain old project-sized mappings or
            # index leases behind a small membership-byte budget.
            self.entries.clear()
            self.keys.clear()
            self.bytes = 0
            self.publication = owner

    def prepare(self, context):
        # Optional display support must not inspect native-only state on a
        # legacy/custom service that cannot issue this capability at all.
        if type(self.service) is not WorkspaceService:
            return None
        self._sync_publication()
        if not self._canonical() or not context.get('main_revision_uuid'):
            return None
        service = self.service
        service._ready()
        index = service.disk_index
        index._check()
        selected = context.get('_view_ids')
        subset = checksum(sorted(selected)) if selected is not None else None
        key = (service._explore_publication, id(index), id(service.rows), id(service._fingerprints),
               id(service.manifests), context['actor'], context['protocol_uuid'],
               context['candidate_revision_uuid'], context['candidate_recipe_sha256'],
               context['baseline_recipe_sha256'], context['main_recipe_sha256'],
               context['expected_binding_version'], subset)
        previous = self.keys.get(key)
        if previous in self.entries:
            self.entries.move_to_end(previous)
            return dict(self.entries[previous]['public'])
        pending = context['pending']
        if context.get('unavailable', set()) & pending.keys():
            return None
        identities = sorted(pending if selected is None else pending.keys() & selected)
        if len(identities) > MAX_MEMBERS or len(identities) * 48 > MAX_BYTES:
            return None
        sources = sorted({service.rows[identity]['source_sha256'] for identity in identities})
        byte_cost = len(identities) * 48 + len(sources) * 64 + ENTRY_BYTES
        if byte_cost > MAX_BYTES:
            return None
        # Compact immutable records bound memory and keep each lookup logarithmic
        # (at most 20 comparisons), independent of all other project metadata.
        records = b''.join(uuid.UUID(identity).bytes + bytes.fromhex(pending[identity]) for identity in identities)
        if len(records) != len(identities) * 48:
            raise TraceViewConflict('Invalid captured metadata fingerprint')
        source_records = b''.join(bytes.fromhex(identity) + bytes.fromhex(checksum(service.manifests[identity]))
                                  for identity in sources)
        if len(source_records) != len(sources) * 64:
            raise TraceViewConflict('Invalid captured recording fingerprint')
        token = str(uuid.uuid4())
        public = dict(kind='prepared_display', token=token, project_uuid=service.project['project_uuid'],
            publication_revision=service._explore_publication,
            view_kind='workbench_selected' if selected is not None else 'workbench_pending',
            protocol_uuid=context['protocol_uuid'], candidate_revision_uuid=context['candidate_revision_uuid'],
            membership_sha256=hashlib.sha256(records).hexdigest())
        entry = dict(key=key, public=public, members=records, actor=context['actor'], index=index,
            rows=service.rows, fingerprints=service._fingerprints, manifests=service.manifests,
            readiness=getattr(service, '_metadata_readiness', None),
            source_records=source_records, byte_cost=byte_cost)
        self.entries[token] = entry
        self.keys[key] = token
        self.bytes += byte_cost
        while len(self.entries) > MAX_VIEWS or self.bytes > MAX_BYTES:
            old, removed = self.entries.popitem(last=False)
            self.keys.pop(removed['key'], None)
            self.bytes -= removed['byte_cost']
        return dict(public)

    def capture(self, token, epoch, actor):
        self._sync_publication()
        entry = self.entries.get(token)
        if entry is None:
            raise TraceViewConflict('Display view expired; reopen the view')
        self._current(entry, actor)
        fingerprint = _member(entry['members'], epoch)
        sealed = entry['index'].trace_record(epoch)
        row = self.service.rows.get(epoch)
        if (sealed is None or row is None or sealed['fingerprint'] != fingerprint or
                self.service._fingerprints.get(epoch) != fingerprint or checksum(row) != checksum(sealed['row'])):
            raise TraceViewConflict('Requested epoch metadata changed; reopen the view')
        source = row['source_sha256']
        manifest = self.service.manifests.get(source)
        if manifest is None or checksum(manifest) != _source_fingerprint(entry['source_records'], source):
            raise TraceViewConflict('Requested recording registration changed; reopen the view')
        path, signature = self.service._verified_source(manifest)
        return {'entry': entry, 'source_path': str(path), 'source_signature': tuple(signature)}

    def _current(self, entry, actor):
        service = self.service
        if (not self._canonical() or actor != entry['actor'] or
                service.project['project_uuid'] != entry['public']['project_uuid'] or
                service._explore_publication != entry['public']['publication_revision'] or
                service.disk_index is not entry['index'] or service.rows is not entry['rows'] or
                service._fingerprints is not entry['fingerprints'] or service.manifests is not entry['manifests'] or
                getattr(service, '_metadata_readiness', None) is not entry['readiness']):
            raise TraceViewConflict('Display source publication changed; reopen the view')
        service._ready()
        entry['index']._check()

    def finish(self, token, epoch, actor, witness, value):
        current = self.capture(token, epoch, actor)
        entry = witness['entry']
        if (current['entry'] is not entry or current['source_path'] != witness['source_path'] or
                current['source_signature'] != witness['source_signature']):
            raise TraceViewConflict('Display view or source changed during the read')
        value['read_context'] = dict(entry['public'])
        for window in value.get('windows', []):
            window['read_context'] = dict(entry['public'])
        return value
