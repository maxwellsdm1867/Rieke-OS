"""Explicit protocol-scoped tag predicates; raw acquisition indexes stay immutable."""
from __future__ import annotations
import copy
import contextlib
import hashlib
import uuid
from collections import OrderedDict
from disco.navigation.predicates import MAX_NODES, validate, matches, predicate_catalog
from disco.workbench.recipes import checksum
from disco.navigation.tree import value_key, value_order, value_label
from disco.navigation.tag_time_filter import TIME_FIELDS, TIME_LABELS, samples, check_time_nodes

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


MEMO_ENTRIES=4


class _Publication:
    """Structures derived from one metadata publication, built on first use."""
    def __init__(self,service):
        self.service=service;self._universe=None;self._cells=None

    def universe(self):
        if self._universe is None:self._universe=checksum(sorted(self.service._fingerprints))
        return self._universe

    def cell_epochs(self,cell):
        if self._cells is None:
            cells={}
            for key,row in self.service.rows.items():cells.setdefault(row['cell_uuid'],[]).append(key)
            self._cells=cells
        return self._cells.get(cell,())

    def cell_links(self):
        return sorted((key,row['cell_uuid']) for key,row in self.service.rows.items())


class _Entry:
    """One generation's tag states, evidence and lazily inverted values."""
    def __init__(self,states,evidence):
        self.states,self.evidence=states,evidence;self._groups={}

    def groups(self,field):
        """Epochs grouped by exact tag array; untagged epochs are implicit."""
        found=self._groups.get(field)
        if found is None:
            grouped={}
            for identity,value in self.states[field].items():
                grouped.setdefault(tuple(value),(value,set()))[1].add(identity)
            found=self._groups[field]=([(value,frozenset(members)) for value,members in grouped.values()],
                                       frozenset(self.states[field]))
        return found

    def leaf(self,node,universe):
        """Exact `matches` per distinct value instead of per epoch."""
        key=node['field'];groups,tagged=self.groups(key)
        result=set()
        for value,members in groups:
            if matches(node,{key:value}):result.update(members)
        result.intersection_update(universe)
        if matches(node,{key:[]}):result.update(universe-tagged)
        return result


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
            # Tag-time rules are composed by the tag filter, not listed as
            # editor fields: their value is a {tag, after, before} object.
            result += [dict(id=field,label=label,path=field.replace('/','.'),category='Shared annotations',
                        annotation_scope={'kind':'shared_annotations'},value_shape='tag_time',
                        description='Per-tag added time (UTC) of shared annotations; contains {tag, after, before}. Backfilled times may be approximate.')
                       for field,label in TIME_LABELS.items()]
        return result

    def _witness(self,fields):
        """Generation witness for exactly these annotation fields; None recomputes.

        Reuses the predicate-catalog witness (verified StateGenerationAuthority,
        native curation/shared readers, publication, index/typed generations,
        source scope and row/cell identities). Tag times share the shared scope
        generation: time rows are written in the same transaction as their tags.
        """
        provider=getattr(self.service,'_annotation_catalog_generation',None)
        if provider is None:return None
        witness=provider(self.service.source_scope()['revision'])
        if witness is None:return None
        common,tokens=witness
        shared=tokens.get(next(iter(SHARED_FIELDS)))
        key=[]
        for field in sorted(fields):
            token=shared if field in TIME_FIELDS else tokens.get(field)
            if token is None:return None
            key.append((field,token))
        return common,tuple(key)

    def _derived(self,common):
        """Per-publication structures (universe digest, cell membership)."""
        current=getattr(self.service,'_tag_predicate_publication',None)
        if common is None:return _Publication(self.service)
        if current is None or current[0]!=common:
            current=self.service._tag_predicate_publication=(common,_Publication(self.service))
        return current[1]

    def _entry(self,fields):
        """States/evidence for these fields, memoized per verified generation.

        A hit performs only witness token reads. Entries are stored only when the
        witness is unchanged after the build; an unavailable witness always
        recomputes, exactly as before.
        """
        fields=frozenset(fields)
        witness=self._witness(fields)
        memo=getattr(self.service,'_tag_predicate_memo',None)
        if witness is not None and memo is not None and witness in memo:
            memo.move_to_end(witness)
            return memo[witness]
        entry=self._build(fields,self._derived(witness[0] if witness else None))
        if witness is not None and self._witness(fields)==witness:
            if memo is None:memo=self.service._tag_predicate_memo=OrderedDict()
            memo[witness]=entry
            while len(memo)>MEMO_ENTRIES:memo.popitem(last=False)
        return entry

    def snapshot(self,fields):
        if isinstance(fields, (set, frozenset)) and not fields:
            return {}, {'version': 1, 'revision': checksum([]), 'protocols': []}
        entry=self._entry(fields)
        # States are shared read-only lookups (tagged epochs only); evidence is
        # an independent copy because callers persist it in recipes.
        return dict(entry.states),copy.deepcopy(entry.evidence)

    def _build(self,fields,derived):
        definitions={field['id']:field for field in self.definitions()}
        if fields-definitions.keys(): raise ValueError('Choose tags from a protocol workspace in this project')
        protocols=[];states={}
        fingerprints=self.service._fingerprints
        for field in sorted(fields):
            if field in SHARED_FIELDS or field in TIME_FIELDS: continue
            protocol=definitions[field]['annotation_scope']['protocol_uuid']
            current=self.service.annotation_provider(protocol,dict(fingerprints))
            if not isinstance(current,dict) or current.keys()-fingerprints.keys():
                raise ValueError('Protocol tag provider returned an invalid epoch scope')
            records=[];values={}
            # Absent epochs are untagged revision-0 defaults: no record, no value.
            for identity,state in current.items():
                tags=state.get('tags',[]);revision=state.get('revision',0)
                if (not isinstance(tags,list) or any(not isinstance(tag,str) or not tag or tag!=tag.strip() or len(tag)>255 for tag in tags)
                        or len(set(tags))!=len(tags) or type(revision) is not int or revision<0):
                    raise ValueError('Invalid saved protocol tag annotation')
                tags=sorted(tags)
                if tags: values[identity]=tags
                if revision or tags: records.append(dict(epoch_uuid=identity,revision=revision,tags=tags))
            records.sort(key=lambda row:row['epoch_uuid'])
            revision=checksum({'registered_epoch_universe':derived.universe(),'records':records})
            protocols.append(dict(protocol_uuid=protocol,field=field,revision=revision,records=records))
            states[field]=values
        evidence={'version':1,'revision':checksum([(p['protocol_uuid'],p['revision']) for p in protocols]),'protocols':protocols}
        shared_fields=fields & SHARED_FIELDS.keys()
        time_fields=fields & TIME_FIELDS.keys()
        if shared_fields or time_fields:
            snapshot=self.service.shared_annotations.snapshot()
            cell_records={};epoch_records={}
            for row in snapshot['records']:
                target=cell_records if row['target_kind']=='cell' else epoch_records
                target.setdefault(row['target_uuid'],[]).append(row)
            for field in shared_fields: states[field]={}
            if shared_fields:
                rows=self.service.rows
                def values_for(cell,epoch):
                    effective=cell+epoch
                    return {'annotations/cell/tags':sorted({tag for r in cell for tag in r['tags']}),
                            'annotations/epoch/tags':sorted({tag for r in epoch for tag in r['tags']}),
                            'annotations/effective/tags':sorted({tag for r in effective for tag in r['tags']}),
                            'annotations/authors':sorted({r['author_name'] for r in effective if r['tags']}),
                            'annotations/author_uuids':sorted({r['profile_uuid'] for r in effective if r['tags']})}
                # Only epochs with direct records or a recorded cell can carry a
                # non-empty value; every other epoch is the empty array. Epochs
                # that share a cell and have no direct record share one value.
                affected={}
                for cell,records in cell_records.items():
                    inherited=values_for(records,[])
                    for key in derived.cell_epochs(cell):
                        if key not in epoch_records:affected[key]=inherited
                for key,records in epoch_records.items():
                    row=rows.get(key)
                    if row is None:continue
                    affected[key]=values_for(cell_records.get(row['cell_uuid'],[]),records)
                for key,values in affected.items():
                    for field in shared_fields:
                        if values[field]:states[field][key]=values[field]
            evidence.update(version=2,shared=snapshot,fields=sorted(shared_fields|time_fields))
            evidence['revision']=checksum({'protocols':[(p['protocol_uuid'],p['revision']) for p in protocols],
                'shared_revision':snapshot['revision'],'shared_fields':sorted(shared_fields|time_fields),
                'registered_cell_links':derived.cell_links()})
        entry=_Entry(states,evidence);entry.publication=derived
        return entry

    def catalog_fields(self,ids,only=None):
        definitions=[field for field in self.definitions() if field.get('value_shape')!='tag_time']
        if only is not None:definitions=[field for field in definitions if field['id'] in only]
        if not definitions: return []
        all_fields={field['id'] for field in definitions};indexed={}
        shared=getattr(self.service,'shared_annotations',None)
        if shared is not None and hasattr(shared,'catalog_fields'):
            indexed=shared.catalog_fields([self.service.rows[key] for key in ids],all_fields & SHARED_FIELDS.keys()) or {}
        remaining=all_fields-indexed.keys()
        states=self._entry(remaining).states if remaining else {}
        fields=[]
        for definition in definitions:
            if definition['id'] in indexed:
                fields.append({**definition,**indexed[definition['id']]});continue
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
        entry=self._entry(fields)
        registered,_=self.service._registered_tree_fields()
        definitions=[field for field in registered['fields'] if not field['id'].startswith('joint/')]+self.definitions()
        # This pass enforces the entire AST's limits/shape and tag literal types.
        # Raw metadata subtrees below retain their exact registered-type validator.
        validated=check_time_nodes(validate(predicate,{'fields':definitions},samples(fields,[''])))
        ids=ids if isinstance(ids,(list,tuple)) else list(ids)
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
            if node['field'] in TIME_FIELDS: return self._time_leaf(node,ids,universe,entry)
            return entry.leaf(node,universe)
        matched=walk(validated)
        return validated,[identity for identity in ids if identity in matched],copy.deepcopy(entry.evidence)

    def _time_leaf(self,node,ids,universe=None,entry=None):
        """Validated per-tag times; canonical chips when no time table exists."""
        from disco.navigation.tag_time_filter import condition, in_window, chip_matches
        shared=self.service.shared_annotations
        value=condition(node['value']);kinds=TIME_FIELDS[node['field']]
        universe=set(ids) if universe is None else universe
        from disco.decisions.tag_times import tag_time_targets
        found=tag_time_targets(shared,value['tag']) if hasattr(shared,'TagTime') else None
        if found is None:
            found=self._approximate_times(shared,value['tag'],universe,
                entry.publication if entry is not None else _Publication(self.service))
        if found is None:
            annotations=shared.for_epochs([self.service.rows[key] for key in ids])
            return {key for key in ids if chip_matches(node,annotations.get(key))}
        epochs=set();cells=set()
        for kind,target,added_at in found:
            if kind in kinds and in_window(added_at,value):(epochs if kind=='epoch' else cells).add(target)
        derived=entry.publication if entry is not None else _Publication(self.service)
        result=epochs&universe
        for cell in cells:
            result.update(key for key in derived.cell_epochs(cell) if key in universe)
        return result

    def _approximate_times(self,shared,tag,universe,derived):
        """Chip times for a store without a time table, read from its records.

        Equivalent to hydrating every scoped epoch's chips: a chip's time is the
        record's update time (approximate). Only records whose target is in
        scope (an epoch in the universe or a cell with an epoch in it) are read
        as chips, and each is validated exactly as hydration would.
        """
        from disco.decisions.annotations import SharedAnnotations
        if type(shared) is not SharedAnnotations or getattr(shared,'TagTime',None) is not None:return None
        from disco.decisions.tag_times import chip_time
        found=[]
        for kind in ('epoch','cell'):
            for row in shared._rows(kind):
                target=row['target_uuid']
                if not (target in universe if kind=='epoch' else
                        any(key in universe for key in derived.cell_epochs(target))):continue
                values=shared._validated_tags(row)
                if tag in values:found.append((kind,row['target_uuid'],chip_time(row,tag,None)['added_at']))
        return found
