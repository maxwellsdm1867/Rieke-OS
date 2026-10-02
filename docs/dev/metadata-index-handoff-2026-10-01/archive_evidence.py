"""Copy existing text evidence without running experiments or copying databases."""
from pathlib import Path
import argparse,hashlib,json,shutil
NAMES=['disco-everyday-benchmark','disco-performance-evals','disco-duckdb-million-evals','disco-real-data-evals','disco-real-typed-sqlite-evals','disco-real-million-evals','disco-metadata-priorities','disco-priority-benchmark-evals']
TEXT={'.md','.json','.py','.mjs','.js','.cjs','.jsx','.css','.html','.txt','.csv','.log','.sh','.yaml','.yml','.toml'}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def archive(source,destination):
    destination.mkdir(parents=True,exist_ok=True)
    inventory={'source_root':str(source),'scope':'Existing text reports, scripts, source snapshots and receipts only; no experiments executed.','bundles':[]}
    for name in NAMES:
        root=source/name
        if not root.is_dir():raise FileNotFoundError(root)
        bundle={'name':name,'source_path':str(root),'files':[],'excluded':[]}
        for path in sorted(root.rglob('*')):
            if not path.is_file():continue
            rel=path.relative_to(root)
            if path.is_symlink() or path.suffix.lower() not in TEXT or path.stat().st_size>2*1024*1024:
                bundle['excluded'].append({'path':str(rel),'bytes':path.stat().st_size,'reason':'binary, generated/large asset, or unsupported text suffix'})
                continue
            target=destination/name/rel;target.parent.mkdir(parents=True,exist_ok=True)
            before=digest(path);shutil.copy2(path,target)
            assert digest(target)==before
            bundle['files'].append({'path':str(rel),'bytes':target.stat().st_size,'sha256':before})
        bundle['copied_bytes']=sum(f['bytes'] for f in bundle['files']);inventory['bundles'].append(bundle)
    (destination/'INVENTORY.json').write_text(json.dumps(inventory,indent=2)+'\n')
    lines=['# Preserved evidence inventory','',
        'Copied from existing conversation artifacts on 2026-10-01. Reports, scripts, source snapshots and raw text receipts are preserved byte-for-byte. No experiment was rerun. The archive excludes scientific databases, binary profiles, images and generated/large assets; INVENTORY.json enumerates every copied and excluded file and the original source root.','',
        '| Bundle | Primary report | Copied files | Text bytes |','|---|---|---:|---:|']
    reports={'disco-everyday-benchmark':'REPORT.md','disco-performance-evals':'evals/CANDIDATE-RESULTS.md','disco-duckdb-million-evals':'evals/RESULTS.md','disco-real-data-evals':'engines/REPORT.md','disco-real-typed-sqlite-evals':'RESULTS.md','disco-real-million-evals':'RESULTS.md','disco-metadata-priorities':'PROPOSAL.md','disco-priority-benchmark-evals':'RESULTS.md'}
    for b in inventory['bundles']:
        name=b['name'];lines.append(f"| {name} | [Report]({name}/{reports[name]}) | {len(b['files'])} | {b['copied_bytes']:,} |")
    lines.extend(['','The original SHA256.json files remain unchanged and may refer to excluded binary assets. ARCHIVE-SHA256.json validates this repository text archive; INVENTORY.json maps its files to the originals. Paths inside historical scripts/reports are retained as evidence and may still depend on temporary databases or installed local runtimes.','',
        'The earlier metadata-priorities proposal and its draft field policy are historical. The subsequent priority experiment rejects narrowing the hot field index as a speed optimization. The current [requirements](../../../design/metadata-query-requirements.md) and [handoff](../README.md) govern the next integration.',''])
    (destination/'INDEX.md').write_text('\n'.join(lines))
    hashes={str(p.relative_to(destination)):digest(p) for p in sorted(destination.rglob('*')) if p.is_file() and p.name!='ARCHIVE-SHA256.json'}
    (destination/'ARCHIVE-SHA256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(json.dumps({'bundles':len(inventory['bundles']),'copied_files':sum(len(b['files']) for b in inventory['bundles']),'copied_bytes':sum(b['copied_bytes'] for b in inventory['bundles']),'byte_identity_verified':True}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--destination',type=Path,default=Path(__file__).parent/'evidence');a=p.parse_args();archive(a.source,a.destination)
