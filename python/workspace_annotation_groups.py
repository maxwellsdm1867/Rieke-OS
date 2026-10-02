"""Supported-size server query tagging: one frozen group, one native commit.

Resolution reuses the O(project) tree scope oracle. This is not a streaming or
million-epoch job system. Preview IDs never leave the server; durable receipts
provide idempotency and changed-only, query-free inverses after a restart.
No-op operations have a durable actor/request receipt; annotation audit events
describe changed tag sets only, as in the existing shared annotation contract.
"""
from __future__ import annotations

import copy
import datetime as dt
from dataclasses import fields,is_dataclass
import getpass
import re
import sys
import time
import uuid

from workspace_annotations import identity, text
from workspace_curation import RevisionConflict
from workspace_explore_queries import context_annotation_fields, context_annotation_locks, generation
from workspace_recipes import checksum, parse_splits
from workspace_tree import joint_definition
from workspace_tree_pages import TreePages, TreePath, _retained_scope_bytes, validate_tree_path

PROJECT_LIMIT=10_000
SCOPE_BYTES=64*1024*1024
RETAINED_BYTES=8*1024*1024
OPERATION_BYTES=32*1024*1024
PREVIEW_SECONDS=600
MAX_PREVIEWS=4


class RetainedBudget:
    """Conservative retained-object admission accounting, not an RSS bound."""
    def __init__(self, used=0, maximum=RETAINED_BYTES):
        self.used=used;self.maximum=maximum

    def charge(self, value):
        pending=[value];seen=set()
        while pending:
            current=pending.pop()
            if id(current) in seen:continue
            seen.add(id(current))
            self.used+=sys.getsizeof(current)+32
            if self.used>self.maximum:
                raise ValueError('This group exceeds the supported retained-memory budget; nothing was committed')
            if isinstance(current,dict):pending.extend(current.keys());pending.extend(current.values())
            elif isinstance(current,(list,tuple,set,frozenset)):pending.extend(current)
            elif is_dataclass(current):pending.extend(getattr(current,field.name) for field in fields(current))
        return value

    def reserve(self,amount):
        self.used+=amount
        if self.used>self.maximum:raise ValueError('This group exceeds the supported retained-memory budget; nothing was committed')


def group_receipt_table(dj):
    schema=dj.Schema('recording_workspace')
    @schema
    class AnnotationGroupReceipt(dj.Manual):
        definition='''
        project_uuid: varchar(36)
        operation_uuid: varchar(36)
        ---
        actor: varchar(255)
        profile_uuid: varchar(36)
        request_sha256: char(64)
        receipt: json
        created_at: datetime
        '''
    return AnnotationGroupReceipt


class AnnotationGroups:
    def __init__(self,service,annotations,receipt_table,db_lock,registration_locks,revision_guard=None):
        self.service=service;self.annotations=annotations;self.Receipt=receipt_table
        self.db_lock=db_lock;self.registration_locks=registration_locks
        self.revision_guard=revision_guard;self.project=service.project['project_uuid']
        self.selections={}

    def _receipt(self, operation, actor, request_sha):
        rows=(self.Receipt&{'project_uuid':self.project,'operation_uuid':operation}).to_dicts()
        if not rows:return None
        row=rows[0]
        if row['actor']!=actor or row['request_sha256']!=request_sha:
            raise RevisionConflict({'operation_uuid':operation,'reason':'Operation UUID belongs to a different request or actor'})
        return self._public(row['receipt'],replayed=True)

    @staticmethod
    def _public(receipt,replayed=False):
        return {key:value for key,value in receipt.items() if key not in {'inverse_targets','scope','fences'}} | {'replayed':replayed}

    def _save(self,operation,actor,profile,request_sha,receipt):
        self.Receipt.insert1(dict(project_uuid=self.project,operation_uuid=operation,actor=actor,
            profile_uuid=profile,request_sha256=request_sha,receipt=receipt,
            created_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)))

    def _tracker(self):
        tracker=getattr(self.service,'_explore_state_generation',None)
        if tracker is None:raise ValueError('Verified native annotation authority is required for group tagging')
        return tracker

    def _vector(self,context):
        protocols={field.split('/')[1] for field in context_annotation_fields(context) if field.startswith('curation/')}
        if context.get('protocol_uuid'):protocols.add(context['protocol_uuid'])
        tracker=self._tracker()
        vector=[tracker.token(protocol) for protocol in [None,*sorted(protocols)]]
        if any(token is None for token in vector):
            raise ValueError('Native group annotation authority is unavailable; refresh before saving')
        return tuple(vector)

    def _assert_vector(self,vector):
        tracker=self._tracker()
        for token in vector:tracker.assert_current_locked(token)

    def _seals(self,context):
        service=self.service;service._ready()
        index=getattr(service,'disk_index',None);typed=getattr(service,'typed_index',None)
        if index:index._check()
        if typed:typed._check()
        protocol=context.get('protocol_uuid')
        provider=getattr(service,'binding_header_provider',None)
        binding=(provider(protocol) if provider else service.binding(protocol)) if protocol else None
        binding=({key:binding.get(key) for key in ('project_uuid','protocol_uuid','revision_uuid','version')} if binding else None)
        return {'metadata':index.generation if index else checksum(service._fingerprints),
            'typed':typed.generation_token if typed else None,'source':service.source_scope()['revision'],
            'publication':getattr(service,'_explore_publication',None),'binding':binding}

    def _verify_sources(self,targets):
        sources=set()
        for target,fingerprint,*_ in targets:
            if self.service._fingerprints.get(target)!=fingerprint or target not in self.service.rows:
                raise RevisionConflict({'target_uuid':target,'reason':'Recorded identity or metadata fingerprint changed'})
            sources.add(self.service.rows[target]['source_sha256'])
        for source in sorted(sources):
            manifest=self.service.manifests.get(source)
            if manifest is None:raise RevisionConflict({'source':'Recording is no longer registered'})
            self.service._verified_source(manifest)

    def preview(self,body,actor):
        if not isinstance(body,dict) or set(body)!={'scope','profile_uuid'}:
            raise ValueError('Use scope and profile_uuid for a group preview')
        profile=identity(body['profile_uuid']);scope=copy.deepcopy(body['scope'])
        if (not isinstance(scope,dict) or set(scope)-{'protocol_uuid','predicate','filters','splits','path','revision'}
                or 'revision' not in scope or not isinstance(scope['revision'],str)
                or not re.fullmatch('[0-9a-f]{64}',scope['revision'])):
            raise ValueError('Choose a current project/protocol tree group; candidate contexts are unsupported')
        validate_tree_path(scope.get('path',[]))
        context={key:value for key,value in scope.items() if key not in {'path','revision'}}
        with self.db_lock,self.registration_locks():
            now=time.monotonic()
            self.selections={key:value for key,value in self.selections.items() if value['expires']>now}
            if len(self.selections)>=MAX_PREVIEWS:raise ValueError('Close or wait for an earlier group preview to expire')
            self.service._ready()
            if len(self.service.rows)>PROJECT_LIMIT:
                raise ValueError('This project exceeds the qualified 10,000-recording scope-resolver admission; nothing was tagged')
            index=getattr(self.service,'disk_index',None)
            catalog=index.catalog() if index else self.service._registered_tree_fields()[0]
            definitions={field['id']:field for field in catalog['fields']}
            order=parse_splits(scope.get('splits','date,cell,block'),definitions)
            for field in order:
                if field not in definitions:definitions[field]=joint_definition(field,definitions)
            context['summary_fields']=sorted(TreePath(order,definitions,scope.get('path',[])).fields)
            with context_annotation_locks(self.service,context):
                profiles=self.annotations.list_profiles()['profiles']
                if profile not in {row['profile_uuid'] for row in profiles}:raise ValueError('Choose an existing tag author profile')
                before=generation(self.service,context)
                result=TreePages(self.service)._scope(scope)
                if _retained_scope_bytes(result,self.service.rows,SCOPE_BYTES)>SCOPE_BYTES:
                    raise ValueError('Tree scope exceeds the supported 64 MiB retained scope budget')
                rows,_,values,definitions,order,revision=result
                if revision!=scope['revision']:raise RevisionConflict({'tree':'Tree changed; reopen the group'})
                path=TreePath(order,definitions,scope.get('path',[]))
                vector=self._vector(context)
                targets=[];budget=RetainedBudget()
                for row in rows:
                    # An empty structural path selects every scoped row. A
                    # native empty layout intentionally projects no values.
                    if not path.path or path.matches(values[row['epoch_uuid']]):
                        if len(targets)>=PROJECT_LIMIT:raise ValueError('Group exceeds the supported project admission')
                        item=[row['epoch_uuid'],self.service._fingerprints[row['epoch_uuid']],0]
                        budget.charge(item);targets.append(item)
                if not targets:raise ValueError('This group has no matching epochs')
                for offset in range(0,len(targets),250):
                    batch=targets[offset:offset+250]
                    requested=[dict(target_kind='epoch',target_uuid=row[0],profile_uuid=profile) for row in batch]
                    relation=self.annotations.Annotation&{'project_uuid':self.project}
                    records={row['target_uuid']:row['revision'] for row in (relation&requested).proj('revision').to_dicts()}
                    for item in batch:item[2]=records.get(item[0],0)
                self._verify_sources(targets)
                guard=self.revision_guard(scope['protocol_uuid']) if scope.get('protocol_uuid') and self.revision_guard else None
                fences=self._seals(context)
                if self._vector(context)!=vector or generation(self.service,context)!=before:
                    raise RevisionConflict({'tree':'Scope changed while capturing the group'})
                key=str(uuid.uuid4())
                entry=dict(scope=scope,context=context,profile=profile,actor=actor,targets=targets,
                    vector=vector,fences=fences,guard=guard,expires=now+PREVIEW_SECONDS,bytes=budget.used)
                budget.charge(vector)
                if guard:
                    budget.charge(guard)
                    # Native query guards retain their explicit context/token
                    # and source-revision tuple in closure cells. Existing API
                    # owners stay borrowed; all newly retained fact graphs count.
                    for cell in getattr(guard,'__closure__',()) or ():
                        budget.charge(cell.cell_contents)
                budget.charge({key:value for key,value in entry.items() if key not in {'targets','guard','vector'}})
                entry['bytes']=budget.used
                if sum(item['bytes'] for item in self.selections.values())+budget.used>RETAINED_BYTES:
                    raise ValueError('Active previews exceed the supported retained-memory admission')
                self.selections[key]=entry
                return dict(selection_uuid=key,target_kind='epoch',count=len(targets),profile_uuid=profile,
                    tree_revision=revision,expires_in_seconds=PREVIEW_SECONDS,
                    resolver='existing project tree scope',project_epoch_count=len(self.service.rows),
                    admission=dict(project_epochs=PROJECT_LIMIT,preview_retained_bytes=RETAINED_BYTES,
                        operation_retained_bytes=OPERATION_BYTES,scope_bytes=SCOPE_BYTES))

    def apply(self,body,actor):
        if not isinstance(body,dict) or set(body)!={'selection_uuid','profile_uuid','tag','operation_uuid'}:
            raise ValueError('Use selection_uuid, profile_uuid, tag and operation_uuid')
        selection=identity(body['selection_uuid']);profile=identity(body['profile_uuid'])
        tag=text(body['tag']);operation=identity(body['operation_uuid']);actor=text(actor)
        request_sha=checksum({'kind':'group_add',**body})
        with self.db_lock:
            replay=self._receipt(operation,actor,request_sha)
            if replay:return replay
            entry=self.selections.get(selection)
            with self.registration_locks(),context_annotation_locks(self.service,entry['context'] if entry else {}):
                replay=self._receipt(operation,actor,request_sha)
                if replay:return replay
                if not entry or entry['expires']<=time.monotonic():raise ValueError('Group preview expired or the server restarted; reopen the group')
                if entry['actor']!=actor or entry['profile']!=profile:raise RevisionConflict({'profile':'Group preview belongs to a different actor/profile'})
                if self._seals(entry['context'])!=entry['fences'] or self._vector(entry['context'])!=entry['vector']:
                    raise RevisionConflict({'scope':'Sources, annotations or binding changed; reopen the group'})
                self._verify_sources(entry['targets'])
                budget=RetainedBudget(entry['bytes'],OPERATION_BYTES)
                operations=[]
                for target,_,revision in entry['targets']:
                    item=dict(target_kind='epoch',target_uuid=target,profile_uuid=profile,expected_revision=revision,tags_add=[tag])
                    budget.charge(item);operations.append(item)
                with self.service.dj.conn().transaction:
                    replay=self._receipt(operation,actor,request_sha)
                    if replay:return replay
                    self._assert_vector(entry['vector'])
                    if entry['guard']:entry['guard']()
                    if self._seals(entry['context'])!=entry['fences']:raise RevisionConflict({'scope':'Source or binding changed before save'})
                    self._verify_sources(entry['targets'])
                    result=self.annotations._apply_batch_locked(operations,actor,_group_budget=budget)
                    budget.reserve(len(entry['targets'])*128+1024)
                    fingerprints={target:fingerprint for target,fingerprint,_ in entry['targets']}
                    inverse=[]
                    for row in result['annotations']:
                        item=[row['target_uuid'],fingerprints[row['target_uuid']],row['revision']]
                        budget.charge(item);inverse.append(item)
                    receipt=dict(format='rieke-group-annotation-receipt',version=1,operation_uuid=operation,
                        action='add',
                        target_kind='epoch',target_count=len(operations),changed=result['changed'],
                        unchanged=len(operations)-result['changed'],profile_uuid=profile,tag=tag,
                        event_uuid=result['event_uuid'],inverse_targets=inverse,undone_by=None,
                        undo={'kind':'annotation_group','operation_uuid':operation,'count':len(inverse)},scope=entry['scope'])
                    budget.charge(receipt)
                    # Reserve native JSON input and its serialization, including
                    # repeated UUID/fingerprint strings and bounded scope text.
                    budget.reserve(len(inverse)*1024+128*1024)
                    self._save(operation,actor,profile,request_sha,receipt)
                    if self._seals(entry['context'])!=entry['fences']:raise RevisionConflict({'scope':'Source or metadata changed during save'})
                    self._verify_sources(entry['targets'])
                self.annotations._after_batch_commit(result)
                self.selections.pop(selection,None)
                return self._public(receipt)

    def release(self,body,actor):
        if not isinstance(body,dict) or set(body)!={'selection_uuid'}:raise ValueError('Use selection_uuid')
        selection=identity(body['selection_uuid'])
        with self.db_lock:
            entry=self.selections.get(selection)
            if entry and entry['actor']!=actor:raise RevisionConflict({'actor':'Preview belongs to a different actor'})
            return {'released':self.selections.pop(selection,None) is not None}

    def undo(self,forward,body,actor):
        forward=identity(forward);actor=text(actor)
        if not isinstance(body,dict) or set(body)!={'operation_uuid'}:raise ValueError('Use a new operation_uuid for group undo')
        operation=identity(body['operation_uuid']);request_sha=checksum({'kind':'group_undo','forward':forward,**body})
        with self.db_lock:
            replay=self._receipt(operation,actor,request_sha)
            if replay:return replay
            rows=(self.Receipt&{'project_uuid':self.project,'operation_uuid':forward}).to_dicts()
            if not rows or rows[0]['actor']!=actor:raise ValueError('No group operation belongs to this actor')
            record=rows[0];original=record['receipt']
            if original.get('action')!='add':raise ValueError('Choose an original group tag operation to undo')
            targets=original['inverse_targets'];profile=record['profile_uuid']
            context={}
            with self.registration_locks(),context_annotation_locks(self.service,context):
                replay=self._receipt(operation,actor,request_sha)
                if replay:return replay
                if original.get('undone_by'):raise RevisionConflict({'undo':'This group operation was already undone'})
                vector=self._vector(context);fences=self._seals(context)
                self._verify_sources(targets)
                budget=RetainedBudget(maximum=OPERATION_BYTES);budget.charge(record);operations=[]
                for target,_,revision in targets:
                    item=dict(target_kind='epoch',target_uuid=target,profile_uuid=profile,expected_revision=revision,tags_remove=[original['tag']])
                    budget.charge(item);operations.append(item)
                with self.service.dj.conn().transaction:
                    replay=self._receipt(operation,actor,request_sha)
                    if replay:return replay
                    self._assert_vector(vector)
                    current=(self.Receipt&{'project_uuid':self.project,'operation_uuid':forward}).to_dicts()[0]
                    budget.charge(current)
                    if current['receipt'].get('undone_by'):raise RevisionConflict({'undo':'This group operation was already undone'})
                    if self._seals(context)!=fences:raise RevisionConflict({'undo':'Source authority changed before inverse'})
                    self._verify_sources(targets)
                    # Empty changed set is a legitimate no-op inverse.
                    result=(self.annotations._apply_batch_locked(operations,actor,_group_budget=budget) if operations
                            else {'changed':0,'annotations':[],'event_uuid':None})
                    receipt=dict(format='rieke-group-annotation-receipt',version=1,operation_uuid=operation,
                        action='undo',
                        target_kind='epoch',target_count=len(targets),changed=result['changed'],unchanged=len(targets)-result['changed'],
                        profile_uuid=profile,forward_operation_uuid=forward,event_uuid=result['event_uuid'],inverse_targets=[],undone_by=None)
                    budget.charge(receipt)
                    budget.reserve(len(targets)*1024+128*1024)
                    self._save(operation,actor,profile,request_sha,receipt)
                    current['receipt']['undone_by']=operation
                    self.Receipt.update1(current)
                    if self._seals(context)!=fences:raise RevisionConflict({'undo':'Source or metadata changed during inverse'})
                    self._verify_sources(targets)
                self.annotations._after_batch_commit(result)
                return self._public(receipt)


def register_group_annotation_routes(app,service,shared_annotations,db_lock,registration_locks,
                                     revision_guard=None,receipt_table=None):
    from flask import jsonify,request
    if receipt_table is None:receipt_table=group_receipt_table(service.dj)
    groups=AnnotationGroups(service,shared_annotations,receipt_table,db_lock,registration_locks,revision_guard)
    app.extensions['group_annotations']=groups
    def body():
        if request.content_length is not None and request.content_length>64*1024:raise ValueError('Group request exceeds 64 KiB')
        try:return request.get_json()
        except RecursionError as error:raise ValueError('Tree group JSON nesting is too deep') from error
    def actor():return getpass.getuser() or 'Local workspace user'
    @app.post('/api/annotations/group-preview')
    def group_annotation_preview():return jsonify(groups.preview(body(),actor()))
    @app.post('/api/annotations/group')
    def group_annotation_apply():return jsonify(groups.apply(body(),actor()))
    @app.post('/api/annotations/group-preview-release')
    def group_annotation_preview_release():return jsonify(groups.release(body(),actor()))
    @app.post('/api/annotations/group/<operation_uuid>/undo')
    def group_annotation_undo(operation_uuid):return jsonify(groups.undo(operation_uuid,body(),actor()))
