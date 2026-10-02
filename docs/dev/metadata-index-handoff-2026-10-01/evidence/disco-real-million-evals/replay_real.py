"""Exact real-record replay into the current seven-table metadata representation.

Owned experiment only. No waveforms, native app publication, or new scientific
values. Structural acquisition identities are deterministically namespaced.
"""
import argparse, collections, hashlib, json, os, re, resource, shutil, signal
import sqlite3, subprocess, sys, threading, time, uuid, zlib
from pathlib import Path

OUT=Path('/private/tmp/disco-real-million-20261001')
SOURCE=Path('/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite')
sys.path.insert(0,'/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python')
from workspace_metadata_objects import Decoder, canonical

START=time.monotonic()
UUID_PATTERN=re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{64}')
NAMESPACE=uuid.UUID('8f0a5eed-375e-5ddb-8a57-6d59fce17b28')
STRUCTURAL={'epoch','cell','block','group'}
LAST_AVAILABLE_RAM=None
def available_ram():
    raw=subprocess.check_output(['/usr/bin/vm_stat'],text=True,timeout=5)
    page_size=int(re.search(r'page size of (\d+) bytes',raw)[1])
    pages={name:int(number) for name,number in re.findall(r'^(Pages [a-z ]+):\s+(\d+)\.',raw,re.M)}
    # Darwin's inactive/speculative pages can be reclaimed. Do not count
    # compressor storage or all file-backed pages a second time.
    return page_size*sum(pages.get(k,0) for k in ('Pages free','Pages inactive','Pages speculative'))
def watch_resources():
    global LAST_AVAILABLE_RAM
    while True:
        try:
            LAST_AVAILABLE_RAM=available_ram()
            rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            free=shutil.disk_usage(OUT).free
            if rss>1024**3 or free<4*1024**3 or LAST_AVAILABLE_RAM<768*1024**2:
                emit('resource_guard_stop',peak_rss_bytes=rss,free_disk_bytes=free,available_ram_bytes=LAST_AVAILABLE_RAM)
                os._exit(91)
        except Exception as error:
            emit('resource_guard_error',error=str(error));os._exit(92)
        time.sleep(2)
def digest_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''): h.update(block)
    return h.hexdigest()
def emit(event,**kw):
    print(json.dumps(dict(event=event,elapsed_seconds=time.monotonic()-START,**kw)),flush=True)
def check_guard(cap):
    if time.monotonic()-START>cap: raise TimeoutError('Replay construction wall-clock cap')
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if rss>1024**3: raise MemoryError('Replay construction 1GiB RSS cap')
    if shutil.disk_usage(OUT).free<4*1024**3: raise OSError('Replay construction 4GiB free-disk floor')
def rewrite_text(raw,mapping):
    return UUID_PATTERN.sub(lambda m:mapping.get(m[0],m[0]),raw)
def text_template(raw,identities):
    parts=[]; previous=0
    for match in UUID_PATTERN.finditer(raw):
        if match[0] not in identities: continue
        parts.extend((raw[previous:match.start()],match[0]));previous=match.end()
    parts.append(raw[previous:]);return tuple(parts)
def render_template(parts,mapping):
    return ''.join(mapping.get(part,part) if i%2 else part for i,part in enumerate(parts))
def rewrite(value,mapping):
    if isinstance(value,str): return rewrite_text(value,mapping)
    if isinstance(value,list): return [rewrite(v,mapping) for v in value]
    if isinstance(value,dict): return {rewrite_text(k,mapping):rewrite(v,mapping) for k,v in value.items()}
    return value
def v1_fingerprint(detail):
    return hashlib.sha256(json.dumps({k:detail[k] for k in ('parameters','properties','attributes')},sort_keys=True,allow_nan=False).encode()).hexdigest()
def mapped_row(row,document,mapping):
    result=rewrite(row,mapping)
    result['metadata_hash']=v1_fingerprint(rewrite(document['inline'],mapping))
    return result
def identity_map(rows,sources,replica):
    identities=set()
    for r in rows:
        row=r['row']
        identities.update(row[k] for k in ('epoch_uuid','cell_uuid','block_uuid','group_uuid') if row.get(k))
    mapping={v:str(uuid.uuid5(NAMESPACE,f'{replica}/{v}')) for v in identities}
    mapping.update({s:hashlib.sha256(f'real-record-replay/{replica}/{s}'.encode()).hexdigest() for s in sources})
    return mapping
def select_tail(rows,count):
    blocks=collections.defaultdict(list)
    for row in rows: blocks[row['row']['block_uuid']].append(row['epoch_id'])
    # Descending blocks minimize the number of partial-copy acquisitions.
    reachable={0:()}
    for block,ids in sorted(blocks.items(),key=lambda item:(-len(item[1]),item[0])):
        for total,chosen in list(reachable.items()):
            nxt=total+len(ids)
            if nxt<=count and nxt not in reachable: reachable[nxt]=chosen+(block,)
        if count in reachable: break
    if count not in reachable: raise ValueError('No exact whole-block remainder')
    picked=reachable[count]
    return set(i for b in picked for i in blocks[b]),list(picked)
def load():
    source=sqlite3.connect(f'file:{SOURCE}?mode=ro&immutable=1',uri=True)
    seal=json.loads(Path(str(SOURCE)+'.sha256.json').read_text())
    assert digest_file(SOURCE)==seal['sha256']
    rows=[]
    for epoch_id,epoch_uuid,source_sha,cell_uuid,row_json,blob,fingerprint in source.execute('SELECT * FROM epochs ORDER BY epoch_id'):
        row=json.loads(row_json); document=json.loads(zlib.decompress(blob))
        assert row['metadata_hash']==v1_fingerprint(document['inline'])
        rows.append(dict(epoch_id=epoch_id,row=row,row_json=row_json,document=document,fingerprint=fingerprint,
            inline_json=canonical(document['inline']).decode(),v1_json=json.dumps({k:document['inline'][k] for k in ('parameters','properties','attributes')},sort_keys=True,allow_nan=False)))
    objects=[]
    for object_id,source_sha,kind,object_uuid,payload,sha in source.execute('SELECT * FROM metadata_objects ORDER BY object_id'):
        raw=zlib.decompress(payload); assert hashlib.sha256(raw).digest()==sha
        objects.append((object_id,source_sha,kind,object_uuid,raw.decode()))
    sources=dict(source.execute('SELECT * FROM sources'))
    return source,seal,rows,objects,sources
def build(path,target,cap):
    check_guard(cap)
    source,seal,rows,objects,sources=load()
    identities=set(identity_map(rows,sources,0))
    for r in rows:
        for key in ('row_json','inline_json','v1_json'):
            r[key+'_template']=text_template(r[key],identities)
    source_templates={s:text_template(raw,identities) for s,raw in sources.items()}
    object_templates={oid:text_template(raw,identities) for oid,s,kind,ouuid,raw in objects}
    full,remainder=divmod(target,len(rows)); tail,tail_blocks=select_tail(rows,remainder)
    n_objects=max(x[0] for x in objects)
    structural_numbers=[no for no,field in source.execute('SELECT field_no,field_id FROM fields') if field in STRUCTURAL]
    placeholders=','.join('?' for _ in structural_numbers)
    structural_values=source.execute(f'SELECT value_id,field_no,value_json FROM field_values WHERE field_no IN ({placeholders}) ORDER BY value_id',structural_numbers).fetchall()
    n_structural=len(structural_values); max_value=source.execute('SELECT MAX(value_id) FROM field_values').fetchone()[0]
    path.unlink(missing_ok=True)
    c=sqlite3.connect(str(path),uri=True)
    c.execute('PRAGMA journal_mode=OFF'); c.execute('PRAGMA synchronous=OFF')
    c.execute('PRAGMA cache_size=-65536'); c.execute('PRAGMA temp_store=FILE')
    c.execute('ATTACH DATABASE ? AS original',(f'file:{SOURCE}?mode=ro&immutable=1',))
    for sql, in source.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY rowid"):
        c.execute(sql)
    c.execute('INSERT INTO fields SELECT * FROM original.fields')
    c.execute(f'INSERT INTO field_values SELECT * FROM original.field_values WHERE field_no NOT IN ({placeholders})',structural_numbers)
    c.execute('CREATE TEMP TABLE structural_value_map(old_id INTEGER PRIMARY KEY,ordinal INTEGER NOT NULL)')
    c.executemany('INSERT INTO structural_value_map VALUES(?,?)',[(value[0],i+1) for i,value in enumerate(structural_values)])
    c.execute('CREATE TEMP TABLE tail_ids(epoch_id INTEGER PRIMARY KEY)')
    c.executemany('INSERT INTO tail_ids VALUES(?)',[(v,) for v in sorted(tail)])
    insert_seconds=0
    for replica in range(full+bool(remainder)):
        check_guard(cap); begin=time.monotonic()
        selected=rows if replica<full else [r for r in rows if r['epoch_id'] in tail]
        mapping=identity_map(rows,sources,replica)
        object_offset=replica*n_objects; epoch_offset=replica*len(rows)
        value_offset=max_value+replica*n_structural
        # Source metadata and ancestor payloads retain all original values;
        # hashes and UUID ownership only identify the replay namespace.
        c.executemany('INSERT INTO sources VALUES(?,?)',[(mapping[s],render_template(source_templates[s],mapping)) for s in sources])
        object_batch=[]
        for oid,s,kind,ouuid,raw in objects:
            rewritten=render_template(object_templates[oid],mapping).encode()
            object_batch.append((oid+object_offset,mapping[s],kind,mapping[ouuid],zlib.compress(rewritten),hashlib.sha256(rewritten).digest()))
        c.executemany('INSERT INTO metadata_objects VALUES(?,?,?,?,?,?)',object_batch)
        c.executemany('INSERT INTO field_values VALUES(?,?,?)',[(value_offset+i+1,no,rewrite_text(raw,mapping)) for i,(_,no,raw) in enumerate(structural_values)])
        batch=[]
        for r in selected:
            original_row=r['row']; document=r['document']
            mapped_inline=render_template(r['inline_json_template'],mapping)
            mapped_objects={kind:oid+object_offset for kind,oid in document['objects'].items()}
            # Canonical encoding is exactly the native Encoder wire document.
            compact=b'{"inline":'+mapped_inline.encode()+b',"objects":'+canonical(mapped_objects)+b',"version":1}'
            v1_hash=hashlib.sha256(render_template(r['v1_json_template'],mapping).encode()).hexdigest()
            row_json=render_template(r['row_json_template'],mapping).replace(original_row['metadata_hash'],v1_hash)
            # Derived experimental fingerprint: authoritative scientific input
            # fingerprint plus replay namespace; not a native app publication.
            fingerprint=hashlib.sha256(f"experimental-replay/{replica}/{r['fingerprint']}".encode()).hexdigest()
            batch.append((r['epoch_id']+epoch_offset,mapping[original_row['epoch_uuid']],mapping[original_row['source_sha256']],mapping[original_row['cell_uuid']],row_json,zlib.compress(compact,1),fingerprint))
        c.executemany('INSERT INTO epochs VALUES(?,?,?,?,?,?,?)',batch)
        predicate='' if replica<full else ' WHERE ev.epoch_id IN (SELECT epoch_id FROM tail_ids)'
        c.execute('INSERT INTO epoch_values SELECT ev.epoch_id+?,ev.field_no,CASE WHEN m.ordinal IS NULL THEN ev.value_id ELSE m.ordinal+? END FROM original.epoch_values ev LEFT JOIN structural_value_map m ON m.old_id=ev.value_id'+predicate,(epoch_offset,value_offset))
        c.commit(); insert_seconds+=time.monotonic()-begin
        if replica<2 or replica%20==19 or replica==full:
            emit('replica_complete',replica=replica,epochs=c.execute('SELECT COUNT(*) FROM epochs').fetchone()[0],bytes=path.stat().st_size,replica_seconds=time.monotonic()-begin,free_disk_bytes=shutil.disk_usage(OUT).free,available_ram_bytes=LAST_AVAILABLE_RAM,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    begin=time.monotonic(); check_guard(cap)
    c.set_progress_handler(lambda:int(time.monotonic()-START>cap or shutil.disk_usage(OUT).free<4*1024**3),500000)
    for sql, in source.execute("SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY rowid"):
        emit('index_begin',sql=sql); c.execute(sql)
    index_seconds=time.monotonic()-begin
    generation=hashlib.sha256(f'{seal["sha256"]}/{target}/replay-v1'.encode()).hexdigest()
    for key,value in dict(format=3,generation=generation,project_uuid=seal['project_uuid'],complete=True).items():
        c.execute('INSERT INTO meta VALUES(?,?)',(key,json.dumps(value)))
    c.commit(); assert c.execute('SELECT COUNT(*) FROM epochs').fetchone()[0]==target
    assert c.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    link_count=c.execute('SELECT COUNT(*) FROM epoch_values').fetchone()[0]
    c.close()
    assert digest_file(SOURCE)==seal['sha256']
    checksum=digest_file(path)
    receipt=dict(source_sha256=seal['sha256'],base_sha256=checksum,epochs=target,full_copies=full,remainder_epochs=remainder,remainder_blocks=tail_blocks,fields=140,epoch_value_links=link_count,source_epochs=len(rows),source_ancestors=len(objects),generation=generation,project_uuid=seal['project_uuid'],bytes=path.stat().st_size,insert_seconds=insert_seconds,index_seconds=index_seconds,total_seconds=time.monotonic()-START,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,source_unchanged=True,experimental_fingerprint=True,limitations=['Real-record replay: scientific parameter cardinalities and timestamps repeat; not one million independent acquired epochs.','Seven production tables and production indices, experimental construction; native full-detail fingerprints and upfront full-field catalogs are not produced.','Source paths are audit provenance; copied replay IDs and paths do not identify readable new H5 traces.','Final remainder comprises whole source blocks; copied source counts remain original provenance for a partial source replay.'])
    Path(str(path)+'.sha256.json').write_text(json.dumps(dict(format=3,generation=generation,project_uuid=seal['project_uuid'],sha256=checksum),indent=2)+'\n')
    path.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    source.close(); emit('build_complete',**receipt)
    return receipt
def validate_fixture(path):
    source,seal,rows,objects,sources=load()
    target=sqlite3.connect(f'file:{path}?mode=ro&immutable=1',uri=True)
    src_decode=Decoder(); dst_decode=Decoder(); checked=0
    # All actual DTOs in both copies, one at a time; no 187MB dictionary.
    for replica in (0,1):
        mapping=identity_map(rows,sources,replica)
        for r in rows:
            row_json,blob=target.execute('SELECT row_json,detail_blob FROM epochs WHERE epoch_id=?',(r['epoch_id']+replica*len(rows),)).fetchone()
            row=json.loads(row_json)
            assert row==mapped_row(r['row'],r['document'],mapping)
            source_blob=source.execute('SELECT detail_blob FROM epochs WHERE epoch_id=?',(r['epoch_id'],)).fetchone()[0]
            expected=rewrite(src_decode.decode(source,r['row'],source_blob),mapping)
            assert dst_decode.decode(target,row,blob)==expected
            assert row['metadata_hash']==v1_fingerprint(expected)
            links=target.execute('SELECT f.field_id,v.value_json FROM epoch_values ev JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE epoch_id=? ORDER BY ev.field_no',(r['epoch_id']+replica*len(rows),)).fetchall()
            originals=source.execute('SELECT f.field_id,v.value_json FROM epoch_values ev JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE epoch_id=? ORDER BY ev.field_no',(r['epoch_id'],)).fetchall()
            assert links==[(field,rewrite_text(raw,mapping) if field in STRUCTURAL else raw) for field,raw in originals]
            checked+=1
    result=dict(all_full_DTOs_and_EAV_rows_equal=True,verified_epochs=checked,native_decoder_used=True,source_unchanged=digest_file(SOURCE)==seal['sha256'])
    (OUT/'fixture-oracle.json').write_text(json.dumps(result,indent=2)+'\n'); emit('fixture_oracle',**result)
def main():
    p=argparse.ArgumentParser();p.add_argument('--epochs',type=int,default=5562);p.add_argument('--cap',type=int,default=300);p.add_argument('--fixture',action='store_true'); args=p.parse_args()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('Replay hard process cap')));signal.alarm(args.cap+30)
    OUT.mkdir(parents=True,exist_ok=True)
    threading.Thread(target=watch_resources,daemon=True).start()
    path=OUT/('fixture.sqlite' if args.fixture else 'base.sqlite')
    build(path,args.epochs,args.cap)
    if args.fixture:validate_fixture(path)
if __name__=='__main__':main()
