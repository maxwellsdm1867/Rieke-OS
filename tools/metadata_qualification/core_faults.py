"""Independent refusal expectations over newly constructed disposable core assets."""
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from core_adapter import CoreAdapter
from disco.metadata.typed_index import TypedMetadataIndex


def changed(path):
    stat=path.stat();os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns+1000000))


def refused(call, expected='ValueError'):
    try:call()
    except Exception as error:
        if type(error).__name__!=expected:raise AssertionError(f'Unexpected fault: {error!r}')
        return
    raise AssertionError('Generation/cancellation fault published successful output')


def qualify_faults(truth):
    passed=[]
    with tempfile.TemporaryDirectory(prefix='rieke-core-faults-') as folder:
        root=Path(folder)
        for name in ('identity','source','during','seal','cancel'):
            directory=root/name;directory.mkdir()
            adapter=CoreAdapter(directory/'typed.sqlite',truth.fixture());reader=adapter.reader
            try:
                if reader.count()!=len(truth.ids):raise AssertionError('Fault fixture count differs')
                if name=='identity':
                    refused(lambda:TypedMetadataIndex(reader.path,expected_generation='foreign'))
                    passed.append('wrong-metadata-generation')
                    refused(lambda:TypedMetadataIndex(reader.path,expected_project_uuid='foreign'))
                    passed.append('wrong-project')
                elif name=='source':
                    changed(reader.source_path)
                    refused(lambda:reader.count());passed.append('source-change-before-query')
                    refused(lambda:TypedMetadataIndex.open_verified(reader));passed.append('source-change-before-verified-clone')
                elif name=='during':
                    original=reader._summaries
                    def summaries(*args,**kwargs):
                        result=original(*args,**kwargs);changed(reader.source_path);return result
                    with patch.object(reader,'_summaries',summaries):
                        refused(lambda:reader.preview(facet_fields=['parameters/mixed']))
                    passed.append('source-change-during-preview-before-publication')
                elif name=='seal':
                    changed(Path(str(reader.path)+'.sha256.json'))
                    refused(lambda:reader.count());passed.append('sidecar-seal-change')
                else:
                    reader.cancel();refused(lambda:reader.count(),'QueryCancelled')
                    reader.reset_cancel()
                    if reader.count()!=len(truth.ids):raise AssertionError('Cancellation recovery differs')
                    passed.append('cancellation-refused-and-recovered')
            finally:adapter.close()
    return dict(status='passed',checks=passed,corpus='12-epoch disposable native fixture',
                source_policy_authority=False,annotation_generation=False,integrated_service=False,real_million=False)
