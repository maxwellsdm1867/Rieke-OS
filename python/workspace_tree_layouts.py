"""Latest protocol tree arrangement, independent of dataset membership."""
import copy
import datetime as dt
import uuid
from workspace_curation import RevisionConflict


def layout_table(dj):
    schema = dj.Schema('recording_workspace')

    @schema
    class ProtocolTreeLayout(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        protocol_uuid: varchar(36)
        ---
        split_order: json
        version: int unsigned
        updated_at: datetime
        actor: varchar(255)
        """
    return ProtocolTreeLayout


class TreeLayouts:
    def __init__(self, store, table=None):
        self.store = store
        self.Table = layout_table(store.dj) if table is None else table

    def read(self, protocol_uuid):
        scope = dict(project_uuid=self.store.project_uuid,
                     protocol_uuid=str(uuid.UUID(protocol_uuid)))
        rows = (self.Table & scope).to_dicts()
        return copy.deepcopy(rows[0]) if rows else None

    def save(self, protocol_uuid, fields, expected_version, actor):
        protocol_uuid = str(uuid.UUID(protocol_uuid))
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError('Tree layout version must be a nonnegative integer')
        if (not isinstance(fields, list) or len(fields) > 8 or
                any(not isinstance(field, str) or not field or len(field) > 2048 for field in fields) or
                len(set(fields)) != len(fields)):
            raise ValueError('Expected up to eight unique tree split fields')
        with self.store._transaction(protocol_uuid):
            previous = self.read(protocol_uuid)
            version = previous['version'] if previous else 0
            if version != expected_version:
                raise RevisionConflict({'tree_layout': previous})
            if previous and previous['split_order'] == fields:
                return previous
            row = dict(project_uuid=self.store.project_uuid, protocol_uuid=protocol_uuid,
                       split_order=list(fields), version=version + 1,
                       updated_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None), actor=actor)
            if previous:
                self.Table.update1(row)
            else:
                self.Table.insert1(row)
            self.store._event(actor, 'protocol_tree_layout_saved', {
                'protocol_uuid': protocol_uuid, 'version': row['version'],
                'previous_split_order': previous['split_order'] if previous else None,
                'split_order': list(fields), 'membership_changed': False})
            return copy.deepcopy(row)
