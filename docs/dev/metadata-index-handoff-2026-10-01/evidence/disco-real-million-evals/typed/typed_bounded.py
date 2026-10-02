"""Second experiment: page narrow IDs before fetching native JSON DTOs.
Original typed indexes, predicate validation, counts, facets and DTOs unchanged.
"""
import json
from typed_sidecar import TypedRealSidecar
class TypedBoundedSidecar(TypedRealSidecar):
    def _page(self,where,arguments,cursor=None,limit=60):
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('Page limit must be 1..100')
        cursor_sql='';cursor_args=[]
        if cursor is not None:
            if type(cursor) is not int or cursor<1:
                raise ValueError('Cursor must be a chronology rank')
            cursor_sql=' AND c.sort_rank>?';cursor_args=[cursor]
        # MATERIALIZED is intentional: choosing IDs must finish before joining
        # wide native row_json, otherwise broad predicates read hundreds of
        # thousands of JSON payloads only to return sixty rows.
        sql=('WITH page_ids AS MATERIALIZED ('
             'SELECT c.epoch_id,c.sort_rank FROM typed_core c WHERE '+where+cursor_sql+
             ' ORDER BY c.sort_rank LIMIT ?) '
             'SELECT p.sort_rank,e.row_json FROM page_ids p JOIN epochs e USING(epoch_id) ORDER BY p.sort_rank')
        fetched=self.connection.execute(sql,arguments+cursor_args+[limit+1]).fetchall()
        page=fetched[:limit]
        return dict(rows=[json.loads(raw) for _,raw in page],cursor=page[-1][0] if len(fetched)>limit else None)

    def preview(self,predicate=None,scope=None,facet_fields=(),limit=60,cursor=None):
        selective=isinstance(scope,dict) and bool(set(scope)&{'cell','block','group'})
        if not selective or not facet_fields:
            return super().preview(predicate,scope,facet_fields,limit,cursor)
        if len(facet_fields)>140 or len(set(facet_fields))!=len(facet_fields):
            raise ValueError('Facet fields must be unique native fields')
        where,arguments=self._where(predicate,scope)
        count=self.connection.execute('SELECT COUNT(*) FROM typed_core c WHERE '+where,arguments).fetchone()[0]
        page=self._page(where,arguments,cursor,limit);facets={}
        for field in facet_fields:
            if field not in self.fields:raise ValueError('Unknown native facet field')
            number=self.fields[field]
            # CROSS JOIN fixes the loop order for structurally bounded scopes:
            # take the selected core rows, then point-read their indexed values.
            query=('SELECT v.value_json,v.kind,COUNT(*),MIN(c.sort_rank) '
                   'FROM typed_core c CROSS JOIN epoch_values ev '
                   'ON ev.epoch_id=c.epoch_id AND ev.field_no=? '
                   'JOIN typed_values v USING(value_id) WHERE '+where+
                   ' GROUP BY v.equality_json ORDER BY MIN(c.sort_rank) LIMIT 61')
            buckets=self.connection.execute(query,[number]+arguments).fetchall()
            present=self.connection.execute('SELECT COUNT(*) FROM typed_core c CROSS JOIN epoch_values ev '
                'ON ev.epoch_id=c.epoch_id AND ev.field_no=? WHERE '+where,[number]+arguments).fetchone()[0]
            facets[field]=dict(values=[dict(value=json.loads(raw),type=kind,count=n) for raw,kind,n,_ in buckets[:60]],
                missing_count=count-present,present_count=present,values_truncated=len(buckets)>60)
        return dict(count=count,**page,facets=facets)
