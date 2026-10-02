"""Aggregate actual mounted metadata, with no synthesized epochs or values."""
from collections import Counter, defaultdict
from pathlib import Path
import datetime
import hashlib
import json
import math
import sqlite3
import statistics

from real_projection_loader import PROJECT, load_real_projections, digest

OUTPUT = Path('/private/tmp/disco-real-data-evals-20261001/profile')

def distribution(items):
    a = sorted(items)
    if not a:
        return {'count': 0}
    def percentile(q):
        return a[round((len(a)-1)*q)]
    return {'count': len(a), 'min': a[0], 'median': statistics.median(a),
            'p90': percentile(.9), 'p95': percentile(.95), 'max': a[-1],
            'mean': statistics.mean(a), 'sum': sum(a)}

def serialized_bytes(value):
    return len(json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False).encode())

def typename(value):
    if value is None: return 'null'
    if isinstance(value, bool): return 'boolean'
    if isinstance(value, int): return 'integer'
    if isinstance(value, float): return 'real'
    if isinstance(value, str): return 'string'
    if isinstance(value, list): return 'array'
    if isinstance(value, dict): return 'object'
    raise TypeError(type(value))

def main():
    rows, details, cells, sources, evidence = load_real_projections()
    n = len(rows)
    cell_counts = Counter(r['cell_uuid'] for r in rows.values())
    block_counts = Counter(r['block_uuid'] for r in rows.values())
    group_counts = Counter(r['group_uuid'] for r in rows.values())
    protocol_counts = Counter(r['protocol_name'] for r in rows.values())
    row_sizes = [serialized_bytes(r) for r in rows.values()]
    detail_sizes = [serialized_bytes(d) for d in details.values()]
    source_epoch_sets = {s['source_sha256']: {i for i, r in rows.items()
                                            if r['source_sha256'] == s['source_sha256']}
                         for s in sources}
    imports = []
    input_hashes = {}
    hierarchy_counts = Counter()
    hierarchy_block_epoch_counts = []
    def hierarchy(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ['animals','preparations','cells','epoch_groups','epoch_blocks','epochs'] and isinstance(child, list):
                    hierarchy_counts[key] += len(child)
                    if key == 'epoch_blocks':
                        hierarchy_block_epoch_counts.extend(len(block.get('epochs', [])) for block in child)
                    for element in child: hierarchy(element)
    for directory in sorted((PROJECT / 'imports').iterdir()):
        index_path = directory / 'epoch-index.json'
        if not index_path.exists(): continue
        blob = index_path.read_bytes()
        index = json.loads(blob)
        identities = {r['epoch_uuid'] for r in index}
        matched = [sha for sha, ids in source_epoch_sets.items() if identities == ids]
        import_manifest = directory / 'import-manifest.json'
        source_selected = json.loads(import_manifest.read_bytes()).get('source_sha256') in source_epoch_sets
        report = {'import_directory': directory.name, 'epochs': len(index),
                  'index_sha256': hashlib.sha256(blob).hexdigest(),
                  'matches_active_epoch_set': bool(matched),
                  'source_selected_by_current_generation': source_selected, 'files': {}}
        if source_selected:
            hierarchy(json.loads((directory/'metadata.raw.json').read_bytes()))
        for name in ['epoch-index.json', 'metadata.catalog.json', 'metadata.raw.json','import-manifest.json']:
            path = directory / name
            if path.exists():
                input_hashes[str(path)] = digest(path)
                report['files'][name] = {'bytes': path.stat().st_size,
                                         'sha256': input_hashes[str(path)]}
        imports.append(report)
    # Both September 24 imports have the same scientific epoch index; only the
    # selected source projection is mounted. The source generation is authority.
    duplicate_indexes = []
    by_digest = defaultdict(list)
    for item in imports:
        by_digest[item['index_sha256']].append(item['import_directory'])
    for names in by_digest.values():
        if len(names) > 1: duplicate_indexes.append(names)

    metadata_dir = PROJECT / 'cache' / 'metadata'
    meta_manifest = metadata_dir / '.current-generations.json'
    meta_manifest_sha = digest(meta_manifest)
    name = json.loads(meta_manifest.read_bytes())['keep'][0]
    database = metadata_dir / name
    database_sha = digest(database)
    con = sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True)
    con.execute('PRAGMA query_only=ON')
    mounted_n = con.execute('SELECT COUNT(*) FROM epochs').fetchone()[0]
    if mounted_n != n:
        raise ValueError('Mounted metadata and active projections differ in epoch count')
    mounted_ids = {r[0] for r in con.execute('SELECT epoch_uuid FROM epochs')}
    if mounted_ids != rows.keys():
        raise ValueError('Mounted metadata and active projections differ in epoch membership')
    fields = []
    for number, field_id, definition_json in con.execute('SELECT field_no,field_id,definition_json FROM fields ORDER BY field_id'):
        counts = Counter()
        nulls = 0
        lengths = []
        frequencies = []
        arrays = []
        large_integer_occurrences = 0
        for encoded, frequency in con.execute('SELECT v.value_json,COUNT(*) FROM epoch_values e JOIN field_values v USING(value_id) WHERE e.field_no=? GROUP BY e.value_id', (number,)):
            value = json.loads(encoded)
            kind = typename(value)
            counts[kind] += frequency
            if value is None: nulls += frequency
            if kind == 'array': arrays.extend([len(value)] * frequency)
            if kind == 'integer' and abs(value) > 2**53: large_integer_occurrences += frequency
            frequencies.append(frequency)
            lengths.extend([len(encoded.encode())] * frequency)
        present = sum(counts.values())
        definition = json.loads(definition_json)
        fields.append({'id': field_id, 'path': definition.get('path'),
                       'category': definition.get('category'), 'present_epochs': present,
                       'missing_epochs': n-present, 'null_epochs': nulls,
                       'types': dict(counts), 'cardinality_including_null': len(frequencies),
                       'top_value_frequencies': sorted(frequencies, reverse=True)[:10],
                       'value_json_bytes': distribution(lengths),
                       'array_length': distribution(arrays),
                       'integer_above_js_safe_precision_occurrences': large_integer_occurrences})
    per_epoch_fields = [r[0] for r in con.execute('SELECT COUNT(*) FROM epoch_values GROUP BY epoch_id')]
    table_counts = {table: con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                    for table in ['epochs','fields','field_values','epoch_values','metadata_objects','sources']}
    source_stats = []
    for source in sources:
        subset = [r for r in rows.values() if r['source_sha256'] == source['source_sha256']]
        source_stats.append({'recording_dates': sorted({r['date'] for r in subset}),
                             'epochs': len(subset),
                             'cells': len({r['cell_uuid'] for r in subset}),
                             'blocks': len({r['block_uuid'] for r in subset}),
                             'groups': len({r['group_uuid'] for r in subset}),
                             'protocols': dict(Counter(r['protocol_name'] for r in subset)),
                             'source_counts': source['counts']})
    con.close()
    if digest(meta_manifest) != meta_manifest_sha or digest(database) != database_sha:
        raise ValueError('Mounted metadata generation changed during profiling')
    if any(digest(path) != sha for path, sha in input_hashes.items()):
        raise ValueError('Source input changed during profiling')
    result = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'real_only': True, 'scaled_or_synthetic_epochs': 0,
              'counts': {'active_sources': len(sources), 'epochs': n, 'cells': len(cells),
                         'blocks': hierarchy_counts['epoch_blocks'],
                         'nonempty_blocks': len(block_counts),
                         'empty_blocks': hierarchy_counts['epoch_blocks']-len(block_counts),
                         'groups': len(group_counts),
                         'protocols': len(protocol_counts)},
              'raw_hierarchy_counts': dict(hierarchy_counts),
              'protocol_epoch_counts': dict(protocol_counts), 'sources': source_stats,
              'epoch_counts_per_cell': distribution(cell_counts.values()),
              'epoch_counts_per_block': distribution(block_counts.values()),
              'epoch_counts_per_block_including_empty': distribution(hierarchy_block_epoch_counts),
              'epoch_counts_per_group': distribution(group_counts.values()),
              'row_json_bytes': distribution(row_sizes),
              'reconstructed_detail_json_bytes': distribution(detail_sizes),
              'query_fields_per_epoch': distribution(per_epoch_fields),
              'native_metadata': {'database': name, 'database_bytes': database.stat().st_size,
                                  'database_sha256': database_sha, 'tables': table_counts,
                                  'manifest_sha256': meta_manifest_sha},
              'query_fields': fields, 'imports': imports,
              'duplicate_index_imports': duplicate_indexes, 'projection_evidence': evidence,
              'input_unchanged_before_after': True,
              'privacy': 'Field IDs and aggregate counts/widths only; raw values excluded.'}
    (OUTPUT/'real-metadata-profile.json').write_text(json.dumps(result, indent=2)+'\n')
    protocol_lines = '\n'.join(f'| {name} | {count:,} |' for name,count in sorted(protocol_counts.items(), key=lambda p:-p[1]))
    report = f'''# Actual mounted Disco metadata profile

The installed project's current generations contain **{n:,} real epochs**, **{len(cells)} cells**, **{hierarchy_counts['epoch_blocks']} blocks** ({len(block_counts)} nonempty and {hierarchy_counts['epoch_blocks']-len(block_counts)} empty), **{len(group_counts)} groups**, **{len(protocol_counts)} protocols**, and **{len(sources)} active sources**. No new epochs or metadata values were generated. This is an inventory at the actual mounted volume, not a million-epoch qualification.

## Real protocol mix

| Protocol | Epochs |
|---|---:|
{protocol_lines}

## Actual metadata workload

- Mounted SQLite has **{len(fields)} query fields**, **{table_counts['field_values']:,} exact typed distinct field/value pairs**, and **{table_counts['epoch_values']:,} epoch/field links**.
- Query fields per epoch: median **{statistics.median(per_epoch_fields):g}**, minimum **{min(per_epoch_fields)}**, maximum **{max(per_epoch_fields)}**.
- Reconstructed full detail JSON: median **{statistics.median(detail_sizes):,.0f} bytes**, p95 **{sorted(detail_sizes)[round((n-1)*.95)]:,} bytes**, maximum **{max(detail_sizes):,} bytes**. This includes shared ancestor metadata reconstructed for each epoch; it excludes waveform samples.
- Epoch row JSON: median **{statistics.median(row_sizes):,.0f} bytes**.
- Epochs per cell: median **{statistics.median(cell_counts.values()):g}**, range **{min(cell_counts.values())}–{max(cell_counts.values())}**.
- Epochs per block: median **{statistics.median(block_counts.values()):g}**, range **{min(block_counts.values())}–{max(block_counts.values())}**.

The JSON companion inventories every field's path, type, missing/null counts, cardinality, top frequency counts, JSON width, array length, and integers above JavaScript's exact numeric range. Raw field values are excluded.

## Source handling and reproducibility

There are four import directories but three selected projection generations. The two September 24 epoch-index files are byte-identical and both contain 1,086 epochs. They must not be counted twice when sizing the mounted dataset. Current projection generation selection and exact mounted SQLite epoch membership establish the actual 2,781-epoch volume.

Only read-only file operations and an immutable, query-only SQLite connection were used. No application service, import, migration, refresh, cache publication, or cache lease was invoked. SHA256 seals were checked for all selected source projections. Generation manifests, projections, mounted SQLite, and examined import files were unchanged before and after inspection.

The read-only helper `real_projection_loader.load_real_projections()` returns actual rows, losslessly reconstructed details, cells, sources, and hash evidence for isolated comparisons. Any future million-epoch expansion should clone whole real acquisition hierarchies and label the result as scaled real data; repeating existing data preserves its observed mix but does not prove behavior for unseen metadata diversity.
'''
    (OUTPUT/'REAL_METADATA_PROFILE.md').write_text(report)
    print(json.dumps({'counts': result['counts'], 'native_tables': table_counts,
                      'protocols': dict(protocol_counts),
                      'detail_width': result['reconstructed_detail_json_bytes'],
                      'query_fields_per_epoch': result['query_fields_per_epoch'],
                      'report': str(OUTPUT/'REAL_METADATA_PROFILE.md'),
                      'profile': str(OUTPUT/'real-metadata-profile.json')}))

if __name__ == '__main__': main()
