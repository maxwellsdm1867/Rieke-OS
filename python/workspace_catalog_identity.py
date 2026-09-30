"""Independently verify populated acquisition relationships before SQL commit.

Names and numeric database IDs are never used as acquisition identity. Numeric
IDs only resolve the foreign-key ownership of exact recorded UUIDs. One fetch
per hierarchy table replaces per-epoch stream fetches for verification.
"""
from __future__ import annotations

import json
import datetime as dt
from decimal import Decimal, InvalidOperation


class CatalogIdentityConflict(ValueError):
    def __init__(self, kind, detail, *, identity=None):
        self.conflict = {'kind':kind,'detail':detail,'resolution':'explicit_source_reconciliation',
                         **({'acquisition_uuid':identity} if identity is not None else {})}
        super().__init__(detail + '; import stopped without merging, renumbering or overwriting acquisition records. Explicit source reconciliation is required.')


def _exact(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def _same_rate(left,right):
    try:
        a,b=Decimal(str(left)),Decimal(str(right))
        return a.is_finite() and b.is_finite() and a==b
    except (InvalidOperation,ValueError,TypeError):
        return False


SCALAR_COLUMNS={
    'Experiment':{'experimenter':'experimenter','institution':'institution','lab':'lab','project':'project','rig':'rig','rig_type':'rig_type'},
    'Animal':{'props_id':'id','description':'description','sex':'sex','age':'age','weight':'weight','dark_adaptation':'darkAdaptation','species':'species'},
    'Preparation':{'bath_solution':'bathSolution','preparation_type':'preparationType','region':'region','array_pitch':'arrayPitch'},
    'Cell':{'type':'type'},
    'EpochBlock':{'array_pitch':'arrayPitch'},
    'Response':{'offset_hours':'inputTimeDotNetDateTimeOffsetOffsetHours','offset_ticks':'inputTimeDotNetDateTimeOffsetTicks'},
}


def _same_scalar(actual,expected):
    if expected is None:return actual is None
    if type(expected) in (int,float):return _same_rate(actual,expected)
    if isinstance(expected,bool):return str(actual)==('1' if expected else '0')
    return str(actual)==str(expected)


def _same_datetime(actual,expected):
    if expected is None:return actual is None
    try:
        source=expected if isinstance(expected,dt.datetime) else dt.datetime.strptime(expected,'%m/%d/%Y %H:%M:%S:%f')
        recorded=actual if isinstance(actual,dt.datetime) else dt.datetime.fromisoformat(str(actual))
    except (TypeError,ValueError):return False
    # The pinned catalog uses DATETIME(0). Historical MySQL modes either truncate
    # or round fractions; full precision remains in the verified source JSON.
    # Accept only those documented encodings, never an arbitrary time tolerance.
    allowed={source,source.replace(microsecond=0)}
    if source.microsecond>=500000:
        allowed.add(source.replace(microsecond=0)+dt.timedelta(seconds=1))
    return recorded in allowed


def validate_catalog_identity(experiment, catalog, experiment_id, progress=None):
    """Check exact membership, multiplicity, parent links and recorded metadata.

    Must run inside the import transaction for both new and same-source imports.
    Supports repeated display labels and metadata, but never duplicate UUID rows
    or a UUID linked to a different parent. No database writes are performed.
    """
    expected={name:{} for name in ('Experiment','Animal','Preparation','Cell','EpochGroup','EpochBlock','Epoch','Response','Stimulus')}
    parents={'Animal':'Experiment','Preparation':'Animal','Cell':'Preparation','EpochGroup':'Cell',
             'EpochBlock':'EpochGroup','Epoch':'EpochBlock','Response':'Epoch','Stimulus':'Epoch'}

    def add(kind,item,parent=None,device=None):
        identity=item.get('uuid')
        if not isinstance(identity,str) or not identity or identity in expected[kind]:
            raise CatalogIdentityConflict('incoming_uuid_multiplicity',f'Incoming {kind} has missing or repeated acquisition UUID',identity=identity)
        expected[kind][identity]=(item,parent,device)

    add('Experiment',experiment)
    for animal in experiment['animals']:
        add('Animal',animal,experiment['uuid'])
        for preparation in animal['preparations']:
            add('Preparation',preparation,animal['uuid'])
            for cell in preparation['cells']:
                add('Cell',cell,preparation['uuid'])
                for group in cell['epoch_groups']:
                    add('EpochGroup',group,cell['uuid'])
                    for block in group['epoch_blocks']:
                        add('EpochBlock',block,group['uuid'])
                        for epoch in block['epochs']:
                            add('Epoch',epoch,block['uuid'])
                            for kind,key in (('Response','responses'),('Stimulus','stimuli')):
                                for device,stream in epoch.get(key,{}).items():
                                    add(kind,stream,epoch['uuid'],device)

    indexed={};fetches=0
    for kind,members in expected.items():
        relation=getattr(catalog,kind)
        if kind in ('Response','Stimulus'):
            # Stream tables have no experiment_id column; restrict through the
            # exact source epochs with a server-side parent-key semi-join.
            restriction=(catalog.Epoch & {'experiment_id':experiment_id}).proj(parent_id='id')
        else:
            restriction={'id':experiment_id} if kind=='Experiment' else {'experiment_id':experiment_id}
        records=(relation & restriction).to_dicts();fetches+=1
        by_uuid={};numeric_ids=set()
        for row in records:
            identity=row.get('h5_uuid');number=row.get('id')
            if identity in by_uuid or number is None or number in numeric_ids:
                raise CatalogIdentityConflict('catalog_uuid_multiplicity',f'Catalog {kind} has duplicate UUID or numeric identity',identity=identity)
            by_uuid[identity]=row;numeric_ids.add(number)
        if set(by_uuid)!=set(members):
            raise CatalogIdentityConflict('catalog_membership',f'Catalog {kind} UUID membership differs from the parsed source')
        indexed[kind]=by_uuid
        for identity,(item,parent,device) in members.items():
            row=by_uuid[identity]
            if kind=='Experiment':
                if row['id']!=experiment_id:
                    raise CatalogIdentityConflict('experiment_identity','Catalog experiment identity differs from its source',identity=identity)
                if row.get('is_mea') != (item.get('rig_type')=='MEA'):
                    raise CatalogIdentityConflict('catalog_metadata','Catalog Experiment is_mea differs from the recorded rig_type',identity=identity)
            elif ((kind not in ('Response','Stimulus') and row.get('experiment_id')!=experiment_id)
                  or row.get('parent_id')!=indexed[parents[kind]][parent]['id']):
                raise CatalogIdentityConflict('catalog_parent',f'Catalog {kind} parent ownership differs from its recorded acquisition',identity=identity)
            fields=() if kind=='Stimulus' else ('label',) if kind=='Response' else ('label','properties','attributes','parameters')
            for field in fields:
                if _exact(row.get(field))!=_exact(item.get(field)):
                    raise CatalogIdentityConflict('catalog_metadata',f'Catalog {kind} {field} differs from the parsed source',identity=identity)
            for column,key in SCALAR_COLUMNS.get(kind,{}).items():
                if not _same_scalar(row.get(column),item.get(key)):
                    raise CatalogIdentityConflict('catalog_metadata',f'Catalog {kind} {column} differs from the parsed source',identity=identity)
            if kind not in ('Response','Stimulus'):
                time_fields=('start_time','end_time') if kind in ('EpochGroup','EpochBlock','Epoch') else ('start_time',)
                for field in time_fields:
                    if not _same_datetime(row.get(field),item.get(field)):
                        raise CatalogIdentityConflict('catalog_metadata',f'Catalog {kind} {field} differs from the source timestamp encoding',identity=identity)
            if kind in ('Response','Stimulus'):
                if row.get('device_name')!=device or row.get('h5path')!=item.get('h5path'):
                    raise CatalogIdentityConflict('catalog_stream','Catalog stream identity/device/path differs from source',identity=identity)
                if kind=='Response':
                    for column,key in (('sample_rate','sampleRate'),('sample_rate_units','sampleRateUnits')):
                        same=(_same_rate(row.get(column),item[key]) if column=='sample_rate' and item.get(key) is not None
                              else row.get(column)==item.get(key))
                        if not same:
                            raise CatalogIdentityConflict('catalog_stream',f'Catalog response {column} differs from source',identity=identity)
        if progress:
            progress('verifying_catalog',completed=fetches,total=len(expected),unit='tables')
    # Both blocks and groups store scientific protocol classifications. Fetch
    # only their distinct referenced protocol keys once, including the sentinel
    # used for empty/mixed groups; never issue one protocol query per group.
    protocols_by_object={}
    for identity,(item,_,_) in expected['EpochBlock'].items():
        name=item.get('protocolID')
        if not isinstance(name,str):
            raise CatalogIdentityConflict('catalog_protocol','Recorded block protocol identity is missing or invalid',identity=identity)
        protocols_by_object['EpochBlock',identity]=name
    for identity,(item,_,_) in expected['EpochGroup'].items():
        names={protocols_by_object['EpochBlock',block['uuid']] for block in item['epoch_blocks']}
        protocols_by_object['EpochGroup',identity]=next(iter(names)) if len(names)==1 else 'no_group_protocol'
    if protocols_by_object:
        protocol_ids={indexed[kind][identity].get('protocol_id') for kind,identity in protocols_by_object}
        if None in protocol_ids:
            raise CatalogIdentityConflict('catalog_protocol','Catalog acquisition protocol reference is missing')
        protocols=(catalog.Protocol & [{'protocol_id':number} for number in sorted(protocol_ids)]).to_dicts()
        names={row['protocol_id']:row['name'] for row in protocols}
        if len(names)!=len(protocols):
            raise CatalogIdentityConflict('catalog_protocol','Catalog protocol identities are repeated')
        for (kind,identity),expected_name in protocols_by_object.items():
            if names.get(indexed[kind][identity]['protocol_id'])!=expected_name:
                raise CatalogIdentityConflict('catalog_protocol',f'Catalog {kind} protocol classification differs from its recorded blocks',identity=identity)
    return {kind:len(values) for kind,values in expected.items()}
