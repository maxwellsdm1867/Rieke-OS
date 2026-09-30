"""Isolate ChainMap source dispatch during metadata-index generation rebuild.

All rows, SQLite, and OS-stat files are disposable synthetic fixtures.
"""
from collections import ChainMap
from pathlib import Path
import json
import platform
import random
import statistics
import tempfile
import time
from unittest.mock import patch
import workspace_disk_index as disk
from workspace_disk_index import DiskMetadataIndex


def run():
    output={'fixture':'synthetic, no H5 or MySQL','epochs':1000,'cells':10,
        'python':platform.python_version(),'measurements':[]}
    rows=[dict(epoch_uuid=f'e-{i}',cell_uuid=f'c-{i//100}',cell_label='Cell',date='2026-09-29',
        source_sha256='s',protocol_name='Synthetic',block_uuid='b',group_uuid='g') for i in range(1000)]
    details={row['epoch_uuid']:{'parameters':{'axis':i%7}} for i,row in enumerate(rows)}
    ids=[row['epoch_uuid'] for row in rows]
    random.Random(1).shuffle(ids)
    with tempfile.TemporaryDirectory(prefix='rieke-source-dispatch-') as folder:
        index=DiskMetadataIndex.build(Path(folder)/'index.sqlite',rows,details,[{'source_sha256':'s'}],'audit','project')
        for scopes in (1,10,100,500):
            memberships=[dict.fromkeys(ids[i::scopes]) for i in range(scopes)]
            chain=ChainMap(*(disk._ScopedDetails(index.details,bucket) for bucket in memberships))
            start=time.perf_counter()
            with patch.object(index,'_check',wraps=index._check) as checks:
                for identity in ids: chain[identity]
                calls=checks.call_count
            elapsed=time.perf_counter()-start
            output['measurements'].append(dict(source_scopes=scopes,lookup_seconds=elapsed,
                index_stat_checks=calls,notes='Mock call recording adds timing overhead; structural call count is exact.'))
            # Timings without instrumentation; same detail cache bounded to 64.
            elapsed=[]
            for repeat in range(3):
                start=time.perf_counter()
                for identity in ids: chain[identity]
                elapsed.append(time.perf_counter()-start)
            output['measurements'][-1].update(uninstrumented_seconds=elapsed,median_seconds=statistics.median(elapsed))
    return output


if __name__=='__main__':
    result=run();path=Path('docs/dev/scale-audit-2026-09-29/backend-source-dispatch.json')
    path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
