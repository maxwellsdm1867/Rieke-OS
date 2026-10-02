"""Read-only physical storage receipts. No corpus construction or live DB writes."""
import os
from pathlib import Path
import sqlite3


def physical_assets(assets):
    """assets: [{path, role, generation}], explicit files in isolated corpus only.

    Hardlinks and repeated references counted once. WAL/SHM, staging, retained
    generations, recovery and caches must be explicitly included by caller.
    """
    files, seen = [], set()
    for asset in assets:
        path = Path(asset['path']).resolve(strict=True)
        stat = path.stat(); identity = (stat.st_dev, stat.st_ino)
        alias = identity in seen; seen.add(identity)
        files.append(dict(path=str(path), role=asset['role'], generation=asset.get('generation'),
                          file_bytes=stat.st_size, allocated_bytes=stat.st_blocks*512,
                          counted=not alias, inode=stat.st_ino, device=stat.st_dev))
    return dict(assets=files, total_file_bytes=sum(f['file_bytes'] for f in files if f['counted']),
                total_allocated_bytes=sum(f['allocated_bytes'] for f in files if f['counted']))


def sqlite_components(path, *, max_file_bytes=64*1024*1024):
    """dbstat costs are used page bytes, not logical bytes or allocated disk.

    Development default refuses large files. Coordinator must explicitly lift
    limit after sealing the required replay, with no competing benchmark worker.
    WAL files are refused; immutable read is safe only for a sealed standalone DB.
    """
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > max_file_bytes: raise ValueError('Large inspection deferred to serial qualification')
    if Path(str(path)+'-wal').exists(): raise ValueError('Checkpoint isolated copy before immutable inspection')
    before = (path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ino)
    connection = sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True)
    try:
        page_size = connection.execute('PRAGMA page_size').fetchone()[0]
        pages = connection.execute('PRAGMA page_count').fetchone()[0]
        free = connection.execute('PRAGMA freelist_count').fetchone()[0]
        components = [dict(name=name, used_page_bytes=size, payload_bytes=payload,
                           unused_page_bytes=unused, pages=count)
                      for name,size,payload,unused,count in connection.execute(
                          'SELECT name,sum(pgsize),sum(payload),sum(unused),count(*) FROM dbstat GROUP BY name ORDER BY name')]
        tables = []
        # Quoted identifier comes from sqlite_schema; never interpolated user SQL.
        for name, kind in connection.execute("SELECT name,type FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY name"):
            entry = dict(name=name, kind=kind)
            if kind=='table':
                quoted = '"'+name.replace('"','""')+'"'
                entry['rows'] = connection.execute('SELECT count(*) FROM '+quoted).fetchone()[0]
            tables.append(entry)
        result = dict(size_definition='file length, allocated disk and SQLite used pages are separate',
                      file_bytes=path.stat().st_size, allocated_bytes=path.stat().st_blocks*512,
                      page_size=page_size, page_count=pages, freelist_pages=free,
                      freelist_bytes=free*page_size, components=components, schema=tables,
                      dbstat_used_page_bytes=sum(c['used_page_bytes'] for c in components))
    finally: connection.close()
    after = (path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ino)
    if before != after: raise ValueError('Storage generation changed during measurement')
    return result


def ratio(numerator, denominator, label, *, projected=False):
    return dict(numerator_bytes=numerator, denominator_bytes=denominator, denominator=label,
                projected=projected, ratio=None if denominator is None or denominator<=0 else numerator/denominator)


def normalized(physical, epochs, links, *, base_bytes, added_bytes,
               actual_h5_bytes=None, projected_h5_bytes=None, projected_response_bytes=None):
    total = physical['total_file_bytes']
    divide = lambda n,d: None if not d else n/d
    return dict(epochs=epochs, epoch_field_links=links, total_metadata_file_bytes=total,
                base_metadata_file_bytes=base_bytes, incremental_index_file_bytes=added_bytes,
                total_bytes_per_epoch=divide(total,epochs), added_bytes_per_epoch=divide(added_bytes,epochs),
                total_bytes_per_epoch_field_link=divide(total,links), added_bytes_per_epoch_field_link=divide(added_bytes,links),
                added_index_over_base_metadata=divide(added_bytes,base_bytes),
                raw_ratios=[ratio(total,actual_h5_bytes,'actual distinct accessible H5 files; same dataset scope required'),
                            ratio(total,projected_h5_bytes,'lineage-weighted equivalent H5 projection',projected=True),
                            ratio(total,projected_response_bytes,'lineage-weighted compressed response payload projection',projected=True)],
                canonical_project_metadata_bytes=None)


def incremental(before, after, workload):
    """Same layout/generation family only; imported epochs/sources/fields/values explicit."""
    if before['layout'] != after['layout']: raise ValueError('Incremental costs require matching layout')
    delta = after['total_file_bytes']-before['total_file_bytes']
    result = dict(delta_file_bytes=delta, workload=workload, before_generation=before['generation'],
                  after_generation=after['generation'])
    for key in ('epochs','sources','fields','distinct_values','relationships'):
        count = workload.get(key)
        result['bytes_per_new_'+key] = None if not count else delta/count
    return result


def growth(points):
    if len({p['layout'] for p in points}) != 1: raise ValueError('Growth requires a controlled common layout')
    if any(p['corpus_kind'] != 'real-lineage-replay' for p in points):
        raise ValueError('Simplified synthetic corpus cannot qualify growth')
    ordered = sorted(points,key=lambda p:p['epochs'])
    for point in ordered:
        if not point.get('lineage_receipt') or not point.get('seal_verified'):
            raise ValueError('Growth needs sealed lineage at every scale')
    return dict(points=ordered, bytes_per_epoch=[p['total_file_bytes']/p['epochs'] for p in ordered],
                increasing_bytes_per_epoch=any(b['total_file_bytes']/b['epochs']>a['total_file_bytes']/a['epochs']
                                              for a,b in zip(ordered,ordered[1:])),
                cardinality_layout_explanation_required=True)


class HighWater:
    """Event/sample observed lower bound, not certified true peak disk usage."""
    def __init__(self): self.samples=[]
    def observe(self, phase, assets):
        sample=physical_assets(assets);sample['phase']=phase;self.samples.append(sample)
        return sample
    def receipt(self):
        return dict(status='observed_lower_bound' if self.samples else 'unrun', samples=self.samples,
                    peak_file_bytes=max((s['total_file_bytes'] for s in self.samples),default=None),
                    peak_allocated_bytes=max((s['total_allocated_bytes'] for s in self.samples),default=None),
                    sampling_limit='Event snapshots can miss temporary peak; serial coordinator must record cadence and staging/old/new/cache assets')
