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
