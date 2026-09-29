"""Explicit protocol-scoped tag predicates; raw acquisition indexes stay immutable."""
from __future__ import annotations
import copy
import contextlib
import hashlib
import uuid
from workspace_predicates import MAX_NODES, validate, matches, predicate_catalog
from workspace_recipes import checksum
from workspace_tree import value_key, value_order, value_label

PREFIX = 'curation/'
SHARED_FIELDS = {
    'annotations/cell/tags': 'Cell tags',
    'annotations/epoch/tags': 'Epoch tags',
    'annotations/effective/tags': 'Effective shared tags',
    'annotations/authors': 'Shared tag authors',
    'annotations/author_uuids': 'Shared tag author UUIDs',
}


def referenced_fields(predicate):
    """Bounded discovery only; the regular validator checks the full AST."""
    result=set();pending=[predicate];visited=0
    while pending and visited<=MAX_NODES:
        node=pending.pop();visited+=1
        if not isinstance(node,dict): continue
        key=node.get('field')
        if isinstance(key,str) and key.startswith((PREFIX, 'annotations/')): result.add(key)
        if 'not' in node: pending.append(node['not'])
        for logic in ('all','any'):
            if isinstance(node.get(logic),list): pending.extend(node[logic][:MAX_NODES+1])
    return result


@contextlib.contextmanager
def annotation_locks(service, predicate, extra_protocols=()):
    """Serialize annotation evidence with curation writes across processes.

    Include destination protocols before entering so every multi-scope operation
    acquires locks in the same order. The caller owns its SQL transaction.
    """
    definitions={field['id']:field for field in TagPredicates(service).definitions()}
    fields=referenced_fields(predicate)
    if fields-definitions.keys():
        raise ValueError('Choose tags from a protocol workspace in this project')
    protocols={definitions[field]['annotation_scope']['protocol_uuid'] for field in fields
               if definitions[field]['annotation_scope']['kind']=='protocol_curation'}
    for identity in extra_protocols:
        if not isinstance(identity,str): raise ValueError('Expected protocol UUID for annotation lock')
        protocols.add(str(uuid.UUID(identity)))
    shared=getattr(service,'shared_annotations',None)
    # Always cover shared export snapshots as well as explicit shared predicates.
    shared_guard=shared.lock() if shared else contextlib.nullcontext()
    with shared_guard:
        with _protocol_locks(service,protocols):
            yield


@contextlib.contextmanager
def _protocol_locks(service,protocols):
    if not protocols:
        yield
        return
    connection=service.dj.conn();acquired=[]
    try:
        for protocol in sorted(protocols):
            lock=hashlib.sha256((service.project['project_uuid']+protocol).encode()).hexdigest()
            if connection.query(f"SELECT GET_LOCK('{lock}', 10)").fetchone()[0]!=1:
                raise RuntimeError('Another protocol annotation update is running; retry shortly')
            acquired.append(lock)
        yield
    finally:
        for lock in reversed(acquired):
            with contextlib.suppress(Exception):
                connection.query(f"SELECT RELEASE_LOCK('{lock}')")


class TagPredicates:
    def __init__(self,service): self.service=service

    def definitions(self):
        result=[]
        if getattr(self.service,'annotation_provider',None):
            result=[dict(id=f'curation/{identity}/tags',label='Tags · '+entry['definition']['name'],
                     path=f'curation.{identity}.tags',category='Protocol tags',
                     annotation_scope={'kind':'protocol_curation','protocol_uuid':identity},
                     description='Tags recorded in this protocol workspace only; imported keywords are separate. Untagged epochs have an empty array.')
                for identity,entry in sorted(self.service.protocols.items())]
        if getattr(self.service,'shared_annotations',None):
            result += [dict(id=field,label=label,path=field.replace('/','.'),category='Shared annotations',
                        annotation_scope={'kind':'shared_annotations'},
                        description='Shared project annotations joined by exact cell/epoch UUID. Local authors are attribution, not authentication; empty arrays mean no tags.')
                       for field,label in SHARED_FIELDS.items()]
        return result

    def snapshot(self,fields):
        definitions={field['id']:field for field in self.definitions()}
        if fields-definitions.keys(): raise ValueError('Choose tags from a protocol workspace in this project')
        protocols=[];states={}
        fingerprints=self.service._fingerprints
        universe=checksum(sorted(fingerprints))
        for field in sorted(fields):
            if field in SHARED_FIELDS: continue
            protocol=definitions[field]['annotation_scope']['protocol_uuid']
            current=self.service.annotation_provider(protocol,dict(fingerprints))
            if not isinstance(current,dict) or current.keys()-fingerprints.keys():
                raise ValueError('Protocol tag provider returned an invalid epoch scope')
            records=[];values={}
            for identity in fingerprints:
                state=current.get(identity,{})
                tags=state.get('tags',[]);revision=state.get('revision',0)
                if (not isinstance(tags,list) or any(not isinstance(tag,str) or not tag or tag!=tag.strip() or len(tag)>255 for tag in tags)
                        or len(set(tags))!=len(tags) or type(revision) is not int or revision<0):
                    raise ValueError('Invalid saved protocol tag annotation')
                tags=sorted(tags)
                if tags: values[identity]=tags
                if revision or tags: records.append(dict(epoch_uuid=identity,revision=revision,tags=tags))
            records.sort(key=lambda row:row['epoch_uuid'])
            revision=checksum({'registered_epoch_universe':universe,'records':records})
            protocols.append(dict(protocol_uuid=protocol,field=field,revision=revision,records=records))
            states[field]=values
        evidence={'version':1,'revision':checksum([(p['protocol_uuid'],p['revision']) for p in protocols]),'protocols':protocols}
        shared_fields=fields & SHARED_FIELDS.keys()
        if shared_fields:
            snapshot=self.service.shared_annotations.snapshot()
            cell_records={};epoch_records={}
            for row in snapshot['records']:
                target=cell_records if row['target_kind']=='cell' else epoch_records
                target.setdefault(row['target_uuid'],[]).append(row)
            for field in shared_fields: states[field]={}
            for key,row in self.service.rows.items():
                cell=cell_records.get(row['cell_uuid'],[]);epoch=epoch_records.get(key,[]);effective=cell+epoch
                values={'annotations/cell/tags':sorted({tag for r in cell for tag in r['tags']}),
                        'annotations/epoch/tags':sorted({tag for r in epoch for tag in r['tags']}),
                        'annotations/effective/tags':sorted({tag for r in effective for tag in r['tags']}),
                        'annotations/authors':sorted({r['author_name'] for r in effective if r['tags']}),
                        'annotations/author_uuids':sorted({r['profile_uuid'] for r in effective if r['tags']})}
                for field in shared_fields:
                    if values[field]:states[field][key]=values[field]
            evidence.update(version=2,shared=snapshot,fields=sorted(shared_fields))
            evidence['revision']=checksum({'protocols':[(p['protocol_uuid'],p['revision']) for p in protocols],
                'shared_revision':snapshot['revision'],'shared_fields':sorted(shared_fields),
                'registered_cell_links':sorted((key,row['cell_uuid']) for key,row in self.service.rows.items())})
        return states,evidence

    def catalog_fields(self,ids):
        definitions=self.definitions()
        if not definitions: return []
        states,_=self.snapshot({field['id'] for field in definitions})
        fields=[]
        for definition in definitions:
            key=definition['id'];values={identity:{key:states[key].get(identity,[])} for identity in ids}
            distinct={value_key(current[key]):current[key] for current in values.values()}
            examples=[value_label(value)[:160] for value in sorted(distinct.values(),key=value_order)[:5]]
            field={**definition,'count':len(ids),'distinct_count':len(distinct),'recorded_distinct_count':len(distinct),
                   'missing_count':0,'null_count':0,'varying':len(distinct)>1,'examples':examples,
                   'grouping_role':'annotation','grouping_priority':100,'varies_within_cell':False,
                   'suggested_rank':None,'suggestion_reason':'','high_cardinality':len(distinct)>24}
            field=predicate_catalog({'fields':[field]},values)['fields'][0]
            field.update(active_types=field['types'],types=['array'],types_scope='project_annotations',element_types=['string'])
            fields.append(field)
        return fields

    def match(self,predicate,ids):
        fields=referenced_fields(predicate)
        if not fields:
            validated,matched=self.service._match_metadata_predicate(predicate,ids)
            return validated,matched,None
        states,evidence=self.snapshot(fields)
        registered,_=self.service._registered_tree_fields()
        definitions=[field for field in registered['fields'] if not field['id'].startswith('joint/')]+self.definitions()
        # This pass enforces the entire AST's limits/shape and tag literal types.
        # Raw metadata subtrees below retain their exact registered-type validator.
        validated=validate(predicate,{'fields':definitions},{field:{field:['']} for field in fields})
        universe=set(ids)
        def walk(node):
            if not referenced_fields(node):
                return set(self.service._match_metadata_predicate(node,ids)[1])
            if 'all' in node:
                result=set(universe)
                for child in node['all']: result.intersection_update(walk(child))
                return result
            if 'any' in node:
                result=set()
                for child in node['any']: result.update(walk(child))
                return result
            if 'not' in node: return universe-walk(node['not'])
            key=node['field']
            return {identity for identity in ids if matches(node,{key:states[key].get(identity,[])})}
        matched=walk(validated)
        return validated,[identity for identity in ids if identity in matched],copy.deepcopy(evidence)
