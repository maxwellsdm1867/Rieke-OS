"""Bounded protocol reads with exact metadata and verified native revisions.

The native v3 contract combines an exact metadata digest with transactional SQL
scope generations; dense saved annotations never enter the metadata cache.
Unsupported adapters retain the legacy full-state oracle and exact-input reuse.
"""
from __future__ import annotations

import copy
import contextlib
import math
import os
import sys
import uuid
from itertools import chain
from dataclasses import asdict
from disco.workbench.recipes import checksum
from disco.decisions.curation import RevisionConflict

from disco.metadata.disk_index import DiskMetadataIndex
from disco.decisions.curation import CurationStore
from disco.decisions.explorer import ExplorerHistory
from workspace_service import WorkspaceService, publication_serial, FrozenDict, FrozenList
from disco.decisions.annotations import SharedAnnotations

PROTOCOL_STATE_CONTRACT='protocol-state-v4'
# v5 (bound mains on a frozen publication): the revision hashes the binding
# revision/version, the frozen recipe's content seal, the process-unique
# publication token, source scope revision and curation generation; no
# per-member metadata digest is computed. Shared tags stay outside, as in v4.
PROTOCOL_STATE_CONTRACT_V5='protocol-state-v5'
NATIVE_STATE_CONTRACTS=(PROTOCOL_STATE_CONTRACT,PROTOCOL_STATE_CONTRACT_V5)
_PUBLICATION_NONCE=str(uuid.uuid4())  # Serials restart per process; tokens never collide across runs.


def native_state_contract(revision):
    """The native contract name of a query revision string, or None."""
    if isinstance(revision,str):
        for contract in NATIVE_STATE_CONTRACTS:
            if revision.startswith(contract+':'):return contract
    return None

STATE_CACHE_BYTES = 64 * 1024 * 1024
STATE_CACHE_SCOPES = 8
_STORE_METHODS={name:getattr(CurationStore,name) for name in ('read','_rows','_state','summary_decisions')}
_SHARED_METHODS={name:getattr(SharedAnnotations,name) for name in ('snapshot','_rows','for_epochs','_validated_tags','summary','read_targets')}
_SERVICE_METHODS={name:getattr(WorkspaceService,name)
    for name in ('query_result','query_view','fingerprints','source_scope','binding','_ready','epoch_page','_epoch_page_identities','_decorate')}
_HISTORY_METHODS={name:getattr(ExplorerHistory,name) for name in ('protocol_binding','protocol_binding_header','get')}


_PLAIN={FrozenDict:dict,FrozenList:list}


def _exact_equal(left, right):
    """JSON-like equality with numeric types and signed zero preserved."""
    if left is right:
        return True
    # Published frozen containers compare exactly like their plain types.
    if _PLAIN.get(type(left),type(left)) is not _PLAIN.get(type(right),type(right)):
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
    if type(current) not in (dict,FrozenDict) or current.keys()!=proof.keys():return False
    epochs=current['epochs'];expected=proof['epochs']
    if type(epochs) not in (list,FrozenList) or len(epochs)!=len(expected):return False
    for row,saved in zip(epochs,expected):
        if (type(row) not in (dict,FrozenDict) or len(row)!=2 or type(row.get('uuid')) is not str
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


def same_protocol_state(after, context):
    """Read fence: v4 revisions omit shared tags, so also compare the full token."""
    return (after is not None and after['query_revision']==context['query_revision']
            and after.get('generation')==context.get('generation'))


def proof_members(entry):
    """Member tuple of an admitted proof; v5 proofs materialize it on first use."""
    if entry.get('members') is None and entry.get('member_source') is not None:
        members=tuple(entry['member_source']())
        entry['members'],entry['allowed']=members,frozenset(members)
        entry.pop('member_source',None)
    return entry['members']


def proof_allowed(entry):
    proof_members(entry)
    return entry['allowed']


class _NativeProtocolRead:
    """Selected reads valid only inside one fully fenced response operation."""
    def __init__(self, reader, protocol, context, proof):
        self.reader,self.protocol,self.context,self.proof=reader,protocol,context,proof
        self.active=True

    def selected(self, epoch_ids):
        if not self.active:raise RuntimeError('Protocol read scope is closed')
        ids=tuple(str(uuid.UUID(key)) for key in epoch_ids)
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate epoch identity')
        if any(key not in proof_allowed(self.proof) for key in ids):
            raise ValueError('Curation includes epochs outside this protocol query')
        saved=self.reader.store._rows(self.protocol,ids,selected_only=True)
        # Members are proven by the admitted proof; the closing native_context
        # fence rejects the response if the publication changed meanwhile.
        fingerprints=self.reader.service._fingerprints
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
        self.native_rejected={}

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
    def _publication_generation(service,index):
        # Every assignment of a published map advances this monotonic serial;
        # object identities alone are never a freshness key (address reuse).
        return (getattr(service,'_publication_serial',None),index.generation)

    @classmethod
    def _generation_key(cls,service,index,header):
        return (cls._publication_generation(service,index),
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

    def _metadata(self, protocol, *, include_shared=True, scoped=False):
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
        # Native revisions describe this effective cohort, including a frozen
        # binding, not its original query or unrelated project cells/epochs.
        # The legacy oracle deliberately retains its historical global inputs.
        query=service.query_view(protocol) if scoped else entry['result']
        members=[member['uuid'] for member in query['epochs']] if scoped else None
        fingerprints=({key:service._fingerprints[key] for key in members}
                      if scoped else service._fingerprints)
        cells=({key:service.cells[key] for key in sorted({service.rows[key]['cell_uuid'] for key in members})}
               if scoped else service.cells)
        return {'generation':self._publication_generation(service,index),
            'project_uuid':service.project['project_uuid'],
            'definition':entry['definition'],'query':query,
            'fingerprints':fingerprints,'binding':header,
            'cells':cells,
            **({'rows':{key:service.rows[key] for key in members}} if scoped else {}),
            'source_scope_revision':service.source_scope()['revision'],
            'shared_revision':self.shared.snapshot()['revision'] if self.shared and include_shared else None}

    def _publication_key(self, protocol):
        """O(1) proof key for a frozen publication, or None (compare contents).

        Valid only when every published proof map is deep-frozen: in-place
        mutation is then impossible and any replacement advances the monotonic
        publication serial. The binding header (revision/version) names the
        immutable, checksum-verified recipe; source scope is read live.
        Callers have verified the native contract and index for this read.
        """
        service=self.service
        serial=publication_serial(service)
        if serial is None:return None
        provider=getattr(service,'binding_header_provider',None)
        if provider is None and getattr(service,'binding_provider',None) is not None:return None
        header=provider(protocol) if provider else None
        if header is not None and type(header) is not dict:return None
        return {'serial':serial,'index':service.disk_index.generation,
            'project_uuid':service.project['project_uuid'],'header':copy.deepcopy(header),
            'source_scope_revision':service.source_scope()['revision']}

    @staticmethod
    def _same_key(current, saved):
        return (current is not None and saved is not None and current['serial']==saved['serial']
            and current['index']==saved['index'] and current['project_uuid']==saved['project_uuid']
            and current['source_scope_revision']==saved['source_scope_revision']
            and _exact_equal(current['header'],saved['header']))

    @staticmethod
    def _proof_digest(metadata):
        """Exact digest of the scoped proof inputs; reads, never mutates them."""
        query=metadata['query'];fingerprints=metadata['fingerprints']
        result={**query,'epochs':[{**row,'metadata_hash':fingerprints[row['uuid']]} for row in query['epochs']],
            'metadata_fingerprint_version':2,'source_scope':{'revision':metadata['source_scope_revision']}}
        digest=checksum({'query':result,'definition':metadata['definition'],'cell_metadata':metadata['cells'],
                         'epoch_metadata':metadata['rows']})
        return digest,result

    def _debug_verify(self, protocol, cached):
        """Opt-in (DISCO_PROTOCOL_STATE_VERIFY=1) content assertion for key hits."""
        if os.environ.get('DISCO_PROTOCOL_STATE_VERIFY')!='1' or cached.get('v5') is not None:return
        metadata=self._metadata(protocol,include_shared=False,scoped=True)
        if metadata is None or self._proof_digest(metadata)[0]!=cached['digest']:
            raise AssertionError('Publication-keyed protocol proof differs from current content')

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
            for key in ('fingerprints','cells','rows'):
                if key not in metadata or key not in previous:continue
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
            if not same_protocol_state(after,context):
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
        A frozen publication is proven in O(1) by its monotonic serial, binding
        header, source scope and index generation; the cache keeps only a digest
        and member set, never rows. Unfrozen read models compare exact contents.
        Dense saved tags never enter this cache. None means the legacy contract.
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
        self.service._ready()
        index=getattr(self.service,'disk_index',None)
        if not isinstance(index,DiskMetadataIndex):return None
        index._check()
        key=self._publication_key(protocol)
        cached=self.native_cache.get(protocol)
        if key is not None:
            if cached is not None and self._same_key(key,cached.get('key')):
                # O(1) hit: frozen maps + unchanged serial/header/scope/index
                # prove the admitted digest. Only the requested IDs are read.
                self._debug_verify(protocol,cached)
                if ids and any(k not in proof_allowed(cached) for k in ids):
                    raise ValueError('Curation includes epochs outside this protocol query')
                return self._native_revision(token,cached,{k:self.service._fingerprints[k] for k in ids})
            return self._published_context(protocol,ids,token,key,cached,tracker)
        return self._content_context(protocol,ids,token,cached,tracker)

    def _published_context(self, protocol, ids, token, key, cached, tracker):
        """Admit a digest-only proof for a frozen publication (no row snapshot)."""
        for name,(serial,_) in list(self.native_rejected.items()):
            if serial!=key['serial']:self.native_rejected.pop(name,None)  # Dropped on publish.
        memo=self.native_rejected.get(protocol)
        if memo is not None and memo[1]==(token,key['index'],key['source_scope_revision'],
                                          checksum(key['header']) if key['header'] is not None else None):
            return None  # Same futile admission; legacy oracle serves the read.
        if key['header'] is not None:
            bound=self._bound_v5_context(protocol,ids,token,key,tracker)
            if bound is not None:return bound
        metadata=self._metadata(protocol,include_shared=False,scoped=True)
        if metadata is None:return None
        digest,result=self._proof_digest(metadata)
        members=tuple(row['uuid'] for row in result['epochs'])
        if not self._same_key(self._publication_key(protocol),key) or tracker.token(protocol)!=token:
            return None  # A racing publication or write prevents admission.
        allowed=None
        for entry in self.native_cache.values():
            if entry.get('members') is not None and members==entry['members']:
                members,allowed=entry['members'],entry['allowed']
                break
        entry={'key':key,'members':members,'allowed':allowed if allowed is not None else frozenset(members),
            'digest':digest,'bound_cells':self._bound_cells(members,metadata),
            'source_revisions':tuple(result['source_revisions']),
            'binding_version':result.get('dataset_binding',{}).get('version',0)}
        entry['size']=sys.getsizeof(entry['members'])+sys.getsizeof(entry['allowed'])+4096
        if entry['size']>STATE_CACHE_BYTES:
            self.native_cache.pop(protocol,None)
            self.native_rejected.pop(protocol,None)
            self.native_rejected[protocol]=(key['serial'],(token,key['index'],key['source_scope_revision'],
                checksum(key['header']) if key['header'] is not None else None))
            while len(self.native_rejected)>STATE_CACHE_SCOPES:
                self.native_rejected.pop(next(iter(self.native_rejected)))
            return None
        self.native_cache.pop(protocol,None)
        self.native_cache[protocol]=entry
        self.native_rejected.pop(protocol,None)
        self._evict_native()
        if any(k not in entry['allowed'] for k in ids):
            raise ValueError('Curation includes epochs outside this protocol query')
        return self._native_revision(token,entry,{k:metadata['fingerprints'][k] for k in ids})

    def _bound_v5_context(self, protocol, ids, token, key, tracker):
        """protocol-state-v5 proof for a bound main: identities, not a digest.

        The binding header names an immutable, checksum-verified revision; its
        content seal plus the publication token (frozen rows/fingerprints) and
        the live source scope and curation generation determine every input of
        the bound query result. The member set is materialized only when a
        caller asks about specific epochs (never for a bare revision read). A
        history exposing ``header(revision)``/``members(revision)`` (sealed
        delta revisions) is read through those, not the full recipe. None falls
        back to the v4 digest proof.
        """
        service=self.service
        header=key['header']
        revision=header.get('revision_uuid')
        owner=getattr(getattr(service,'binding_provider',None),'__self__',None)
        meta=self._bound_revision_header(owner,protocol,header)
        if meta is None or not isinstance(meta.get('content_sha256'),str):return None
        if not self._same_key(self._publication_key(protocol),key) or tracker.token(protocol)!=token:
            return None

        def members():
            reader=getattr(owner,'members',None)
            if callable(reader) and getattr(type(owner),'members',None) is not None:
                identities=tuple(reader(revision))
            else:
                recipe=getattr(owner,'_recipe_cache',{}).get(revision) or (service.binding(protocol) or {}).get('recipe')
                if recipe is None:raise ValueError('Bound dataset revision is unavailable')
                identities=tuple(member['uuid'] for member in recipe['epochs'])
            if any(identity not in service.rows for identity in identities):
                raise ValueError('Bound dataset contains unavailable epochs; explicit reconciliation is required')
            return identities
        entry={'key':key,'members':None,'allowed':None,'member_source':members,
            'digest':None,'bound_cells':None,'source_revisions':tuple(meta.get('source_revisions',())),
            'binding_version':header['version'],
            'v5':{'project_uuid':key['project_uuid'],'binding_revision_uuid':revision,
                  'binding_version':header['version'],'content_seal':meta['content_sha256'],
                  'publication':_PUBLICATION_NONCE+':'+str(key['serial']),'index':key['index'],
                  'source_scope_revision':key['source_scope_revision']}}
        entry['size']=4096
        self.native_cache.pop(protocol,None)
        self.native_cache[protocol]=entry
        self.native_rejected.pop(protocol,None)
        self._evict_native()
        if ids and any(k not in proof_allowed(entry) for k in ids):
            raise ValueError('Curation includes epochs outside this protocol query')
        return self._native_revision(token,entry,{k:service._fingerprints[k] for k in ids})

    def _bound_revision_header(self, owner, protocol, header):
        """Seal and source revisions of the bound revision, without its members."""
        revision=header.get('revision_uuid')
        reader=getattr(owner,'header',None)
        if callable(reader) and getattr(type(owner),'header',None) is not None:
            try:
                return reader(revision)
            except (KeyError,ValueError):
                return None
        recipe=getattr(owner,'_recipe_cache',{}).get(revision)
        if recipe is None:
            binding=self.service.binding(protocol)
            if (binding is None or binding.get('revision_uuid')!=revision
                    or binding.get('version')!=header.get('version')):
                return None
            recipe=binding['recipe']
        return {'content_sha256':recipe.get('content_sha256'),'source_revisions':recipe.get('source_revisions',())}

    def _evict_native(self):
        def retained():
            seen=set()
            snapshots={key:entry for key,entry in self.native_cache.items() if 'metadata' in entry}
            total=(_retained_bytes(snapshots,STATE_CACHE_BYTES)+4096*len(snapshots)) if snapshots else 0
            for entry in self.native_cache.values():
                if 'metadata' in entry:continue
                for value in (entry.get('members'),entry.get('allowed')):
                    if value is not None and id(value) not in seen:
                        seen.add(id(value));total+=sys.getsizeof(value)
                total+=4096
            return total
        # Shared member sets count once; snapshots (unfrozen path) count fully.
        while len(self.native_cache)>STATE_CACHE_SCOPES or retained()>STATE_CACHE_BYTES:
            self.native_cache.pop(next(iter(self.native_cache)))

    def _content_context(self, protocol, ids, token, cached, tracker):
        """Unfrozen read model: compare exact current contents with a snapshot."""
        if cached is not None and 'metadata' not in cached:cached=None
        metadata=self._metadata(protocol,include_shared=False,scoped=True)
        if metadata is None:return None
        if cached is None or not self._metadata_equal(metadata,cached['metadata'],plain_epochs=cached['plain_epochs']) or self._bound_cells(cached['members'],metadata)!=cached['bound_cells']:
            self.native_cache.pop(protocol,None)
            if _retained_bytes(metadata,STATE_CACHE_BYTES)>STATE_CACHE_BYTES:return None
            snapshot=self._native_snapshot(metadata)
            plain_epochs=_plain_epoch_records(snapshot['query'].get('epochs'))
            digest,result=self._proof_digest(metadata)
            members=tuple(row['uuid'] for row in result['epochs'])
            after=self._metadata(protocol,include_shared=False,scoped=True)
            if after is None or not self._metadata_equal(after,snapshot,plain_epochs=plain_epochs) or tracker.token(protocol)!=token:return None
            allowed=None
            for entry in self.native_cache.values():
                if members==entry['members']:
                    members,allowed=entry['members'],entry['allowed']
                    break
            cached={'metadata':snapshot,'members':members,'allowed':allowed if allowed is not None else frozenset(members),'digest':digest,
                'plain_epochs':plain_epochs,'key':None,
                'bound_cells':self._bound_cells(members,after),
                'source_revisions':tuple(result['source_revisions']),
                'binding_version':result.get('dataset_binding',{}).get('version',0)}
            cached['size']=_retained_bytes(cached,STATE_CACHE_BYTES)+4096
            if cached['size']>STATE_CACHE_BYTES:return None
            self.native_cache[protocol]=cached
            self._evict_native()
        if any(key not in cached['allowed'] for key in ids):
            raise ValueError('Curation includes epochs outside this protocol query')
        return self._native_revision(token,cached,{key:metadata['fingerprints'][key] for key in ids})

    @staticmethod
    def _native_revision(token, cached, fingerprints):
        # v4 covers protocol metadata and curation generations only. Shared tags
        # carry their own per-target author revisions, so a tag write does not
        # retire every page's curation authority. Reads still fence shared
        # annotations separately (accepts_shared) and keep the full token.
        scoped={key:value for key,value in asdict(token).items() if key not in ('shared_epoch','shared_generation')}
        if cached.get('v5') is not None:
            contract=PROTOCOL_STATE_CONTRACT_V5
            revision=contract+':'+checksum({**cached['v5'],'generation':scoped})
        else:
            contract=PROTOCOL_STATE_CONTRACT
            revision=contract+':'+checksum({'metadata':cached['digest'],'generation':scoped})
        return {'query_revision':revision,'query_revision_contract':contract,'generation':token,
            'binding_version':cached['binding_version'],'source_revisions':cached['source_revisions'],
            'metadata_digest':cached['digest'],
            'fingerprints':fingerprints}

    def assert_context_locked(self, protocol_uuid, context):
        self.store.state_generation.assert_current_locked(context['generation'])
        protocol=str(uuid.UUID(protocol_uuid))
        cached=self.native_cache.get(protocol)
        if cached is None or cached['digest']!=context['metadata_digest']:
            raise RevisionConflict({'query_revision':'metadata changed during mutation'})
        if cached.get('key') is not None:
            # Frozen publication: the serial/header/scope key is a complete proof.
            if not self._same_key(self._publication_key(protocol),cached['key']):
                raise RevisionConflict({'query_revision':'metadata changed during mutation'})
            return context['query_revision']
        current=self._metadata(protocol,include_shared=False,scoped=True)
        if (current is None or not self._metadata_equal(current,cached['metadata'],plain_epochs=cached['plain_epochs'])
                or self._bound_cells(cached['members'],current)!=cached['bound_cells']):
            raise RevisionConflict({'query_revision':'metadata changed during mutation'})
        return context['query_revision']

    def read_revision(self, protocol_uuid):
        """Fresh revision for a caller that already owns bound membership.

        The native proof still compares exact current metadata and generations.
        Unsupported authority uses the same full-state oracle, exactly once.
        Callers retain independent opening and closing checks.
        """
        context = self.native_context(protocol_uuid)
        return context['query_revision'] if context is not None else self.full_state(protocol_uuid)[2]

    def materialized_state(self, protocol_uuid):
        context=self.native_context(protocol_uuid)
        if context is None:return self.full_state(protocol_uuid)
        result,current,_=self.full_state(protocol_uuid)
        after=self.native_context(protocol_uuid)
        if not same_protocol_state(after,context):
            raise RevisionConflict({'query_revision':'changed during read'})
        result['query_revision_contract']=context['query_revision_contract']
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
            if not same_protocol_state(after,context):
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
