"""Adapter for committed full typed core; source truth never imports this module."""
from pathlib import Path
from disco.metadata.disk_index import DiskMetadataIndex
from disco.metadata.typed_index import build, TypedMetadataIndex


class CoreAdapter:
    def __init__(self, path, fixture):
        path=Path(path);source=path.with_name('native.sqlite')
        native=DiskMetadataIndex.build(source,fixture['rows'],fixture['details'],fixture['sources'],
                                       'qualification-v1','isolated')
        try:
            self.build_receipt=build(source,path,expected_generation='qualification-v1',
                                     expected_project_uuid='isolated',max_seconds=30,
                                     min_free_gib=0,max_rss_gib=1)
            self.reader=TypedMetadataIndex(path,expected_generation='qualification-v1',
                                           expected_project_uuid='isolated')
        finally:native.close()
        self.fields=[f['id'] for f in self.reader.field_registry()['fields']]
    def membership(self,predicate=None,scope=None):return self.reader.membership(predicate,scope)
    def preview(self,**kwargs):return self.reader.preview(**kwargs)
    def detail(self,identity):return self.reader.detail(identity)
    def close(self):self.reader.close()
