"""Versioned project query methods, independent of frozen export membership."""
import copy
import datetime as dt
import json
import hashlib
import uuid
from workspace_curation import RevisionConflict


def preset_tables(dj):
    schema = dj.Schema('recording_workspace')

    @schema
    class SearchPreset(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        preset_uuid: varchar(36)
        ---
        name: varchar(160)
        description: varchar(2000)
        predicate: json
        splits: varchar(4096)
        pinned: bool
        version: int unsigned
        updated_at: datetime
        actor: varchar(255)
        """

    @schema
    class SearchPresetVersion(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        preset_uuid: varchar(36)
        version: int unsigned
        ---
        recipe: json
        """
    return SearchPreset, SearchPresetVersion


def canonical_predicate(predicate):
    def number_literals(value):
        if type(value) is float and value.is_integer():
            return int(value)
        if isinstance(value, list):
            return [number_literals(item) for item in value]
        if isinstance(value, dict):
            return {key: number_literals(item) for key, item in value.items()}
        return value
    def serialize(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    def normalize(node):
        if 'not' in node:
            child = normalize(node['not'])
            return child['not'] if set(child) == {'not'} else {'not': child}
        for key in ('all', 'any'):
            if key in node:
                children = []
                for child in node[key]:
                    child = normalize(child)
                    children.extend(child[key] if set(child) == {key} else [child])
                unique = {serialize(child): child for child in children}
                children = [unique[key] for key in sorted(unique)]
                return children[0] if len(children) == 1 else {key: children}
        leaf = number_literals(node)
        if leaf.get('operator') in ('in', 'not_in'):
            unique = {serialize(item): item for item in leaf['value']}
            leaf['value'] = [unique[key] for key in sorted(unique)]
        return leaf
    return normalize(predicate)


def query_key(predicate):
    return hashlib.sha256(json.dumps(canonical_predicate(predicate), sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def query_run_table(dj):
    schema = dj.Schema('recording_workspace')

    @schema
    class SearchQueryLastRun(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        query_sha256: char(64)
        ---
        result: json
        """
    return SearchQueryLastRun


class SearchPresets:
    def __init__(self, store, tables=None, runs=None):
        self.store = store
        self.Table, self.Version = preset_tables(store.dj) if tables is None else tables
        self.Runs = query_run_table(store.dj) if runs is None else runs

    @staticmethod
    def validate(body, update=False):
        required = {'name', 'predicate', 'splits', 'pinned'}
        allowed = required | {'description'}
        if update:
            required.add('expected_version')
            allowed.add('expected_version')
        if not isinstance(body, dict) or set(body) - allowed or required - set(body):
            raise ValueError('Preset requires name, predicate, splits and pinned; updates also require expected_version')
        if not isinstance(body['name'], str) or not body['name'].strip() or len(body['name']) > 160:
            raise ValueError('Preset name must contain 1–160 characters')
        description = body.get('description', '')
        if not isinstance(description, str) or len(description) > 2000:
            raise ValueError('Preset description must be at most 2000 characters')
        if type(body['pinned']) is not bool:
            raise ValueError('Preset pinned must be a boolean')
        if not isinstance(body['predicate'], dict) or len(json.dumps(body['predicate'], allow_nan=False)) > 65536:
            raise ValueError('Preset predicate must be an object of at most 64 KB')
        if not isinstance(body['splits'], str) or len(body['splits']) > 4096:
            raise ValueError('Preset splits must be a string of at most 4096 characters')
        if update and (type(body['expected_version']) is not int or body['expected_version'] < 1):
            raise ValueError('Preset expected_version must be a positive integer')
        return dict(name=body['name'].strip(), description=description.strip(),
                    predicate=copy.deepcopy(body['predicate']), splits=body['splits'], pinned=body['pinned'])

    def read(self, identity):
        rows = (self.Table & {'project_uuid': self.store.project_uuid,
                              'preset_uuid': str(uuid.UUID(identity))}).to_dicts()
        if not rows:
            raise KeyError('Saved query preset not found in this project')
        row = copy.deepcopy(rows[0])
        row['pinned'] = bool(row['pinned'])
        return self.with_last_runs([row])[0]

    def with_last_runs(self, rows):
        if not rows:
            return []
        keys = [{'query_sha256': query_key(row['predicate'])} for row in rows]
        runs = (self.Runs & {'project_uuid': self.store.project_uuid} & keys).to_dicts()
        by_key = {row['query_sha256']: row['result'] for row in runs}
        return [{**row, 'last_run': copy.deepcopy(by_key.get(query_key(row['predicate'])))} for row in rows]

    def record_run(self, preview, rows, actor):
        key = query_key(preview['predicate'])
        result = dict(ran_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                      predicate=copy.deepcopy(preview['predicate']), splits=preview.get('splits',''),
                      source_revisions=sorted(preview.get('source_revisions',preview['source_scope'].get('active_source_revisions',[]))),
                      predicate_version=1, metadata_fingerprint_version=preview.get('metadata_fingerprint_version',2),
                      epoch_count=preview['matched_count'],
                      cell_count=len({rows[item['uuid']]['cell_uuid'] for item in preview['membership']}),
                      tree_revision=preview['tree_revision'],
                      source_revision=preview['source_scope']['revision'], actor=actor)
        scope = dict(project_uuid=self.store.project_uuid, query_sha256=key)
        with self.store._transaction('query:' + key):
            previous = (self.Runs & scope).to_dicts()
            row = dict(**scope, result=result)
            if previous:
                self.Runs.update1(row)
            else:
                self.Runs.insert1(row)
            self.store._event(actor, 'search_query_run', dict(query_sha256=key, **result, membership_changed=False))
        return result

    def list(self, limit=100, offset=0):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError('Preset pagination requires limit 1–100 and a nonnegative offset')
        relation = self.Table & {'project_uuid': self.store.project_uuid}
        total = len(relation)
        rows = relation.fetch(as_dict=True, order_by='pinned DESC, name ASC, preset_uuid ASC', limit=limit, offset=offset)
        return {'presets': self.with_last_runs([{**copy.deepcopy(row), 'pinned': bool(row['pinned'])} for row in rows]),
                'total': total, 'has_more': offset + limit < total, 'offset': offset, 'limit': limit}

    def resolve(self, predicate, exclude=None):
        key = query_key(predicate)
        rows = (self.Table & {'project_uuid': self.store.project_uuid}).proj('predicate').to_dicts()
        for row in rows:
            if row['preset_uuid'] != exclude and query_key(row['predicate']) == key:
                return self.read(row['preset_uuid'])
        return None

    def versions(self, identity, limit=20, offset=0):
        self.read(identity)
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError('Version pagination requires limit 1–100 and nonnegative offset')
        rows = (self.Version & dict(project_uuid=self.store.project_uuid, preset_uuid=identity)).fetch(
            as_dict=True, order_by='version DESC', limit=limit+1, offset=offset)
        return {'versions': [{key: row['recipe'].get(key) for key in ('name','description','updated_at','actor','predicate','splits','preset_version')} for row in rows[:limit]],
                'has_more': len(rows)>limit, 'offset':offset, 'limit':limit}

    def save(self, body, actor, identity=None):
        values = self.validate(body, update=identity is not None)
        identity = str(uuid.UUID(identity)) if identity else str(uuid.uuid4())
        with self.store._transaction('search-presets'):
            duplicate = self.resolve(values['predicate'], exclude=identity)
            if duplicate:
                if 'expected_version' in body:
                    raise RevisionConflict({'duplicate_search_preset': duplicate})
                return {**duplicate, 'reused': True}
            previous = self.read(identity) if 'expected_version' in body else None
            if previous and previous['version'] != body['expected_version']:
                raise RevisionConflict({'search_preset': previous})
            if previous and all(previous[key] == value for key,value in values.items() if key != 'predicate') and query_key(previous['predicate']) == query_key(values['predicate']):
                return {**previous, 'reused': True}
            row = dict(project_uuid=self.store.project_uuid, preset_uuid=identity, **values,
                       version=previous['version'] + 1 if previous else 1,
                       updated_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None), actor=actor)
            if previous:
                self.Table.update1(row)
            else:
                self.Table.insert1(row)
            snapshot = {**copy.deepcopy(row), 'updated_at': row['updated_at'].isoformat() + 'Z',
                        'format': 'rieke-search-preset', 'version': 1, 'preset_version': row['version'],
                        'catalog_ref': 'catalog.json', 'membership_mode': 'live-query'}
            self.Version.insert1(dict(project_uuid=self.store.project_uuid, preset_uuid=identity,
                                      version=row['version'], recipe=snapshot))
            self.store._event(actor, 'search_preset_updated' if previous else 'search_preset_created', {
                'preset_uuid': identity, 'name': row['name'], 'version': row['version'],
                'previous_version': previous['version'] if previous else None,
                'pinned': row['pinned'], 'membership_changed': False})
            return self.with_last_runs([copy.deepcopy(row)])[0]
