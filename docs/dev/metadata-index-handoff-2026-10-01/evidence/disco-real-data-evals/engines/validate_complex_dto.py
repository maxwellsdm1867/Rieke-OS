"""Actual array/wide-integer parity on the previously copied real EAV DBs."""
from compare_real import *
import workspace_tree as tree

def main():
    seal=json.loads((OUT/'real.sqlite.sha256.json').read_bytes())
    index=DiskMetadataIndex.open(OUT/'real.sqlite',seal['generation'],seal['project_uuid'])
    duck=DuckCatalogIndex(OUT/'real.duckdb')
    duck.connection.execute("SET memory_limit='192MB'")
    sql=sqlite3.connect((OUT/'real.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
    candidates=[]
    for field,raw in sql.execute('SELECT f.field_id,v.value_json FROM fields f JOIN field_values v USING(field_no)'):
        value=json.loads(raw)
        candidates.append((field,raw,value))
    tests=[]
    arrays=[item for item in candidates if isinstance(item[2],list) and item[2]]
    wideints=[item for item in candidates if type(item[2]) is int and abs(item[2])>2**53-1]
    if arrays: tests.append(('widest_recorded_array',max(arrays,key=lambda item:len(item[1].encode()))))
    if wideints: tests.append(('integer_above_js_safe_precision',max(wideints,key=lambda item:abs(item[2]))))
    receipt=dict(data_kind='actual real metadata, no synthetic values',tests=[],all_oracles_passed=False)
    try:
        for label,(field,raw,expected) in tests:
            query='''SELECT e.epoch_uuid FROM epochs e JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE f.field_id=? AND v.value_json=? ORDER BY e.epoch_id'''
            ids=[item[0] for item in sql.execute(query,[field,raw])]
            assert ids==[item[0] for item in duck.connection.execute(query,[field,raw]).fetchall()]
            sample=ids[:60]
            measurements={}
            for name,arm in [('sqlite',index),('duckdb',duck)]:
                measurements[name],values=timed(lambda arm=arm:dict(arm.values(ids=sample,fields=[field]).items()))
                for datum in values.values():
                    assert type(datum[field]) is type(expected) and datum[field]==expected
            assert measurements['sqlite']['output_sha256']==measurements['duckdb']['output_sha256']
            row=json.loads(sql.execute('SELECT row_json FROM epochs WHERE epoch_uuid=?',[ids[0]]).fetchone()[0])
            source_detail=index.details[ids[0]]
            _,source_values=tree.catalog([row],{ids[0]:source_detail})
            assert source_values[ids[0]][field]==expected
            detail_measurements={}
            for name,connection in [('sqlite',sql),('duckdb',DecodeSQL(duck.connection))]:
                def get_detail(connection=connection):
                    record=connection.execute('SELECT row_json,detail_blob FROM epochs WHERE epoch_uuid=?',[ids[0]]).fetchone()
                    return Decoder().decode(connection,json.loads(record[0]),record[1])
                detail_measurements[name],datum=timed(get_detail)
                assert datum==source_detail
            assert detail_measurements['sqlite']['output_sha256']==detail_measurements['duckdb']['output_sha256']
            test=dict(label=label,field=field,matching_epochs=len(ids),membership_sha256=digest(ids),sample_epochs=len(sample),
                      value_type=type(expected).__name__,value_json_bytes=len(raw.encode()),
                      array_length=len(expected) if isinstance(expected,list) else None,
                      typed_values_plus_json=measurements,representative_detail_decode_json=detail_measurements)
            receipt['tests'].append(test)
            event('complex_metadata_verified',label=label,field=field,matching_epochs=len(ids),value_json_bytes=len(raw.encode()))
        # Raw detail integers can exceed JavaScript's safe range even when the
        # production query catalog deliberately does not index those leaves.
        def wide_integer_paths(value,path=''):
            result=[]
            if type(value) is int and abs(value)>2**53-1:return [path]
            if isinstance(value,dict):
                for key,child in value.items():result.extend(wide_integer_paths(child,path+'/'+str(key)))
            if isinstance(value,list):
                for ordinal,child in enumerate(value):result.extend(wide_integer_paths(child,path+'/'+str(ordinal)))
            return result
        identity=sql.execute('SELECT epoch_uuid FROM epochs ORDER BY epoch_id LIMIT 1').fetchone()[0]
        expected_detail=index.details[identity]
        paths=wide_integer_paths(expected_detail)
        if paths:
            measurements={}
            for name,connection in [('sqlite',sql),('duckdb',DecodeSQL(duck.connection))]:
                def get_detail(connection=connection):
                    record=connection.execute('SELECT row_json,detail_blob FROM epochs WHERE epoch_uuid=?',[identity]).fetchone()
                    return Decoder().decode(connection,json.loads(record[0]),record[1])
                measurements[name],datum=timed(get_detail)
                assert canonical(datum)==canonical(expected_detail)
                assert wide_integer_paths(datum)==paths
            assert measurements['sqlite']['output_sha256']==measurements['duckdb']['output_sha256']
            receipt['tests'].append(dict(label='raw_detail_integers_above_js_safe_precision',paths=paths,
                indexed_value_support=False,note='Observed raw detail ticks are excluded from native query fields; preserved in exact metadata DTO.',
                detail_sql_decode_json=measurements))
        receipt['indexed_wide_integer_candidates']=len(wideints)
        receipt['all_oracles_passed']=True
        receipt['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        (OUT/'complex-dto-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    finally:
        sql.close();duck.close();index.close()

if __name__=='__main__':main()
