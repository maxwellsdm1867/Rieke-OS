"""Stat-only development inventory. Explicit serial opt-in required for large seals."""
import hashlib
import json
from pathlib import Path
import sqlite3

SOURCE_SHA='0427f38b01fad730941c3161d67a4fd6ae75988344527648cc066771b983147e'
REPLAY_SHA='7e03e05e97885505f227e1b0938b34f303229db90ddcdd1f7e40f40d6b55e2b6'


def inventory(paths):
    return [dict(path=str(p),exists=Path(p).exists(),
                 bytes=Path(p).stat().st_size if Path(p).is_file() else None,
                 seal_status='unverified; stat is not integrity or generation proof') for p in paths]


def verify(source, replay, receipt, *, serial_authorized=False):
    if not serial_authorized: raise ValueError('Heavy seals/replay validation deferred; serial authorization required')
    expected=json.loads(Path(receipt).read_bytes())
    if (expected['source_sha256'],expected['base_sha256'],expected['epochs'],expected['source_epochs'],
        expected['full_copies'],expected['remainder_epochs'],expected['fields'],expected['epoch_value_links']) != (
            SOURCE_SHA,REPLAY_SHA,1000000,2781,359,1621,140,77107863):
        raise ValueError('Wrong required real-million replay receipt; establish new paired baseline')
    # Fail before hashing if files missing. Preserve before/after file identity.
    stats={str(p):(Path(p).stat().st_ino,Path(p).stat().st_size,Path(p).stat().st_mtime_ns) for p in (source,replay)}
    for path,seal in ((source,SOURCE_SHA),(replay,REPLAY_SHA)):
        hasher=hashlib.sha256()
        with open(path,'rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):hasher.update(chunk)
        if hasher.hexdigest()!=seal: raise ValueError('Required corpus seal mismatch')
    if Path(str(replay)+'-wal').exists(): raise ValueError('Replay must be immutable standalone file')
    with sqlite3.connect(Path(replay).resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as con:
        counts={table:con.execute('SELECT count(*) FROM '+table).fetchone()[0]
                for table in ('epochs','fields','epoch_values')}
        meta=dict(con.execute('SELECT key,value FROM meta'))
    if counts != dict(epochs=1000000,fields=140,epoch_values=77107863): raise ValueError('Replay counts differ')
    def decoded(value):
        try:return json.loads(value)
        except (ValueError,TypeError):return value
    for key in ('generation','project_uuid'):
        if decoded(meta[key])!=expected[key]:raise ValueError('Replay generation differs')
    if any(stats[str(p)]!=(Path(p).stat().st_ino,Path(p).stat().st_size,Path(p).stat().st_mtime_ns)
           for p in (source,replay)):raise ValueError('Corpus changed during verification')
    return dict(status='seals_counts_generation_verified',source_sha256=SOURCE_SHA,replay_sha256=REPLAY_SHA,
                counts=counts,lineage_receipt=expected,limitations=[
                    'Exact replay seal binds preserved namespace/whole-block tail. Streaming native lineage/value oracle still required.',
                    'Repeated scientific cardinality; no new readable waveform sources; native eligibility remains a separate gate.'])
