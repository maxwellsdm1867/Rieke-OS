"""Baseline-only adapter. Its rank cursors are NOT production cursor qualification."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'python'))
from disco.metadata.disk_index import DiskMetadataIndex
import disco.navigation.predicates as predicates


class NativeAdapter:
    def __init__(self, path, fixture):
        self.index = DiskMetadataIndex.build(path, fixture['rows'], fixture['details'],
                                            fixture['sources'], 'qualification-v1', 'isolated')
        rows = self.index.rows()
        ids = sorted(rows, key=lambda i: (rows[i]['date'], rows[i]['start_time'], i))
        self.rank = {i:r for r,i in enumerate(ids,1)}
        self.fields = [f['id'] for f in self.index.catalog()['fields']]

    def membership(self, predicate=None, scope=None):
        if isinstance(scope, dict):
            requested=scope
            structural={f:v for f,v in scope.items() if f not in {'sources','epoch_ids'}}
            scope = self.index.match({'all':[dict(field=f, operator='eq', value=v)
                                            for f,v in structural.items()]})[1]
            if 'epoch_ids' in requested:scope=[i for i in scope if i in requested['epoch_ids']]
            if 'sources' in requested:
                rows=self.index.rows()
                scope=[i for i in scope if rows[i]['source_sha256'] in requested['sources']]
        if predicate is None: predicate = {'all':[]}
        return sorted(self.index.match(predicate, ids=scope)[1], key=self.rank.__getitem__)

    def preview(self, predicate=None, scope=None, facet_fields=(), limit=60, cursor=None):
        ids = self.membership(predicate, scope)
        remaining = [i for i in ids if self.rank[i] > (cursor or 0)]
        page = remaining[:limit]
        with self.index._connect(page) as connection:
            rows = [json.loads(raw) for raw, in connection.execute(
                'SELECT e.row_json FROM scope s JOIN epochs e USING(epoch_id) ORDER BY s.ordinal')]
        values = dict(self.index.values(ids, facet_fields).items()) if facet_fields else {}
        facets = {}
        for field in facet_fields:
            buckets, present = {}, 0
            for i in ids:
                if field not in values[i]: continue
                present += 1
                v = values[i][field]; key = predicates.equality_key(v)
                buckets.setdefault(key, dict(value=v, type=predicates.kind(v), count=0))['count'] += 1
            facets[field] = dict(values=list(buckets.values())[:60], missing_count=len(ids)-present,
                                 present_count=present, values_truncated=len(buckets)>60)
        return dict(count=len(ids), rows=rows, cursor=self.rank[page[-1]] if len(remaining)>limit else None,
                    facets=facets)

    def detail(self, identity): return self.index.details[identity]
    def close(self): self.index.close()
