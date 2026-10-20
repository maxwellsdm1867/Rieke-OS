"""Explicit protocol-scoped tag predicates; raw acquisition indexes stay immutable."""
from __future__ import annotations
import copy
import contextlib
import hashlib
import uuid
from disco.navigation.predicates import MAX_CHOICES, MAX_NODES, validate, matches
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
DELTA_MAX_RECORDS=1000


def _shared_token(witness):
    """The shared scope token in a witness (every shared/time field carries it)."""
    return next((token for field,token in witness[1] if field in SHARED_FIELDS or field in TIME_FIELDS),None)


def _shared_values(cell,epoch):
    """Shared field arrays for one epoch from its cell and direct records."""
    effective=cell+epoch
    return {'annotations/cell/tags':sorted({tag for r in cell for tag in r['tags']}),
            'annotations/epoch/tags':sorted({tag for r in epoch for tag in r['tags']}),
            'annotations/effective/tags':sorted({tag for r in effective for tag in r['tags']}),
            'annotations/authors':sorted({r['author_name'] for r in effective if r['tags']}),
            'annotations/author_uuids':sorted({r['profile_uuid'] for r in effective if r['tags']})}


_PLAIN=frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./:-')


def _canonical_strings(value):
    """checksum()'s JSON text for nested lists of plain strings; None otherwise."""
    if isinstance(value,str):
        return '"'+value+'"' if _PLAIN.issuperset(value) else None
    if isinstance(value,(list,tuple)):
        parts=[_canonical_strings(item) for item in value]
        return None if any(part is None for part in parts) else '['+','.join(parts)+']'
    return None


class _Publication:
    """Structures derived from one captured metadata publication."""
    def __init__(self,service):
        self.rows,self.fingerprints=service.rows,service._fingerprints
        self._universe=None;self._cells=None;self._links_hash=None;self.source_counts=None

    def universe(self):
        if self._universe is None:self._universe=checksum(sorted(self.fingerprints))
        return self._universe

    def cell_epochs(self,cell):
        if self._cells is None:
            cells={}
            for key,row in self.rows.items():cells.setdefault(row['cell_uuid'],[]).append(key)
            self._cells=cells
        return self._cells.get(cell,())

    def cell_links(self):
        return sorted((key,row['cell_uuid']) for key,row in self.rows.items())

    def prepare(self):
        """Do publication-sized work before the read model becomes available."""
        self.universe()
        cells={};sources={}
        for key,row in self.rows.items():
            cells.setdefault(row['cell_uuid'],[]).append(key)
            source=row['source_sha256'];sources[source]=sources.get(source,0)+1
        self._cells,self.source_counts=cells,sources
        # Keep the exact historical JSON/hash bytes used in saved evidence.
        links=_canonical_strings(self.cell_links())
        if links is not None:
            self._links_hash=hashlib.sha256(('{"protocols":[],"registered_cell_links":'+links).encode())
        return self

    def shared_revision(self,protocols,shared_revision,fields):
        """checksum() of the shared evidence identity, byte for byte.

        Without protocol fields the canonical JSON begins with a fixed prefix
        and the publication's sorted cell links, so that hash state is kept and
        each shared generation only appends its own suffix.
        """
        identity=lambda:checksum({'protocols':protocols,'shared_revision':shared_revision,
                                  'shared_fields':fields,'registered_cell_links':self.cell_links()})
        names,revision=_canonical_strings(fields),_canonical_strings(shared_revision)
        if protocols or names is None or revision is None:return identity()
        if self._links_hash is None:
            links=_canonical_strings(self.cell_links())
            if links is None:return identity()
            self._links_hash=hashlib.sha256(('{"protocols":[],"registered_cell_links":'+links).encode())
        state=self._links_hash.copy()
        state.update((',"shared_fields":'+names+',"shared_revision":'+revision+'}').encode())
        return state.hexdigest()


def prepare_publication(service):
    """Prepare immutable metadata-derived tag witnesses during publication.

    Tags and their SQL generations are deliberately absent: only the frozen
    row/cell links, fingerprint universe and source cardinalities are retained.
    Mutable/custom publications keep their existing uncached fallback.
    """
    from workspace_service import publication_serial
    if publication_serial(service) is None:
        return None
    current=getattr(service,'_prepared_tag_publication',None)
    if current is None or current.rows is not service.rows or current.fingerprints is not service._fingerprints:
        current=_Publication(service).prepare()
        service._prepared_tag_publication=current
    return current


class _Entry:
    """One generation's tag states, evidence and lazily inverted values."""
    def __init__(self,states,evidence):
        self.states,self.evidence=states,evidence;self._groups={};self._plain={}
        self.publication=None;self.shared=None;self.shared_token=None

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

    def plain(self,field):
        """True when every tag's JSON text is the same in Python and SQLite."""
        found=self._plain.get(field)
        if found is None:
            found=self._plain[field]=all(not any(ord(char)<32 or 0xd800<=ord(char)<=0xdfff for char in tag)
                for value,_ in self.groups(field)[0] for tag in value)
        return found

    def buckets(self,field,ids,universe,rank):
        """(value, count) per distinct array in `ids`, ordered by first occurrence."""
        groups,tagged=self.groups(field);found=[]
        for value,members in groups:
            inside=members & universe
            if inside:found.append((min(map(rank,inside)),value,len(inside)))
        untagged=len(universe)-len(tagged & universe)
        if untagged:
            first=next(identity for identity in ids if identity not in tagged)
            found.append((rank(first),[],untagged))
        found.sort(key=lambda item:item[0])
        return [(value,amount) for _,value,amount in found]

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
            prepared=getattr(self.service,'_prepared_tag_publication',None)
            if prepared is None or prepared.rows is not self.service.rows or prepared.fingerprints is not self.service._fingerprints:
                prepared=_Publication(self.service)
            current=self.service._tag_predicate_publication=(common,prepared)
        return current[1]

    def _entry(self,fields):
        """States/evidence for these fields, memoized per verified generation.

        A hit performs only witness token reads. After a shared tag write, the
        previous entry for these fields is patched from the shared change feed
        when that feed proves the complete set of changed records; otherwise
        the entry is rebuilt. Entries are stored only when the witness is
        unchanged after the build; an unavailable witness always recomputes,
        exactly as before.
        """
        fields=frozenset(fields)
        witness=self._witness(fields)
        memo=getattr(self.service,'_tag_predicate_memo',None)
        if witness is not None and memo is not None and witness in memo:
            memo[witness]=memo.pop(witness)  # Most recently used last.
            return memo[witness]
        tracker=getattr(self.service,'_explore_state_generation',None)
        token=tracker.token(None) if witness is not None and tracker is not None else None
        entry=self._delta(fields,witness,memo,tracker) if witness is not None else None
        if entry is None:
            entry=self._build(fields,self._derived(witness[0] if witness else None))
        if witness is not None and self._witness(fields)==witness:
            shared=_shared_token(witness)
            entry.shared_token=token if token is not None and shared==(token.shared_epoch,token.shared_generation) else None
            if memo is None:memo=self.service._tag_predicate_memo={}
            memo[witness]=entry
            while len(memo)>MEMO_ENTRIES:memo.pop(next(iter(memo)))
        return entry

    def _delta(self,fields,witness,memo,tracker):
        """Patch the latest entry for `fields` from the shared change feed, or None.

        Only when the publication, every protocol token and the field set are
        unchanged, the previous entry carries the exact shared token it was
        built at, and the feed returns every changed record up to the current
        witness. Changed records are re-read and validated by key.
        """
        shared_fields=fields & SHARED_FIELDS.keys()
        store=getattr(self.service,'shared_annotations',None)
        if not shared_fields or not memo or tracker is None or store is None:return None
        reader=getattr(store,'_index_records',None);validate=getattr(store,'_index_record_tags',None)
        if reader is None or validate is None:return None
        common,tokens=witness
        current=_shared_token(witness)
        previous=None
        for key,candidate in reversed(memo.items()):
            if (key[0]==common and len(key[1])==len(tokens) and {name for name,_ in key[1]}=={name for name,_ in tokens}
                    and all(value==dict(key[1])[name] for name,value in tokens if name.startswith(PREFIX))
                    and getattr(candidate,'shared_token',None) is not None and getattr(candidate,'shared',None) is not None):
                previous=candidate;break
        if previous is None:return None
        change=tracker.shared_changes(previous.shared_token)
        if change is None:return None
        rows,after=change
        if after is None or (after.shared_epoch,after.shared_generation)!=current:return None
        keys={}
        for row in rows:
            if row['target_kind'] in ('cell','epoch'):
                keys[(row['target_kind'],row['target_uuid'],row['profile_uuid'])]=row
        if len(keys)>DELTA_MAX_RECORDS:return None
        fresh={}
        if keys:
            for row in reader([{'target_kind':kind,'target_uuid':target,'profile_uuid':profile} for kind,target,profile in keys]):
                key=(row['target_kind'],row['target_uuid'],row['profile_uuid'])
                if key not in keys:raise ValueError('Shared tag change read returned an unrequested record')
                validate(row)
                fresh[key]={name:copy.deepcopy(row[name]) for name in ('target_kind','target_uuid','profile_uuid','author_name','revision','tags')}
        old=previous.shared;records={(r['target_kind'],r['target_uuid'],r['profile_uuid']):r for r in old['records']}
        for key in keys:
            if key in fresh:records[key]=fresh[key]
            else:records.pop(key,None)
        ordered=[records[key] for key in sorted(records)]
        snapshot={**{name:value for name,value in old.items() if name not in ('records','revision')},
                  'revision':checksum({'project_uuid':old['project_uuid'],'records':ordered}),'records':ordered}
        derived=previous.publication
        cell_records={};epoch_records={}
        for row in ordered:
            (cell_records if row['target_kind']=='cell' else epoch_records).setdefault(row['target_uuid'],[]).append(row)
        rows_=self.service.rows;affected=set()
        for kind,target,_ in keys:
            if kind=='epoch':
                if target in rows_:affected.add(target)
            else:affected.update(derived.cell_epochs(target))
        states={field:(dict(values) if field in shared_fields else values) for field,values in previous.states.items()}
        for epoch in affected:
            values=_shared_values(cell_records.get(rows_[epoch]['cell_uuid'],[]),epoch_records.get(epoch,[]))
            for field in shared_fields:
                if values[field]:states[field][epoch]=values[field]
                else:states[field].pop(epoch,None)
        evidence={**previous.evidence,'shared':snapshot}
        evidence['revision']=derived.shared_revision([(p['protocol_uuid'],p['revision']) for p in evidence['protocols']],
            snapshot['revision'],evidence['fields'])
        entry=_Entry(states,evidence);entry.publication=derived;entry.shared=snapshot
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
            provider=self.service.annotation_provider
            saved=getattr(provider,'saved_states',None)
            # Saved decisions only: an absent epoch is untagged at revision 0
            # and contributes no record or value, exactly as its default state.
            current=saved(protocol,fingerprints) if saved is not None else provider(protocol,dict(fingerprints))
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
                values_for=_shared_values
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
            evidence['revision']=derived.shared_revision([(p['protocol_uuid'],p['revision']) for p in protocols],
                snapshot['revision'],sorted(shared_fields|time_fields))
        entry=_Entry(states,evidence);entry.publication=derived
        entry.shared=evidence.get('shared')
        return entry

    def catalog_fields(self,ids,only=None):
        """Annotation catalog fields over `ids` (in scope order).

        Buckets come from the generation's tag states: one pass over tagged
        epochs and distinct tag arrays, never one value per epoch. Output is
        exactly the previous construction: the shared index's format for shared
        fields it would answer, the per-epoch catalog format otherwise. When
        `ids` is the service's cached eligible tuple, its universe and tree-key
        order are reused instead of indexing every ID.
        """
        definitions=[field for field in self.definitions() if field.get('value_shape')!='tag_time']
        if only is not None:definitions=[field for field in definitions if field['id'] in only]
        if not definitions: return []
        ids=ids if isinstance(ids,(list,tuple)) else list(ids)
        all_fields={field['id'] for field in definitions};indexed={};index_format=set()
        shared=getattr(self.service,'shared_annotations',None)
        shared_fields=all_fields & SHARED_FIELDS.keys()
        if shared is not None and hasattr(shared,'catalog_fields') and shared_fields:
            if self._witness(shared_fields) is not None:
                # A verified native store answers these from its shared index;
                # the same statistics follow from the tag states below.
                index_format=set(shared_fields)
            else:
                indexed=shared.catalog_fields([self.service.rows[key] for key in ids],shared_fields) or {}
        remaining=all_fields-indexed.keys()
        entry=self._entry(remaining) if remaining else None
        if entry is not None:
            for key in sorted(index_format):
                if not entry.plain(key):
                    # Text whose JSON spelling could differ: ask the index itself.
                    indexed.update(shared.catalog_fields([self.service.rows[item] for item in ids],{key}) or {})
            index_format-=indexed.keys()
        cached=getattr(self.service,'_eligible_cache',None)
        if cached is not None and ids is cached[1][1]:
            universe,rows=cached[1][3],self.service.rows
            rank=lambda key:(rows[key]['date'],rows[key]['start_time'],key)
        else:
            universe=set(ids)
            positions={identity:position for position,identity in enumerate(ids)}
            rank=positions.__getitem__
        fields=[]
        for definition in definitions:
            key=definition['id']
            if key in indexed:
                fields.append({**definition,**indexed[key]});continue
            buckets=entry.buckets(key,ids,universe,rank)
            distinct=len(buckets);count=len(ids)
            if key in index_format:
                examples=sorted(value_key(value)[:160] for value,_ in buckets)[:5]
                fields.append({**definition,'count':count,'distinct_count':distinct,'recorded_distinct_count':distinct,
                    'missing_count':0,'null_count':0,'varying':distinct>1,'examples':examples,
                    'grouping_role':'annotation','grouping_priority':100,'varies_within_cell':False,
                    'suggested_rank':None,'suggestion_reason':'','high_cardinality':distinct>24,
                    'active_types':['array'] if count else [],'types':['array'],'types_scope':'project_annotations',
                    'element_types':['string'],'choices':[{'value':copy.deepcopy(value),'type':'array','count':amount}
                        for value,amount in buckets[:MAX_CHOICES]],'choices_truncated':distinct>MAX_CHOICES})
                continue
            examples=[value_label(value)[:160] for value in sorted((value for value,_ in buckets),key=value_order)[:5]]
            field=copy.deepcopy(definition)
            field.update({'count':count,'distinct_count':distinct,'recorded_distinct_count':distinct,
                'missing_count':0,'null_count':0,'varying':distinct>1,'examples':examples,
                'grouping_role':'annotation','grouping_priority':100,'varies_within_cell':False,
                'suggested_rank':None,'suggestion_reason':'','high_cardinality':distinct>24,
                'types':['array'] if count else [],
                'choices':[{'value':copy.deepcopy(value),'type':'array','count':amount} for value,amount in buckets[:MAX_CHOICES]],
                'choices_truncated':distinct>MAX_CHOICES})
            field.update(active_types=field['types'],types=['array'],types_scope='project_annotations',element_types=['string'])
            fields.append(field)
        return fields

    def match(self,predicate,ids,*,universe=None,order=None):
        """Validated predicate, matching IDs in `ids` order, and tag evidence.

        A caller that owns `ids` may pass its precomputed `universe` (exactly
        set(ids)) and `order`, a function returning matched IDs in `ids` order.
        """
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
        universe=set(ids) if universe is None else universe
        def walk(node):
            # Every branch returns a fresh mutable subset of the universe.
            if not referenced_fields(node):
                return set(self.service._match_metadata_predicate(node,ids)[1])
            if 'all' in node:
                children=node['all']
                if not children:return set(universe)
                result=walk(children[0])
                # No short circuit: each metadata subtree is still validated.
                for child in children[1:]: result.intersection_update(walk(child))
                return result
            if 'any' in node:
                result=set()
                for child in node['any']: result.update(walk(child))
                return result
            if 'not' in node:
                result=set(universe);result.difference_update(walk(node['not']))
                return result
            if node['field'] in TIME_FIELDS: return self._time_leaf(node,ids,universe,entry)
            return entry.leaf(node,universe)
        matched=walk(validated)
        ordered=(order(matched) if order is not None and len(matched)*8<len(ids)
                 else [identity for identity in ids if identity in matched])
        return validated,ordered,copy.deepcopy(entry.evidence)

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
        """Chip times for a store without a time table, read from its records."""
        reader=getattr(shared,'approximate_tag_times',None)
        if reader is None:return None
        return reader(tag,universe.__contains__,
                      lambda cell:any(key in universe for key in derived.cell_epochs(cell)))
