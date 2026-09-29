"""Shared project annotations: exact cell/epoch UUIDs, local profile attribution.

A set belongs to one target and one author. Cell inheritance is an identity join,
never copied rows. Profiles are local attribution, not authenticated accounts.
"""
from __future__ import annotations
import contextlib
import copy
import datetime as dt
import getpass
import hashlib
import time
import uuid
from collections import Counter

from recording_workspace import workspace_tables
from workspace_audit import build_audit_payload
from workspace_curation import RevisionConflict
from workspace_recipes import checksum

MAX_TARGETS = 1000
MAX_OPERATIONS = 2000


def identity(value):
    if not isinstance(value,str): raise ValueError('Expected a UUID string')
    try: return str(uuid.UUID(value))
    except (ValueError,TypeError,AttributeError) as error: raise ValueError('Expected a UUID string') from error


def text(value,maximum=255):
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>maximum or any(ord(c)<32 for c in value):
        raise ValueError(f'Use trimmed printable text of 1–{maximum} characters')
    return value


def tags(value):
    if not isinstance(value,list) or len(value)>100: raise ValueError('Use at most 100 tag strings')
    result=[text(item) for item in value]
    if len(set(result))!=len(result): raise ValueError('Duplicate exact tags are not allowed')
    return result


def annotation_tables(dj):
    schema=dj.Schema('recording_workspace')
    @schema
    class AnnotationProfile(dj.Manual):
        definition='''
        project_uuid: varchar(36)
        profile_uuid: varchar(36)
        ---
        display_name: varchar(120)
        created_at: datetime
        created_by: varchar(255)
        '''
    @schema
    class SharedAnnotation(dj.Manual):
        definition='''
        project_uuid: varchar(36)
        target_kind: enum('cell','epoch')
        target_uuid: varchar(36)
        profile_uuid: varchar(36)
        ---
        tags: json
        author_name: varchar(120)
        revision: int unsigned
        updated_at: datetime
        '''
    return AnnotationProfile,SharedAnnotation


class SharedAnnotations:
    def __init__(self,service,tables=None):
        self.service=service;self.dj=service.dj;self.project_uuid=identity(service.project['project_uuid'])
        if tables is None:
            self.Profile,self.Annotation=annotation_tables(self.dj)
            _,_,self.Event,_=workspace_tables(self.dj)
        else: self.Profile,self.Annotation,self.Event=tables
        self._vocabulary=None

    @property
    def default_profile(self):
        name=getpass.getuser() or 'Local workspace user'
        return {'profile_uuid':str(uuid.uuid5(uuid.UUID(self.project_uuid),'local-os-profile:'+name)),
                'display_name':name,'local':True}

    @contextlib.contextmanager
    def lock(self):
        connection=self.dj.conn()
        name=hashlib.sha256((self.project_uuid+'shared-annotations').encode()).hexdigest()
        if connection.query(f"SELECT GET_LOCK('{name}', 10)").fetchone()[0]!=1:
            raise RuntimeError('Another shared annotation update is running; retry shortly')
        try: yield
        finally:
            with contextlib.suppress(Exception):connection.query(f"SELECT RELEASE_LOCK('{name}')")

    def _event(self,action,actor,payload):
        event=str(uuid.uuid4())
        self.Event.insert1({'event_uuid':event,'project_uuid':self.project_uuid,
            'occurred_at':dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),'actor':text(actor),
            'action':action,'payload':build_audit_payload(action,actor,payload,
                context={'project_uuid':self.project_uuid})})
        return event

    def list_profiles(self):
        rows=(self.Profile&{'project_uuid':self.project_uuid}).to_dicts()
        profiles={row['profile_uuid']:{'profile_uuid':row['profile_uuid'],'display_name':row['display_name'],'local':True} for row in rows}
        default=self.default_profile;profiles.setdefault(default['profile_uuid'],default)
        return {'profiles':sorted(profiles.values(),key=lambda p:(p['display_name'].casefold(),p['profile_uuid'])),
                'default_profile_uuid':default['profile_uuid'],'attribution':'local_profile_not_authentication'}

    def _ensure_profiles(self,profiles,actor,pending=None):
        if not isinstance(profiles,list) or len(profiles)>100:raise ValueError('Use at most 100 profile definitions')
        existing={row['profile_uuid']:row for row in (self.Profile&{'project_uuid':self.project_uuid}).to_dicts()}
        seen=set()
        for profile in profiles:
            if not isinstance(profile,dict) or set(profile)-{'profile_uuid','display_name'}:raise ValueError('Invalid profile definition')
            key=identity(profile.get('profile_uuid'));name=text(profile.get('display_name'),120)
            if key in seen:raise ValueError('Duplicate profile identity')
            seen.add(key)
            if key in existing:
                if existing[key]['display_name']!=name:raise ValueError('Profile UUID already has another name; explicitly map the author before import')
                continue
            row={'project_uuid':self.project_uuid,'profile_uuid':key,'display_name':name,
                 'created_at':dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),'created_by':actor}
            if pending is None:self.Profile.insert1(row)
            else:pending.append(row)
            existing[key]=row
        return existing

    def create_profile(self,name,actor):
        name=text(name,120);actor=text(actor)
        with self.lock(),self.dj.conn().transaction:
            existing=self.list_profiles()['profiles']
            for row in existing:
                if row['display_name'].casefold()==name.casefold():return row
            key=str(uuid.uuid4())
            self._ensure_profiles([{'profile_uuid':key,'display_name':name}],actor)
            self._event('annotation_profile_created',actor,{'profile_uuid':key,'display_name':name,'attribution':'local_profile_not_authentication'})
        return {'profile_uuid':key,'display_name':name,'local':True}

    def _scope(self,kind,ids,maximum=MAX_TARGETS):
        ready=getattr(self.service,'_ready',None)
        if ready:ready()
        if kind not in ('cell','epoch'):raise ValueError('Annotation target_kind must be cell or epoch')
        if not isinstance(ids,list) or not 1<=len(ids)<=maximum:raise ValueError(f'Select 1–{maximum} explicit target UUIDs')
        ids=[identity(value) for value in ids]
        if len(set(ids))!=len(ids):raise ValueError('Duplicate annotation target')
        known=self.service.cells if kind=='cell' else self.service.rows
        if set(ids)-known.keys():raise ValueError('Annotation target is outside this registered project')
        return ids

    def _rows(self,kind=None,ids=None):
        relation=self.Annotation&{'project_uuid':self.project_uuid}
        if kind is not None:relation=relation&{'target_kind':kind}
        if ids is not None:
            if not ids:return []
            if len(ids)<=250:relation=relation&[{'target_uuid':key} for key in ids]
        result=relation.to_dicts()
        if ids is not None:
            allowed=set(ids);result=[row for row in result if row['target_uuid'] in allowed]
        return result

    @staticmethod
    def _chips(row):
        values=tags(row['tags'])
        identity(row['profile_uuid']);identity(row['target_uuid']);text(row['author_name'],120)
        if type(row['revision']) is not int or row['revision']<1:raise ValueError('Invalid shared annotation revision')
        return [{'tag':tag,'profile_uuid':row['profile_uuid'],'author_name':row['author_name'],
                 'target_kind':row['target_kind'],'target_uuid':row['target_uuid'],'revision':row['revision']}
                for tag in sorted(values)]

    def read_targets(self,kind,ids):
        ids=self._scope(kind,ids)
        output={key:{'target_kind':kind,'target_uuid':key,'tags':[],'revisions':{}} for key in ids}
        for row in self._rows(kind,ids):
            output[row['target_uuid']]['tags'].extend(self._chips(row))
            output[row['target_uuid']]['revisions'][row['profile_uuid']]=row['revision']
        for item in output.values():item['tags'].sort(key=lambda r:(r['tag'],r['author_name'],r['profile_uuid']))
        return output

    def for_epochs(self,rows):
        if not rows:return {}
        ids=[r['epoch_uuid'] for r in rows];cells=sorted({r['cell_uuid'] for r in rows})
        if len(set(ids))!=len(ids) or any(key not in self.service.rows for key in ids):raise ValueError('Expected unique registered epoch identities')
        if any(row['cell_uuid']!=self.service.rows[row['epoch_uuid']]['cell_uuid'] for row in rows):raise ValueError('Epoch/cell identity linkage does not match this project')
        # Summary/export calls may cover whole projects. No per-epoch SQL reads.
        direct={key:{'tags':[],'revisions':{}} for key in ids};inherited={key:{'tags':[],'revisions':{}} for key in cells}
        for kind,keys,target in [('epoch',ids,direct),('cell',cells,inherited)]:
            for row in self._rows(kind,keys):
                item=target[row['target_uuid']];item['tags'].extend(self._chips(row));item['revisions'][row['profile_uuid']]=row['revision']
        for scope in (direct,inherited):
            for item in scope.values():item['tags'].sort(key=lambda r:(r['tag'],r['author_name'],r['profile_uuid']))
        result={}
        for row in rows:
            cell=inherited[row['cell_uuid']];epoch=direct[row['epoch_uuid']]
            result[row['epoch_uuid']]={'epoch_uuid':row['epoch_uuid'],'cell_uuid':row['cell_uuid'],
                'cell_tags':copy.deepcopy(cell['tags']),'epoch_tags':copy.deepcopy(epoch['tags']),
                'effective_tags':copy.deepcopy(cell['tags']+epoch['tags']),
                'revisions':{'cell':dict(cell['revisions']),'epoch':dict(epoch['revisions'])}}
        return result

    def summary(self,rows):
        rows=list(rows);ids={row['epoch_uuid'] for row in rows};cells={row['cell_uuid'] for row in rows}
        cell_epochs={key:set() for key in cells};epoch_cell={row['epoch_uuid']:row['cell_uuid'] for row in rows}
        for row in rows:cell_epochs[row['cell_uuid']].add(row['epoch_uuid'])
        tagged_cells=set();tagged_epochs=set();by_tag={}
        for row in self._rows():
            if not row['tags']:continue
            if row['target_kind']=='cell' and row['target_uuid'] in cells:
                tagged_cells.add(row['target_uuid']);affected=cell_epochs[row['target_uuid']]
            elif row['target_kind']=='epoch' and row['target_uuid'] in ids:affected={row['target_uuid']}
            else:continue
            tagged_epochs.update(affected)
            for tag in tags(row['tags']):by_tag.setdefault(tag,set()).update(affected)
        tag_counts=[{'tag':tag,'epoch_count':len(members),'cell_count':len({epoch_cell[key] for key in members})} for tag,members in by_tag.items()]
        tag_counts.sort(key=lambda item:(-item['epoch_count'],item['tag'].casefold(),item['tag']))
        return {'shared_tagged_cells':len(tagged_cells),'shared_tagged_epochs':len(tagged_epochs),
                'tags':tag_counts[:12],'total_tags':len(tag_counts),'truncated':len(tag_counts)>12}

    def snapshot(self):
        records=[]
        for row in self._rows():
            known=self.service.cells if row['target_kind']=='cell' else self.service.rows
            if row['target_uuid'] not in known:raise ValueError('Shared annotation target is no longer registered')
            self._chips(row)
            records.append({key:copy.deepcopy(row[key]) for key in ('target_kind','target_uuid','profile_uuid','author_name','revision','tags')})
        records.sort(key=lambda r:(r['target_kind'],r['target_uuid'],r['profile_uuid']))
        return {'version':1,'project_uuid':self.project_uuid,'revision':checksum({'project_uuid':self.project_uuid,'records':records}),'records':records,
                'semantics':'cell tags inherit by cell UUID; epoch tags are direct; protocol curation is separate'}

    def update(self,kind,ids,profile_uuid,changes,expected_revisions,actor):
        ids=self._scope(kind,ids)
        if not isinstance(changes,dict) or set(changes)-{'tags_add','tags_remove'}:raise ValueError('Use tags_add and tags_remove only')
        if not isinstance(expected_revisions,dict) or set(expected_revisions)!=set(ids):raise ValueError('Expected revisions must cover exactly the selected targets')
        operations=[dict(target_kind=kind,target_uuid=key,profile_uuid=profile_uuid,
                         expected_revision=expected_revisions[key],**changes) for key in ids]
        result=self.apply_batch(operations,actor)
        result['targets']=self.read_targets(kind,ids)
        return result

    def apply_batch(self,operations,actor,profiles=None,audit_context=None):
        actor=text(actor)
        if not isinstance(operations,list) or not 1<=len(operations)<=MAX_OPERATIONS:raise ValueError('Use 1–2000 annotation operations')
        if profiles is not None and not isinstance(profiles,list):raise ValueError('Profiles must be an array')
        parsed=[];seen=set()
        for operation in operations:
            if not isinstance(operation,dict) or set(operation)-{'target_kind','target_uuid','profile_uuid','tags_add','tags_remove','expected_revision'}:raise ValueError('Invalid annotation operation')
            kind=operation.get('target_kind');target=self._scope(kind,[operation.get('target_uuid')])[0]
            author=identity(operation.get('profile_uuid'));revision=operation.get('expected_revision')
            if type(revision) is not int or revision<0:raise ValueError('Expected revision must be a nonnegative integer')
            add=tags(operation.get('tags_add',[]));remove=tags(operation.get('tags_remove',[]))
            if set(add)&set(remove):raise ValueError('Cannot add and remove the same tag')
            key=(kind,target,author)
            if key in seen:raise ValueError('Duplicate target/author operation')
            seen.add(key);parsed.append((key,revision,add,remove))
        before=[];after=[];changed=0;event=None
        with self.lock(),self.dj.conn().transaction:
            incoming=list(profiles or [])
            if any(not isinstance(p,dict) for p in incoming):raise ValueError('Invalid profile definition')
            default=self.default_profile
            if any(key[2]==default['profile_uuid'] for key,_,_,_ in parsed) and not any(p.get('profile_uuid')==default['profile_uuid'] for p in incoming):
                incoming.append({k:default[k] for k in ('profile_uuid','display_name')})
            pending_profiles=[]
            authors=self._ensure_profiles(incoming,actor,pending_profiles)
            saved={(row['target_kind'],row['target_uuid'],row['profile_uuid']):row for row in self._rows()}
            for key,expected,add,remove in parsed:
                if key[2] not in authors:raise ValueError('Select an existing local annotation profile')
                old=saved.get(key);revision=old['revision'] if old else 0
                if revision!=expected:raise RevisionConflict({'target_kind':key[0],'target_uuid':key[1],'profile_uuid':key[2],'revision':revision})
                previous=tags(old['tags']) if old else []
                current=sorted((set(previous)|set(add))-set(remove))
                if len(current)>100:raise ValueError('A target/author may have at most 100 current tags')
                if set(previous)==set(current):continue
                row={'project_uuid':self.project_uuid,'target_kind':key[0],'target_uuid':key[1],
                     'profile_uuid':key[2],'tags':current,'author_name':authors[key[2]]['display_name'],
                     'revision':revision+1,'updated_at':dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)}
                before.append({**{k:row[k] for k in ('target_kind','target_uuid','profile_uuid','author_name')},'revision':revision,'tags':previous})
                after.append({k:row[k] for k in ('target_kind','target_uuid','profile_uuid','author_name','revision','tags')})
                if old:self.Annotation.update1(row)
                else:self.Annotation.insert1(row)
                changed+=1
            if changed:
                used_authors={row['profile_uuid'] for row in after}
                for profile in pending_profiles:
                    if profile['profile_uuid'] in used_authors:self.Profile.insert1(profile)
                event=self._event('shared_annotations_updated',actor,{'before':before,'after':after,
                    'target_count':changed,'attribution':'client_selected_local_profile',
                    **({'exchange':audit_context} if audit_context else {})})
        if changed:self._vocabulary=None
        return {'changed':changed,'event_uuid':event,'annotations':after}

    def suggestions(self,query='',limit=30):
        if not isinstance(query,str) or len(query)>255 or type(limit) is not int or not 1<=limit<=100:raise ValueError('Use a tag prefix up to 255 characters and limit 1–100')
        if self._vocabulary is None or time.monotonic()>=self._vocabulary[0]:
            values={}
            for row in self._rows():
                for tag in tags(row['tags']):
                    current=values.setdefault(tag,{'targets':set(),'authors':{}})
                    current['targets'].add((row['target_kind'],row['target_uuid']))
                    current['authors'][row['profile_uuid']]=row['author_name']
            self._vocabulary=(time.monotonic()+2,values)
        selected=[(tag,value) for tag,value in self._vocabulary[1].items() if tag.casefold().startswith(query.strip().casefold())]
        selected.sort(key=lambda pair:(-len(pair[1]['targets']),pair[0].casefold(),pair[0]))
        return {'tags':[{'tag':tag,'count':len(value['targets']),'authors':[{'profile_uuid':key,'display_name':name} for key,name in sorted(value['authors'].items())]} for tag,value in selected[:limit]],
                'scope':'project_shared_annotations','query':query,'total':len(selected),'limit':limit,
                'count_unit':'distinct_annotation_targets','match':'case_insensitive_prefix','has_more':len(selected)>limit}


def register_annotation_routes(app,service,store,db_lock):
    from flask import jsonify,request
    def body(allowed):
        if request.content_length is not None and request.content_length>1024*1024:raise ValueError('Annotation request exceeds 1 MiB')
        value=request.get_json(silent=True)
        if not isinstance(value,dict) or set(value)-allowed:raise ValueError('Invalid annotation request')
        return value
    def actor():return getpass.getuser() or 'Local workspace user'
    @app.get('/api/annotation-profiles')
    def annotation_profiles():
        if request.args:raise ValueError('Profile listing accepts no query filters')
        with db_lock:return jsonify(store.list_profiles())
    @app.post('/api/annotation-profiles')
    def annotation_profile_create():
        value=body({'display_name'})
        with db_lock:return jsonify(store.create_profile(value.get('display_name'),actor())),201
    @app.get('/api/annotation-tags')
    def annotation_suggestions():
        if set(request.args)-{'q','limit'} or any(len(v)!=1 for _,v in request.args.lists()):raise ValueError('Invalid tag suggestion query')
        raw=request.args.get('limit','30')
        if not raw.isascii() or not raw.isdecimal() or len(raw)>3:raise ValueError('Suggestion limit must be an integer 1–100')
        with db_lock:return jsonify(store.suggestions(request.args.get('q',''),int(raw)))
    @app.post('/api/annotations/read')
    def annotation_batch_read():
        value=body({'target_kind','target_uuids'})
        with db_lock:
            result={'targets':store.read_targets(value.get('target_kind'),value.get('target_uuids'))}
            if value.get('target_kind')=='epoch':
                result['annotations']=store.for_epochs([service.rows[key] for key in result['targets']])
            return jsonify(result)
    @app.post('/api/annotations')
    def annotation_update():
        value=body({'target_kind','target_uuids','profile_uuid','tags_add','tags_remove','expected_revisions'})
        with db_lock:return jsonify(store.update(value.get('target_kind'),value.get('target_uuids'),value.get('profile_uuid'),
            {key:value[key] for key in ('tags_add','tags_remove') if key in value},value.get('expected_revisions'),actor()))
    @app.get('/api/cells/<cell_uuid>/annotations')
    def annotation_cell(cell_uuid):
        if request.args:raise ValueError('Cell annotations use the complete registered cell')
        with db_lock:
            result=store.read_targets('cell',[cell_uuid])[identity(cell_uuid)]
            result['epoch_count']=sum(row['cell_uuid']==identity(cell_uuid) for row in service.rows.values())
            return jsonify(result)
    @app.get('/api/epochs/<epoch_uuid>/annotations')
    def annotation_epoch(epoch_uuid):
        if request.args:raise ValueError('Epoch annotations are independent of protocol filters')
        with db_lock:
            key=store._scope('epoch',[epoch_uuid])[0];row=service.rows[key]
            result=store.for_epochs([row])[key]
            result['cell_epoch_count']=sum(item['cell_uuid']==row['cell_uuid'] for item in service.rows.values())
            return jsonify(result)
