"""Read-only AST comparison; never imports application code or connects to SQL."""
import argparse, ast, hashlib, json, subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--kit',type=Path,required=True);p.add_argument('--repo',type=Path,required=True);p.add_argument('--retinanalysis-schema',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
old=json.loads((a.kit/'current-database-schema.json').read_text())
def norm(s):return '\n'.join(x.strip() for x in s.strip().splitlines() if x.strip())
def definitions(path):
 tree=ast.parse(path.read_text());out={}
 for node in ast.walk(tree):
  if isinstance(node,ast.ClassDef):
   for item in node.body:
    if isinstance(item,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='definition' for t in item.targets) and isinstance(item.value,ast.Constant) and isinstance(item.value.value,str):out[node.name]=(item.value.value,node.lineno)
 return out
results=[];known={};hashes={}
for table in old['tables']:
 path=a.retinanalysis_schema if table['schema']=='schema' else a.repo/'python'/Path(table['source']).name
 key='dependency/retinanalysis/config/schema.py' if table['schema']=='schema' else 'python/'+path.name
 current=definitions(path);known.setdefault(key,set()).add(table['class']);hashes[key]=hashlib.sha256(path.read_bytes()).hexdigest()
 found=current.get(table['class']);results.append({'table':table['schema']+'.'+table['table'],'class':table['class'],'source':key,'line':found[1] if found else None,'definition_equal_ignoring_indentation':bool(found and norm(found[0])==norm(table['datajoint_definition']))})
extra=[]
for path in [*(a.repo/'python').glob('*.py'), a.retinanalysis_schema]:
 key='dependency/retinanalysis/config/schema.py' if path==a.retinanalysis_schema else 'python/'+path.name
 for cls,(definition,line) in definitions(path).items():
  if cls not in known.get(key,set()):extra.append({'class':cls,'source':key,'line':line})
# DDL literal parity is independent of runtime interpolation/live DDL.
ddl=[]
for entry in old['derived_table_ddl_source_literals']:
 path=a.repo/entry['source'];ddl.append({'source':entry['source'],'literal_present':entry['source_literal'] in path.read_text()})
tree=ast.parse((a.repo/'python/workspace_sqlite.py').read_text());schema=next(n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SCHEMA' for t in n.targets))
out={'method':'AST string comparison, whitespace-normalized definitions; no application imports or SQL','catalog_baseline_commit':old['baseline_commit'],'comparison_commit':subprocess.check_output(['git','-C',str(a.repo),'rev-parse','HEAD'],text=True).strip(),'tables':results,'additional_definition_classes':extra,'derived_ddl_literals':ddl,'frozen_export_ddl_equal':schema==old['frozen_export_sqlite_v2_ddl'],'source_sha256':hashes,'limitations':['Acquisition definitions compared to installed dependency, not proven identical to pinned upstream.','No live DDL/index introspection.','Additional definition scan is static; generated/runtime declarations cannot be excluded.']}
out['passed'] = (all(r['definition_equal_ignoring_indentation'] for r in results)
                 and not extra and all(r['literal_present'] for r in ddl)
                 and out['frozen_export_ddl_equal'])
a.output.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'tables':len(results),'equal':sum(r['definition_equal_ignoring_indentation'] for r in results),'unequal':[r for r in results if not r['definition_equal_ignoring_indentation']],'extra':extra,'ddl_literals':len(ddl),'ddl_equal':sum(r['literal_present'] for r in ddl),'export_equal':out['frozen_export_ddl_equal']},indent=2))

raise SystemExit(0 if out["passed"] else 1)
