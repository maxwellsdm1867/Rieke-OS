"""Full 140-field control with structurally scoped correlated leaf membership.

Only query shape changes for cell/block/group scopes. Global and protocol-only
queries use the previous SQL exactly; native field validation and full typed
value dictionaries, DTOs, count, cursor and facet payloads remain unchanged.
"""
import sys
sys.path.insert(0,'/private/tmp/disco-real-million-20261001/typed')
from typed_bounded import TypedBoundedSidecar

class FullScopedSidecar(TypedBoundedSidecar):
    def _where(self,predicate=None,scope=None):
        previous=getattr(self,'_structurally_scoped',False)
        self._structurally_scoped=isinstance(scope,dict) and bool(set(scope)&{'cell','block','group'})
        try:
            return super()._where(predicate,scope)
        finally:
            self._structurally_scoped=previous

    def _leaf(self,node):
        sql,arguments=super()._leaf(node)
        if not getattr(self,'_structurally_scoped',False):
            return sql,arguments
        exists='c.epoch_id IN (SELECT epoch_id FROM epoch_values WHERE field_no=?)'
        missing='c.epoch_id NOT IN (SELECT epoch_id FROM epoch_values WHERE field_no=?)'
        local='EXISTS (SELECT 1 FROM epoch_values ev WHERE ev.epoch_id=c.epoch_id AND ev.field_no=?)'
        if sql==exists:return local,arguments
        if sql==missing:return 'NOT '+local,arguments
        prefix=('c.epoch_id IN (SELECT ev.epoch_id FROM typed_values v JOIN epoch_values ev '
                'ON ev.field_no=v.field_no AND ev.value_id=v.value_id WHERE v.field_no=? AND (')
        if sql.startswith(prefix) and sql.endswith('))'):
            selector=sql[len(prefix):-2]
            # Fix loop order to first point-read the selected epoch/field entry,
            # then its globally unique dictionary value. A tiny parent scope
            # must never enumerate project-wide metadata membership first.
            sql=('EXISTS (SELECT 1 FROM epoch_values ev CROSS JOIN typed_values v '
                 'ON ev.field_no=v.field_no AND ev.value_id=v.value_id '
                 'WHERE ev.epoch_id=c.epoch_id AND ev.field_no=? AND ('+selector+'))')
        return sql,arguments
