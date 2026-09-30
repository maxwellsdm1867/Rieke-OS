"""Exact database ownership oracle: repeated names must never collapse cells."""
import copy
import datetime as dt
from types import SimpleNamespace
import unittest

from workspace_catalog_identity import CatalogIdentityConflict,validate_catalog_identity


class Rows:
    def __init__(self,rows,fetches=None,name=''):
        self.rows=rows;self.fetches=[] if fetches is None else fetches;self.name=name
    def __and__(self,restriction):
        restrictions=restriction.rows if isinstance(restriction,Rows) else restriction if isinstance(restriction,list) else [restriction]
        selected=[row for row in self.rows if any(all(row.get(key)==value for key,value in condition.items()) for condition in restrictions)]
        return Rows(selected,self.fetches,self.name)
    def proj(self,*fields,**renames):
        keys=fields or ()
        return Rows([{**{key:row[key] for key in keys},**{new:row[old] for new,old in renames.items()}} for row in self.rows],self.fetches,self.name)
    def to_dicts(self):
        self.fetches.append((self.name,len(self.rows)))
        return copy.deepcopy(self.rows)
    def __len__(self):return len(self.rows)
    def fetch1(self,*fields):
        assert len(self.rows)==1
        return self.rows[0][fields[0]] if fields else copy.deepcopy(self.rows[0])


def fixture(epochs_per_cell=2):
    # The two cells deliberately share date, label, type and all properties.
    source={'uuid':'experiment','label':'2026-06-11','properties':{'rig':'Rig C'},'attributes':{},'rig_type':'PATCH','animals':[]}
    animal={'uuid':'animal','label':'Animal','properties':{},'attributes':{},'preparations':[]};source['animals']=[animal]
    prep={'uuid':'preparation','label':'Retina','properties':{},'attributes':{},'cells':[]};animal['preparations']=[prep]
    rows={name:[] for name in ('Experiment','Animal','Preparation','Cell','EpochGroup','EpochBlock','Epoch','Response','Stimulus','Protocol')}
    rows['Protocol']=[{'protocol_id':13,'name':'example.Protocol'}]
    next_id=100
    def row(kind,item,parent=None):
        nonlocal next_id
        number=7 if kind=='Experiment' else next_id;next_id+=1
        value={key:copy.deepcopy(item[key]) for key in ('label','properties','attributes','parameters','type') if key in item}
        value.update(id=number,h5_uuid=item['uuid'])
        if kind!='Experiment':value.update(experiment_id=7,parent_id=parent)
        rows[kind].append(value);return number
    row('Experiment',source);rows['Experiment'][0].update(rig_type='PATCH',is_mea=0)
    a=row('Animal',animal,7);p=row('Preparation',prep,a)
    for n in range(2):
        cell={'uuid':f'cell-{n}','label':'Cell3','type':'ON','properties':{'date':'2026-06-11'},'attributes':{},'epoch_groups':[]};prep['cells'].append(cell)
        c=row('Cell',cell,p)
        group={'uuid':f'group-{n}','label':'Control','properties':{},'attributes':{},'epoch_blocks':[]};cell['epoch_groups']=[group]
        g=row('EpochGroup',group,c);rows['EpochGroup'][-1]['protocol_id']=13
        block={'uuid':f'block-{n}','label':'Protocol','protocolID':'example.Protocol','properties':{},'attributes':{},'parameters':{},'epochs':[]};group['epoch_blocks']=[block]
        b=row('EpochBlock',block,g);rows['EpochBlock'][-1]['protocol_id']=13
        for i in range(epochs_per_cell):
            epoch={'uuid':f'epoch-{n}-{i}','label':'Epoch','properties':{},'attributes':{},'parameters':{'contrast':.5,'control':True},'responses':{},'stimuli':{}}
            block['epochs'].append(epoch);e=row('Epoch',epoch,b)
            response={'uuid':f'response-{n}-{i}','label':'Amp1','h5path':f'/source/{n}/{i}/responses/Amp1','sampleRate':10000.,'sampleRateUnits':'Hz'};epoch['responses']['Amp1']=response
            rows['Response'].append({'id':next_id,'h5_uuid':response['uuid'],'parent_id':e,'device_name':'Amp1','h5path':response['h5path'],'label':'Amp1','sample_rate':'10000.0','sample_rate_units':'Hz'});next_id+=1
    fetches=[]
    catalog=SimpleNamespace(**{name:Rows(items,fetches,name) for name,items in rows.items()})
    return source,catalog,rows,fetches


class CatalogIdentityTests(unittest.TestCase):
    def test_matching_labels_and_metadata_are_distinct_by_exact_ownership(self):
        source,catalog,rows,fetches=fixture()
        before=copy.deepcopy((source,rows))
        counts=validate_catalog_identity(source,catalog,7)
        self.assertEqual(counts['Cell'],2);self.assertEqual(counts['Epoch'],4)
        self.assertEqual((source,rows),before)
        self.assertEqual(len(fetches),10)

    def test_swapped_cells_with_unchanged_epoch_sets_counts_and_values_reject(self):
        source,catalog,rows,_=fixture()
        rows['EpochGroup'][0]['parent_id'],rows['EpochGroup'][1]['parent_id']=rows['EpochGroup'][1]['parent_id'],rows['EpochGroup'][0]['parent_id']
        with self.assertRaisesRegex(CatalogIdentityConflict,'EpochGroup parent ownership'):
            validate_catalog_identity(source,catalog,7)

    def test_foreign_source_parent_and_duplicate_uuid_rows_reject(self):
        for kind in ('Cell','EpochBlock','Epoch','Response'):
            with self.subTest(kind=kind):
                source,catalog,rows,_=fixture()
                rows[kind][0]['parent_id']=999999
                with self.assertRaises(CatalogIdentityConflict):validate_catalog_identity(source,catalog,7)
                source,catalog,rows,_=fixture()
                duplicate=copy.deepcopy(rows[kind][0]);duplicate['id']=999999;rows[kind].append(duplicate)
                with self.assertRaisesRegex(CatalogIdentityConflict,'duplicate UUID'):
                    validate_catalog_identity(source,catalog,7)

    def test_correct_counts_with_wrong_cell_identity_or_metadata_reject(self):
        for field,value in [('h5_uuid','other-cell'),('properties',{'date':'2026-06-12'}),('type','OFF')]:
            with self.subTest(field=field):
                source,catalog,rows,_=fixture();rows['Cell'][0][field]=value
                with self.assertRaises(CatalogIdentityConflict):validate_catalog_identity(source,catalog,7)

    def test_boolean_number_confusion_and_wrong_protocol_or_stream_reject(self):
        for mutation in ('boolean','protocol','device','path','rate'):
            with self.subTest(mutation=mutation):
                source,catalog,rows,_=fixture()
                if mutation=='boolean':rows['Epoch'][0]['parameters']['control']=1
                elif mutation=='protocol':rows['Protocol'][0]['name']='other.Protocol'
                elif mutation=='device':rows['Response'][0]['device_name']='Amp2'
                elif mutation=='path':rows['Response'][0]['h5path']='/other'
                else:rows['Response'][0]['sample_rate']='20000'
                with self.assertRaises(CatalogIdentityConflict):validate_catalog_identity(source,catalog,7)

    def test_stream_verification_has_constant_table_fetch_count(self):
        source,catalog,_,fetches=fixture(1000)
        self.assertEqual(validate_catalog_identity(source,catalog,7)['Epoch'],2000)
        self.assertEqual(len(fetches),10)
        self.assertEqual([row for row in fetches if row[0]=='Response'],[('Response',2000)])

    def test_rig_and_time_columns_cannot_disagree_with_source_json(self):
        source,catalog,rows,_=fixture()
        source['rig']='Rig C';rows['Experiment'][0]['rig']='Rig C'
        source['start_time']='06/11/2026 23:59:59:600000'
        for stored in (dt.datetime(2026,6,11,23,59,59),dt.datetime(2026,6,12)):
            rows['Experiment'][0]['start_time']=stored
            validate_catalog_identity(source,catalog,7)
        rows['Experiment'][0]['rig']='Rig H'
        with self.assertRaisesRegex(CatalogIdentityConflict,'rig differs'):
            validate_catalog_identity(source,catalog,7)
        rows['Experiment'][0]['rig']='Rig C';rows['Experiment'][0]['start_time']=dt.datetime(2026,6,10)
        with self.assertRaisesRegex(CatalogIdentityConflict,'timestamp'):
            validate_catalog_identity(source,catalog,7)

    def test_offset_ticks_preserve_large_integer_and_varchar_encoding(self):
        source,catalog,rows,_=fixture()
        epoch=source['animals'][0]['preparations'][0]['cells'][0]['epoch_groups'][0]['epoch_blocks'][0]['epochs'][0]
        response=epoch['responses']['Amp1'];response['inputTimeDotNetDateTimeOffsetTicks']=639258608779858225
        rows['Response'][0]['offset_ticks']='639258608779858225'
        validate_catalog_identity(source,catalog,7)
        rows['Response'][0]['offset_ticks']='639258608779858224'
        with self.assertRaisesRegex(CatalogIdentityConflict,'offset_ticks'):
            validate_catalog_identity(source,catalog,7)

    def test_absent_source_fields_cannot_gain_catalog_metadata(self):
        for kind,column in (('Experiment','rig'),('Animal','sex'),('Preparation','region'),
                            ('Epoch','start_time'),('Response','offset_ticks')):
            with self.subTest(kind=kind,column=column):
                source,catalog,rows,_=fixture()
                rows[kind][0][column]='invented'
                with self.assertRaises(CatalogIdentityConflict):
                    validate_catalog_identity(source,catalog,7)

    def test_nullable_response_fields_must_remain_null_when_absent(self):
        source,catalog,rows,_=fixture()
        response=source['animals'][0]['preparations'][0]['cells'][0]['epoch_groups'][0]['epoch_blocks'][0]['epochs'][0]['responses']['Amp1']
        del response['sampleRate'];rows['Response'][0]['sample_rate']=None
        validate_catalog_identity(source,catalog,7)
        rows['Response'][0]['sample_rate']='10000'
        with self.assertRaises(CatalogIdentityConflict):
            validate_catalog_identity(source,catalog,7)

    def test_experiment_classification_matches_population_for_patch_and_mea(self):
        for rig,expected in (('PATCH',0),('MEA',1)):
            with self.subTest(rig=rig):
                source,catalog,rows,_=fixture()
                source['rig_type']=rig;rows['Experiment'][0].update(rig_type=rig,is_mea=expected)
                validate_catalog_identity(source,catalog,7)
                rows['Experiment'][0]['is_mea']=1-expected
                with self.assertRaisesRegex(CatalogIdentityConflict,'is_mea'):
                    validate_catalog_identity(source,catalog,7)

    def test_uniform_group_protocol_cannot_disagree_with_its_blocks(self):
        source,catalog,rows,_=fixture()
        rows['Protocol'].append({'protocol_id':17,'name':'no_group_protocol'})
        rows['EpochGroup'][0]['protocol_id']=17
        with self.assertRaisesRegex(CatalogIdentityConflict,'EpochGroup protocol classification'):
            validate_catalog_identity(source,catalog,7)

    def test_mixed_and_empty_groups_use_population_sentinel_in_one_fetch(self):
        source,catalog,rows,fetches=fixture()
        first,second=[cell['epoch_groups'][0] for cell in source['animals'][0]['preparations'][0]['cells']]
        moved=second['epoch_blocks'].pop();moved['protocolID']='other.Protocol'
        first['epoch_blocks'].append(moved)
        rows['EpochBlock'][1].update(parent_id=rows['EpochGroup'][0]['id'],protocol_id=17)
        rows['Protocol'].extend([{'protocol_id':17,'name':'other.Protocol'},
                                 {'protocol_id':18,'name':'no_group_protocol'}])
        for row in rows['EpochGroup']:row['protocol_id']=18
        validate_catalog_identity(source,catalog,7)
        self.assertEqual(len(fetches),10)
        self.assertEqual([item for item in fetches if item[0]=='Protocol'],[('Protocol',3)])
        for group in rows['EpochGroup']:
            group['protocol_id']=13
            with self.assertRaisesRegex(CatalogIdentityConflict,'EpochGroup protocol classification'):
                validate_catalog_identity(source,catalog,7)
            group['protocol_id']=18

    def test_empty_groups_still_validate_protocol_without_any_blocks(self):
        source,catalog,rows,fetches=fixture()
        for cell in source['animals'][0]['preparations'][0]['cells']:
            cell['epoch_groups'][0]['epoch_blocks']=[]
        for kind in ('EpochBlock','Epoch','Response','Stimulus'):rows[kind].clear()
        rows['Protocol'].append({'protocol_id':18,'name':'no_group_protocol'})
        for row in rows['EpochGroup']:row['protocol_id']=18
        validate_catalog_identity(source,catalog,7)
        self.assertEqual([item for item in fetches if item[0]=='Protocol'],[('Protocol',1)])
        rows['EpochGroup'][0]['protocol_id']=13
        with self.assertRaisesRegex(CatalogIdentityConflict,'EpochGroup protocol classification'):
            validate_catalog_identity(source,catalog,7)


if __name__=='__main__':unittest.main()
