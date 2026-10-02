"""Bounded protocol reads with exact metadata and verified native revisions.

The native v3 contract combines an exact metadata digest with transactional SQL
scope generations; dense saved annotations never enter the metadata cache.
Unsupported adapters retain the legacy full-state oracle and exact-input reuse.
"""
from __future__ import annotations

import copy
import contextlib
import math
import sys
import uuid
from itertools import chain
from dataclasses import asdict
from workspace_recipes import checksum
from workspace_curation import RevisionConflict

from workspace_disk_index import DiskMetadataIndex
from workspace_curation import CurationStore
from workspace_explorer import ExplorerHistory
from workspace_service import WorkspaceService
from workspace_annotations import SharedAnnotations

STATE_CACHE_BYTES = 64 * 1024 * 1024
STATE_CACHE_SCOPES = 8
_STORE_METHODS={name:getattr(CurationStore,name) for name in ('read','_rows','_state','summary_decisions')}
_SHARED_METHODS={name:getattr(SharedAnnotations,name) for name in ('snapshot','_rows','for_epochs','_validated_tags','summary','read_targets')}
_SERVICE_METHODS={name:getattr(WorkspaceService,name)
    for name in ('query_result','fingerprints','source_scope','binding','_ready','epoch_page','_epoch_page_identities','_decorate')}
_HISTORY_METHODS={name:getattr(ExplorerHistory,name) for name in ('protocol_binding','protocol_binding_header','get')}


def _exact_equal(left, right):
    """JSON-like equality with numeric types and signed zero preserved."""
    if left is right:
        return True
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (left.keys() == right.keys()
                and all(_exact_equal(value,right[key]) for key,value in left.items()))
    if isinstance(left, (list,tuple)):
        return len(left)==len(right) and all(_exact_equal(a,b) for a,b in zip(left,right))
    if type(left) is float and left == right == 0:
        return math.copysign(1,left)==math.copysign(1,right)
    return left == right


def _plain_epoch_records(value):
    return type(value) is list and all(type(row) is dict and len(row)==2
        and type(row.get('uuid')) is str and type(row.get('metadata_hash')) is str for row in value)


def _epoch_query_equal(current, proof):
    """Exact equality against a previously checked plain-string epoch proof.

    Plain string values cannot equate to bool/int/float values. Checking every
    current record's exact types permits C-level dictionary equality for this
    large, common schema while preserving the recursive comparator elsewhere.
    """
    if type(current) is not dict or current.keys()!=proof.keys():return False
    epochs=current['epochs'];expected=proof['epochs']
    if type(epochs) is not list or len(epochs)!=len(expected):return False
    for row,saved in zip(epochs,expected):
        if (type(row) is not dict or len(row)!=2 or type(row.get('uuid')) is not str
                or type(row.get('metadata_hash')) is not str or row!=saved):return False
    return all(_exact_equal(value,proof[key]) for key,value in current.items() if key!='epochs')


def _retained_bytes(value, limit):
    """Conservative identity-aware object estimate; short-circuit admission."""
    total,seen=0,set()
    pending=[iter((value,))]
    while pending:
        try:
            current=next(pending[-1])
        except StopIteration:
            pending.pop()
            continue
        identity=id(current)
        if identity in seen:
            continue
        seen.add(identity)
        total+=sys.getsizeof(current)
        if total>limit:
            return total
        if isinstance(current,dict):
            pending.append(chain(current.keys(),current.values()))
        elif isinstance(current,(list,tuple,set,frozenset)):
            pending.append(iter(current))
    return total


class _NativeProtocolRead:
    """Selected reads valid only inside one fully fenced response operation."""
    def __init__(self, reader, protocol, context, proof):
        self.reader,self.protocol,self.context,self.proof=reader,protocol,context,proof
        self.active=True

    def selected(self, epoch_ids):
        if not self.active:raise RuntimeError('Protocol read scope is closed')
        ids=tuple(str(uuid.UUID(key)) for key in epoch_ids)
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate epoch identity')
        if any(key not in self.proof['allowed'] for key in ids):
            raise ValueError('Curation includes epochs outside this protocol query')
        saved=self.reader.store._rows(self.protocol,ids,selected_only=True)
        fingerprints=self.proof['metadata']['fingerprints']
        return {key:self.reader.store._state(saved.get(key),fingerprints[key]) for key in ids}

    def accepts_shared(self, token):
        expected=self.context['generation']
        return all(getattr(token,key)==getattr(expected,key) for key in
            ('authority','project_uuid','shared_epoch','shared_generation'))


class ProtocolStateReader:
    def __init__(self, service, store, shared_annotations, full_state):
        self.service,self.store,self.shared,self.full_state=service,store,shared_annotations,full_state
        self.cache={}
        self.rejected={}
        self.native_cache={}

    @staticmethod
    def _native_method(owner, name, expected):
        method=getattr(owner,name,None)
        return getattr(method,'__func__',method) is expected

    def _native_contract(self):
        """Private-row proofs apply only to the native reader semantics.

        A custom public read/query policy may add inputs that are absent from
        this proof. It must use the full oracle, even if initially equivalent.
        Binding headers must belong to the same native immutable-recipe reader.
        """
        service,store=self.service,self.store
        if type(store) is not CurationStore or not all(self._native_method(store,name,method)
                for name,method in _STORE_METHODS.items()):
            return False
        if type(service) is not WorkspaceService or not all(self._native_method(service,name,method)
                for name,method in _SERVICE_METHODS.items()):
            return False
        provider=getattr(service,'binding_provider',None)
        header=getattr(service,'binding_header_provider',None)
        if provider is None:
            return header is None
        owner=getattr(provider,'__self__',None)
        return (type(owner) is ExplorerHistory
            and getattr(provider,'__func__',None) is _HISTORY_METHODS['protocol_binding']
            and getattr(header,'__self__',None) is owner
            and getattr(header,'__func__',None) is _HISTORY_METHODS['protocol_binding_header']
            and all(self._native_method(owner,name,method) for name,method in _HISTORY_METHODS.items()))

    @staticmethod
    def _generation_key(service,index,header):
        return ((id(index),index.generation,id(service.rows),id(service.protocols),id(service._fingerprints)),
                header['version'] if header else None,header.get('revision_uuid') if header else None)

    def _rejection_key(self, protocol):
        if not self._native_contract():
            return None
        service=self.service
        service._ready()
        index=getattr(service,'disk_index',None)
        if not isinstance(index,DiskMetadataIndex):
            return None
        index._check()
        provider=getattr(service,'binding_header_provider',None)
        return self._generation_key(service,index,provider(protocol) if provider else None)

    def _reject(self, protocol, metadata):
        header=metadata['binding']
        key=(metadata['generation'],header['version'] if header else None,header.get('revision_uuid') if header else None)
        self.rejected.pop(protocol,None)
        self.rejected[protocol]=key
        while len(self.rejected)>STATE_CACHE_SCOPES:
            self.rejected.pop(next(iter(self.rejected)))

    def _oracle(self, protocol, ids):
        result,current,revision=self.full_state(protocol)
        if any(key not in current for key in ids):
            raise ValueError('Curation includes epochs outside this protocol query')
        return result,current,revision,{key:current[key] for key in ids},result.get('dataset_binding',{}).get('version',0)

    def _metadata(self, protocol, *, include_shared=True):
        service=self.service
        if not self._native_contract():
            return None
        service._ready()
        index=getattr(service,'disk_index',None)
        if not isinstance(index,DiskMetadataIndex):
            return None  # Mutable/non-indexed adapters retain the full oracle.
        index._check()
        provider=getattr(service,'binding_header_provider',None)
        if provider is None and getattr(service,'binding_provider',None) is not None:
            return None
        header=provider(protocol) if provider else None
        entry=service.protocols[protocol]
        return {'generation':(id(index),index.generation,id(service.rows),id(service.protocols),id(service._fingerprints)),
            'project_uuid':service.project['project_uuid'],
            'definition':entry['definition'],'query':entry['result'],
            'fingerprints':service._fingerprints,'binding':header,
            'cells':service.cells,
            'source_scope_revision':service.source_scope()['revision'],
            'shared_revision':self.shared.snapshot()['revision'] if self.shared and include_shared else None}

    @staticmethod
    def _metadata_equal(left,right,*,plain_epochs=False):
        # Fingerprints are validated SHA256 strings in the full-state oracle;
        # normal dict equality is exact for those string keys and values.
        return (left['fingerprints']==right['fingerprints']
            and all((_epoch_query_equal(value,right[key]) if plain_epochs and key=='query'
                else _exact_equal(value,right[key])) for key,value in left.items() if key!='fingerprints'))

    def _bound_cells(self, members, metadata):
        if metadata['binding'] is None:
            return None
        return frozenset(self.service.rows[key]['cell_uuid'] for key in members)

    def _native_snapshot(self, metadata):
        """Share exact, privately owned source proofs across protocol scopes.

        Membership lists and the source fingerprint dictionary commonly repeat
        across many protocols. Only immutable-in-practice snapshots owned by
        this reader are shared; every use still compares the current mutable
        service values exactly. Different index generations never share proofs.
        """
        memo={}
        for entry in self.native_cache.values():
            previous=entry['metadata']
            if previous['generation']!=metadata['generation']:continue
            for key in ('fingerprints','cells'):
                value=metadata[key]
                if id(value) not in memo and (value==previous[key] if key=='fingerprints'
                        else _exact_equal(value,previous[key])):
                    memo[id(value)]=previous[key]
            for key in ('epochs','cells','source_revisions'):
                value=metadata['query'].get(key)
                old=previous['query'].get(key)
                if key in metadata['query'] and key in previous['query'] and id(value) not in memo and _exact_equal(value,old):
                    memo[id(value)]=old
        return copy.deepcopy(metadata,memo)

    def _selected(self, ids, allowed, saved, fingerprints):
        if any(key not in allowed for key in ids):
            raise ValueError('Curation includes epochs outside this protocol query')
        return {key:self.store._state(saved.get(key),fingerprints[key]) for key in ids}

    @contextlib.contextmanager
    def native_read(self, protocol_uuid, *, provider):
        """Share schema verification only within this complete fenced response."""
        from workspace_state_generation import StateGenerationAuthority
        tracker=getattr(self.store,'state_generation',None)
        contract=(tracker.response_contract() if type(tracker) is StateGenerationAuthority
            and self._native_contract() else contextlib.nullcontext())
        previous_index=getattr(self.shared,'_shared_tag_index',None)
        try:
            with contract:
                with self._native_read(protocol_uuid,provider=provider) as read:
                    yield read
        except BaseException:
            current_index=getattr(self.shared,'_shared_tag_index',None)
            for index in (previous_index,current_index if current_index is not previous_index else None):
                if index is not None:
                    with contextlib.suppress(Exception):index.close()
            raise

    @contextlib.contextmanager
    def _native_read(self, protocol_uuid, *, provider):
        """Fence membership, selected decisions and provenance as one response.

        The API owns the ordinary curation provider. Replacing it, the service
        reader or a native adapter retains the existing public read path.
        No token is reused across requests or after the final attestation.
        """
        if self.service.curation_provider is not provider:
            yield None
            return
        protocol=str(uuid.UUID(protocol_uuid))
        context=self.native_context(protocol)
        proof=self.native_cache.get(protocol) if context is not None else None
        if proof is None or proof['digest']!=context['metadata_digest']:
            yield None
            return
        read=_NativeProtocolRead(self,protocol,context,proof)
        from workspace_state_generation import StateGenerationAuthority
        tracker=self.store.state_generation
        generation_scope=(tracker.read_scope(context['generation']) if type(tracker) is StateGenerationAuthority
            else contextlib.nullcontext())
        previous_index=getattr(self.shared,'_shared_tag_index',None)
        try:
            with generation_scope:
                yield read
            # This is deliberately outside read_scope: a real SQL attestation
            # validates all membership, current rows and visible provenance.
            after=self.native_context(protocol)
            if after is None or after['query_revision']!=context['query_revision']:
                raise RevisionConflict({'query_revision':'changed while reading protocol response'})
        except BaseException:
            # Nested index operations may have loaded rows while an external
            # writer advanced the generation. Nothing derived in a rejected
            # response may survive under the scope's earlier generation token.
            current_index=getattr(self.shared,'_shared_tag_index',None)
            for index in (previous_index,current_index if current_index is not previous_index else None):
                if index is not None:
                    with contextlib.suppress(Exception):index.close()
            raise
        finally:
            read.active=False

    def native_context(self, protocol_uuid, epoch_ids=()):
        """Selected mutation/read inputs and an explicit v3 opaque revision.

        Native scope generations replace whole-dataset curation serialization.
        Exact metadata comparison remains mandatory; dense saved tags never enter
        this bounded cache. None means the unchanged legacy contract applies.
        """
        protocol=str(uuid.UUID(protocol_uuid))
        ids=tuple(str(uuid.UUID(key)) for key in epoch_ids)
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate epoch identity')
        tracker=getattr(self.store,'state_generation',None)
        if tracker is None or not self._native_contract():return None
        if self.shared is not None and (type(self.shared) is not SharedAnnotations or not all(
                self._native_method(self.shared,name,method) for name,method in _SHARED_METHODS.items())):
            return None
        token=tracker.token(protocol)
        if token is None:return None
        metadata=self._metadata(protocol,include_shared=False)
        if metadata is None:return None
        cached=self.native_cache.get(protocol)
        if cached is None or not self._metadata_equal(metadata,cached['metadata'],plain_epochs=cached['plain_epochs']) or self._bound_cells(cached['members'],metadata)!=cached['bound_cells']:
            self.native_cache.pop(protocol,None)
            if _retained_bytes(metadata,STATE_CACHE_BYTES)>STATE_CACHE_BYTES:return None
            snapshot=self._native_snapshot(metadata)
            plain_epochs=_plain_epoch_records(snapshot['query'].get('epochs'))
            result=self.service.query_result(protocol)
            for row in result['epochs']:row['metadata_hash']=metadata['fingerprints'][row['uuid']]
            result['metadata_fingerprint_version']=2
            result['source_scope']={'revision':metadata['source_scope_revision']}
            members=tuple(row['uuid'] for row in result['epochs'])
            digest=checksum({'query':result,'definition':metadata['definition'],'cell_metadata':metadata['cells']})
            after=self._metadata(protocol,include_shared=False)
            if after is None or not self._metadata_equal(after,snapshot,plain_epochs=plain_epochs) or tracker.token(protocol)!=token:return None
            allowed=None
            for entry in self.native_cache.values():
                if members==entry['members']:
                    members,allowed=entry['members'],entry['allowed']
                    break
            cached={'metadata':snapshot,'members':members,'allowed':allowed if allowed is not None else frozenset(members),'digest':digest,
                'plain_epochs':plain_epochs,
                'bound_cells':self._bound_cells(members,after),
                'source_revisions':tuple(result['source_revisions']),
                'binding_version':result.get('dataset_binding',{}).get('version',0)}
            cached['size']=_retained_bytes(cached,STATE_CACHE_BYTES)+4096
            if cached['size']>STATE_CACHE_BYTES:return None
            self.native_cache[protocol]=cached
            # Shared immutable snapshots count once in the retained graph.
            # Summing per-protocol estimates would evict identical large proofs.
            while (len(self.native_cache)>STATE_CACHE_SCOPES
                    or _retained_bytes(self.native_cache,STATE_CACHE_BYTES)+4096*len(self.native_cache)>STATE_CACHE_BYTES):
                self.native_cache.pop(next(iter(self.native_cache)))
        if any(key not in cached['allowed'] for key in ids):
            raise ValueError('Curation includes epochs outside this protocol query')
        revision='protocol-state-v3:'+checksum({'metadata':cached['digest'],'generation':asdict(token)})
        return {'query_revision':revision,'query_revision_contract':'protocol-state-v3','generation':token,
            'binding_version':cached['binding_version'],'source_revisions':cached['source_revisions'],
            'metadata_digest':cached['digest'],
            'fingerprints':{key:metadata['fingerprints'][key] for key in ids}}

    def assert_context_locked(self, protocol_uuid, context):
        self.store.state_generation.assert_current_locked(context['generation'])
        protocol=str(uuid.UUID(protocol_uuid))
        cached=self.native_cache.get(protocol)
        current=self._metadata(protocol,include_shared=False)
        if (cached is None or current is None or cached['digest']!=context['metadata_digest']
                or not self._metadata_equal(current,cached['metadata'],plain_epochs=cached['plain_epochs'])
                or self._bound_cells(cached['members'],current)!=cached['bound_cells']):
            raise RevisionConflict({'query_revision':'metadata changed during mutation'})
        return context['query_revision']

    def materialized_state(self, protocol_uuid):
        context=self.native_context(protocol_uuid)
        if context is None:return self.full_state(protocol_uuid)
        result,current,_=self.full_state(protocol_uuid)
        after=self.native_context(protocol_uuid)
        if after is None or after['query_revision']!=context['query_revision']:
            raise RevisionConflict({'query_revision':'changed during read'})
        result['query_revision_contract']='protocol-state-v3'
        return result,current,context['query_revision']

    def read_selected(self, protocol_uuid, epoch_ids):
        """Return selected current states, exact legacy revision, binding version.

        Callers hold the ordinary workspace DB lock. Native authority reads only
        selected SQL rows and fences their generation; legacy reuse verifies all
        saved values. Every cache admission proves exact current metadata.
        """
        protocol=str(uuid.UUID(protocol_uuid))
        ids=tuple(str(uuid.UUID(key)) for key in epoch_ids)
        if len(set(ids))!=len(ids):
            raise ValueError('Duplicate epoch identity')
        context=self.native_context(protocol,ids)
        if context is not None:
            saved=self.store._rows(protocol,ids,selected_only=True)
            selected={key:self.store._state(saved.get(key),context['fingerprints'][key]) for key in ids}
            tracker=self.store.state_generation
            after=self.native_context(protocol,ids)
            if after is None or after['query_revision']!=context['query_revision']:
                raise RevisionConflict({'query_revision':'changed during selected read'})
            return selected,context['query_revision'],context['binding_version']
        if protocol in self.rejected:
            key=self._rejection_key(protocol)
            previous=self.rejected.pop(protocol)
            if key is not None and key==previous:
                # This memo caches no scientific state or revision. Every read
                # still runs the complete oracle; only futile proof allocation
                # is skipped until generation/binding changes (no TTL).
                self.rejected[protocol]=key
                _,_,revision,selected,version=self._oracle(protocol,ids)
                return selected,revision,version
        metadata=self._metadata(protocol)
        cached=self.cache.get(protocol)
        if metadata is not None and cached is not None and self._metadata_equal(metadata,cached['metadata']):
            saved=self.store._rows(protocol,cached['members'])
            if (_exact_equal(saved,cached['saved'])
                    and self._bound_cells(cached['members'],metadata)==cached['bound_cells']):
                self.cache.pop(protocol)
                self.cache[protocol]=cached
                return (self._selected(ids,cached['allowed'],saved,metadata['fingerprints']),
                        cached['revision'],cached['binding_version'])
        self.cache.pop(protocol,None)
        # Check admission before copying large metadata dictionaries. An oversized
        # proof serves through the unchanged full-state path without retention.
        snapshot=(copy.deepcopy(metadata) if metadata is not None
                  and _retained_bytes(metadata,STATE_CACHE_BYTES)<=STATE_CACHE_BYTES else None)
        result,current,revision,selected,version=self._oracle(protocol,ids)
        if snapshot is None:
            if metadata is not None:
                self._reject(protocol,metadata)
            return selected,revision,version
        after=self._metadata(protocol)
        if after is None or not self._metadata_equal(snapshot,after):
            return selected,revision,version
        members=tuple(row['uuid'] for row in result['epochs'])
        saved=self.store._rows(protocol,members)
        # Verify the oracle's exact source/shared/binding state and every saved
        # decision/default against fresh input. A racing writer prevents caching.
        header=after['binding']
        if (result['source_scope']['revision']!=after['source_scope_revision']
                or result.get('shared_annotations_revision')!=after['shared_revision']
                or not _exact_equal(version,header['version'] if header else 0)
                or result.get('dataset_binding',{}).get('revision_uuid')!=(header.get('revision_uuid') if header else None)
                or any(not _exact_equal(self.store._state(saved.get(key),after['fingerprints'][key]),state) for key,state in current.items())):
            return selected,revision,version
        bound_cells=self._bound_cells(members,after)
        if header is not None and bound_cells!=frozenset(cell['uuid'] for cell in result['cells']):
            return selected,revision,version
        payload={'metadata':snapshot,'members':members,'allowed':frozenset(members),
            'saved':saved,'revision':revision,'binding_version':version,
            'bound_cells':bound_cells}
        size=_retained_bytes(payload,STATE_CACHE_BYTES)+4096
        if size<=STATE_CACHE_BYTES:
            # SQL adapters return fresh row objects; still copy saved values so
            # no mutable provider-owned object can silently change the proof.
            payload['saved']=copy.deepcopy(saved)
            payload['size']=size
            self.cache[protocol]=payload
            while len(self.cache)>STATE_CACHE_SCOPES or sum(item['size'] for item in self.cache.values())>STATE_CACHE_BYTES:
                self.cache.pop(next(iter(self.cache)))
        else:
            self._reject(protocol,after)
        return selected,revision,version
