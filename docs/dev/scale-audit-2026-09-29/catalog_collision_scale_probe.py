"""Disposable native MySQL collision-lookup plan, timing and transaction proof.

Never accepts an existing project or connection. No acquisition schema is altered;
all benchmark data lives in throwaway probe tables in a fresh temporary project.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import tempfile
import time
import traceback
from types import SimpleNamespace

from workspace_projects import create_project
from workspace_native_mysql import ensure_native_database, stop_native_database, connection_parameters
from recording_workspace import connect,assert_new_catalog_identities


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--epochs',type=int,default=100000)
    parser.add_argument('--baseline-batches',type=int,default=5)
    args=parser.parse_args()
    if args.output.exists():parser.error('Use a fresh output file')
    if not 1000<=args.epochs<=1000000:parser.error('epochs must be 1000–1000000')
    if not 1<=args.baseline_batches<=100:parser.error('baseline-batches must be 1–100')
    temporary=Path(tempfile.mkdtemp(prefix='rieke-collision-scale-'))
    report={'epochs':args.epochs,'database_scope':'fresh disposable native MySQL only',
        'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limitations':['Lookup benchmark only; not full parser/population/import latency.',
            'Baseline full100k time is extrapolated from measured disjoint200-identity batches; not an observed full baseline run.',
            'This proves the proposed scratch-table algorithm, not product integration.']}
    project=dj=None;clean=False
    try:
        project=Path(create_project(temporary/'projects','Disposable collision probe')['path'])
        ensure_native_database(project);dj=connect({'kind':'native-project'},project_dir=project)
        from retinanalysis.config import schema as catalog
        conn=catalog.schema.connection
        report['mysql_version']=conn.query('SELECT VERSION()').fetchone()[0]
        report['catalog_columns']={};report['catalog_indexes']={}
        for kind in ('Animal','Preparation','Cell','EpochGroup','EpochBlock','Epoch','Response','Stimulus'):
            table=getattr(catalog,kind)
            report['catalog_columns'][kind]=conn.query(f'SHOW FULL COLUMNS FROM {table.full_table_name} WHERE Field=%s',('h5_uuid',),as_dict=True).fetchone()
            report['catalog_indexes'][kind]=conn.query(f'SHOW INDEX FROM {table.full_table_name}',as_dict=True).fetchall()
        collation=report['catalog_columns']['Epoch']['Collation'];charset=collation.split('_',1)[0]
        assert re.fullmatch(r'[A-Za-z0-9_]+',collation)
        conn.query(f'CREATE TABLE `schema`.`identity_scan_probe` (id BIGINT PRIMARY KEY AUTO_INCREMENT,h5_uuid VARCHAR(255) CHARACTER SET {charset} COLLATE {collation} NOT NULL) ENGINE=InnoDB')
        # Candidate index is declared before starting the import transaction.
        conn.query(f'CREATE TEMPORARY TABLE `schema`.`identity_candidates_probe` (h5_uuid VARCHAR(255) CHARACTER SET {charset} COLLATE {collation} NOT NULL, KEY candidate_uuid(h5_uuid)) ENGINE=InnoDB')
        conn.query('CREATE TABLE `schema`.`identity_rollback_probe` (id INT PRIMARY KEY) ENGINE=InnoDB')
        def insert(table,values,batch=1000):
            for offset in range(0,len(values),batch):
                block=values[offset:offset+batch]
                conn.query(f'INSERT INTO {table} (h5_uuid) VALUES '+','.join(['(%s)']*len(block)),tuple(block))
        incoming=[f'incoming-{n:09d}' for n in range(args.epochs)]
        with conn.transaction:insert('`schema`.`identity_scan_probe`',[f'catalog-{n:09d}' for n in range(args.epochs)])
        baseline='SELECT h5_uuid FROM `schema`.`identity_scan_probe` WHERE '+' OR '.join(['h5_uuid=%s']*200)+' LIMIT 1'
        candidate='SELECT existing.h5_uuid FROM `schema`.`identity_scan_probe` AS existing STRAIGHT_JOIN `schema`.`identity_candidates_probe` AS incoming FORCE INDEX(candidate_uuid) ON incoming.h5_uuid=existing.h5_uuid LIMIT 1'
        report['baseline_explain']=conn.query('EXPLAIN FORMAT=JSON '+baseline,tuple(incoming[:200])).fetchone()[0]
        samples=[]
        for n in range(args.baseline_batches):
            block=incoming[n*200:n*200+200]
            if len(block)!=200:break
            start=time.perf_counter();assert conn.query(baseline,tuple(block)).fetchone() is None;samples.append(time.perf_counter()-start)
        report['baseline']={'batch_size':200,'measured_batches':len(samples),'samples_seconds':samples,'median_batch_seconds':statistics.median(samples),
            'full_batches_required':(len(incoming)+199)//200,'extrapolated_total_seconds':statistics.median(samples)*((len(incoming)+199)//200)}
        assert conn.query("SELECT GET_LOCK('recording_workspace_import',30)").fetchone()[0]==1
        start=time.perf_counter()
        with conn.transaction:
            insert('`schema`.`identity_candidates_probe`',incoming)
            report['candidate_staging_seconds']=time.perf_counter()-start
            report['candidate_explain']=conn.query('EXPLAIN FORMAT=JSON '+candidate).fetchone()[0]
            report['candidate_analyze']=conn.query('EXPLAIN ANALYZE '+candidate).fetchone()[0]
            samples=[]
            for _ in range(3):
                at=time.perf_counter();assert conn.query(candidate).fetchone() is None;samples.append(time.perf_counter()-at)
            report['candidate_lookup']={'samples_seconds':samples,'median_seconds':statistics.median(samples)}
        report['candidate_stage_plus_median_seconds']=report['candidate_staging_seconds']+report['candidate_lookup']['median_seconds']
        # A second connection cannot access this connection's scratch table.
        import pymysql
        other=pymysql.connect(**connection_parameters(project))
        try:
            try:
                with other.cursor() as cursor:cursor.execute('SELECT COUNT(*) FROM `schema`.`identity_candidates_probe`')
            except pymysql.err.ProgrammingError as error:report['connection_local']=error.args[0]==1146
            else:report['connection_local']=False
        finally:other.close()
        report['collation_cases']=[]
        for index,name in enumerate(dict.fromkeys([collation,'utf8mb4_bin','utf8mb4_unicode_ci','utf8mb4_0900_ai_ci'])):
            case_charset=name.split('_',1)[0]
            source=f'`schema`.`identity_collation_{index}`';temp=f'`schema`.`identity_temp_{index}`'
            conn.query(f'CREATE TABLE {source} (h5_uuid VARCHAR(255) CHARACTER SET {case_charset} COLLATE {name} NOT NULL) ENGINE=InnoDB')
            conn.query(f'CREATE TEMPORARY TABLE {temp} (h5_uuid VARCHAR(255) CHARACTER SET {case_charset} COLLATE {name} NOT NULL,KEY candidate_uuid(h5_uuid)) ENGINE=InnoDB')
            for stored,value in [('ABC','abc'),('résumé','resume'),('trail','trail '),("quote'\\value","quote'\\value"),('plain','other')]:
                with conn.transaction:
                    conn.query(f'DELETE FROM {source}');conn.query(f'DELETE FROM {temp}')
                    insert(source,[stored]);insert(temp,[value])
                    original=conn.query(f'SELECT h5_uuid FROM {source} WHERE h5_uuid=%s LIMIT1'.replace('LIMIT1','LIMIT 1'),(value,)).fetchone()
                    joined=conn.query(f'SELECT existing.h5_uuid FROM {source} existing STRAIGHT_JOIN {temp} incoming FORCE INDEX(candidate_uuid) ON incoming.h5_uuid=existing.h5_uuid LIMIT 1').fetchone()
                    report['collation_cases'].append({'collation':name,'stored':stored,'incoming':value,'original':original,'candidate':joined,'equal':original==joined})
            conn.query(f'DROP TEMPORARY TABLE {temp}')
        # Lookup/staging cannot commit a preceding write when later work fails.
        class RollbackProbe(Exception):pass
        try:
            with conn.transaction:
                conn.query('INSERT INTO `schema`.`identity_rollback_probe` VALUES (1)')
                conn.query('DELETE FROM `schema`.`identity_candidates_probe`')
                insert('`schema`.`identity_candidates_probe`',[f'catalog-{args.epochs-1:09d}'])
                assert conn.query(candidate).fetchone() is not None
                raise RollbackProbe()
        except RollbackProbe:pass
        report['transaction_rollback_preserved']=conn.query('SELECT COUNT(*) FROM `schema`.`identity_rollback_probe`').fetchone()[0]==0
        report['candidate_insert_rollback_preserved']=conn.query('SELECT COUNT(*) FROM `schema`.`identity_candidates_probe`').fetchone()[0]==args.epochs
        report['source_row_count_preserved']=conn.query('SELECT COUNT(*) FROM `schema`.`identity_scan_probe`').fetchone()[0]==args.epochs
        report['advisory_lock_still_owned']=conn.query("SELECT IS_USED_LOCK('recording_workspace_import')=CONNECTION_ID()").fetchone()[0]==1
        # Exercise the production helper, including its real table metadata,
        # ownership checks and bounded parameter batches, in this same fixture.
        from workspace_catalog_collision import CatalogCollisionLookup,KINDS
        import workspace_catalog_collision as helper_module
        report['helper_sha256']=hashlib.sha256(Path(helper_module.__file__).read_bytes()).hexdigest()
        relation=dj.FreeTable(conn,'`schema`.`identity_scan_probe`')
        probe_catalog=SimpleNamespace(schema=SimpleNamespace(connection=conn),**{kind:relation for kind in KINDS})
        with CatalogCollisionLookup(probe_catalog) as lookup:
            report['helper_temp_tables']=len(lookup.temporary)
            try:
                with conn.transaction:
                    conn.query('INSERT INTO `schema`.`identity_rollback_probe` VALUES (2)')
                    at=time.perf_counter()
                    assert lookup.first_collision('Epoch',incoming) is None
                    report['helper_100000_lookup_seconds']=time.perf_counter()-at
                    expected=f'catalog-{args.epochs-1:09d}'
                    assert lookup.first_collision('Epoch',[*incoming,expected])==expected
                    raise RollbackProbe()
            except RollbackProbe:pass
            report['helper_rollback_preserved']=conn.query('SELECT COUNT(*) FROM `schema`.`identity_rollback_probe`').fetchone()[0]==0
            source={'animals':[{'uuid':'incoming-animal','preparations':[{'uuid':'incoming-preparation','cells':[
                {'uuid':'incoming-cell','epoch_groups':[{'uuid':'incoming-group','epoch_blocks':[
                    {'uuid':'incoming-block','epochs':[{'uuid':key} for key in incoming]}]}]}]}]}]}
            with conn.transaction:
                at=time.perf_counter();assert_new_catalog_identities(source,probe_catalog,lookup=lookup)
                report['integrated_guard_100000_seconds']=time.perf_counter()-at
            source['animals'][0]['preparations'][0]['cells'][0]['uuid']=expected
            from workspace_catalog_identity import CatalogIdentityConflict
            try:
                with conn.transaction:
                    conn.query('INSERT INTO `schema`.`identity_rollback_probe` VALUES (3)')
                    assert_new_catalog_identities(source,probe_catalog,lookup=lookup)
            except CatalogIdentityConflict as error:
                report['integrated_guard_collision_rejected']=(error.conflict['kind']=='source_uuid_collision' and error.conflict['acquisition_uuid']==expected)
            else:report['integrated_guard_collision_rejected']=False
            report['integrated_guard_rollback_preserved']=conn.query('SELECT COUNT(*) FROM `schema`.`identity_rollback_probe`').fetchone()[0]==0
        report['helper_cleanup_complete']=not lookup.temporary
        conn.query('DROP TEMPORARY TABLE `schema`.`identity_candidates_probe`')
        conn.query("SELECT RELEASE_LOCK('recording_workspace_import')")
    except Exception as error:
        report['runtime_error']={'type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc()};print(traceback.format_exc(),flush=True)
    finally:
        if dj is not None:
            try:dj.conn().close()
            except Exception:pass
        if project is not None:
            try:clean=stop_native_database(project);report['clean_shutdown']=clean
            except Exception as error:report['shutdown_error']=str(error)
        if clean:
            import shutil
            shutil.rmtree(temporary);report['temporary_project_removed']=True
        else:report['preserved_project']=str(temporary)
        report['passed']=not report.get('runtime_error') and clean and all(report.get(key) is True for key in ('connection_local','transaction_rollback_preserved','candidate_insert_rollback_preserved','source_row_count_preserved','advisory_lock_still_owned','helper_rollback_preserved','helper_cleanup_complete','integrated_guard_collision_rejected','integrated_guard_rollback_preserved')) and all(row['equal'] for row in report.get('collation_cases',[]))
        args.output.write_text(json.dumps(report,indent=2,default=str)+'\n')
        print(json.dumps({key:report[key] for key in ('passed','baseline','candidate_stage_plus_median_seconds','runtime_error') if key in report}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
