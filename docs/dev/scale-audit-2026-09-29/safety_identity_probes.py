import argparse,copy,json,re,sys,tempfile,uuid
from pathlib import Path
from unittest.mock import patch
import h5py,numpy as np
sys.path.insert(0,'python')
import recording_workspace as workspace
from workspace_service import WorkspaceService,read_response_window

def uid(n):return str(uuid.UUID(int=n))
REJECTION_PATTERNS={
 'wrong_cell_and_group':r'(cell|group).*(identity|uuid|ownership|source|mismatch|differ|mapping)|(identity|uuid|ownership|mismatch|differ|mapping).*(cell|group)',
 'duplicate_raw_epoch_omitted_by_parser':r'(duplicate|multiplicity|membership|more than once).*(epoch|uuid)|(epoch|uuid).*(duplicate|multiplicity|membership|more than once)',
 'wrong_block':r'epoch points to a different source block',
 'external_link_data_changed':r'(external|virtual|dependenc).*(link|data|stor|source|unsupported|not|reject|seal)|(link|data|stor|source|unsupported|reject|seal).*(external|virtual|dependenc)'}
def expected_validation_rejection(variant,error):
 return isinstance(error,ValueError) and bool(re.search(REJECTION_PATTERNS.get(variant,r'(?!)'),str(error),re.I))
# A runtime/setup error must never make a hostile fixture green.
for variant in REJECTION_PATTERNS:
 for unrelated in (OSError('Disk unavailable'),KeyError('Missing field'),ValueError('Metadata checksum mismatch')):
  assert not expected_validation_rejection(variant,unrelated)
arguments=argparse.ArgumentParser(description='Reproduce importer identity gaps on disposable fixtures; --strict fails when unsafe fixtures are accepted.')
arguments.add_argument('--strict',action='store_true')
arguments.add_argument('--output',type=Path)
args=arguments.parse_args()
parser,parser_path=workspace.load_parser(Path('.rieke-runtime/retinanalysis').resolve())
results={'date':'2026-09-29','method':'Tiny disposable real HDF5 recording with actual pinned parser ExperimentObj/parse_value. Cached parser document is generated and checksum sealed in the fixture to simulate semantically wrong parser output. Calls production prepare() and read-model _read_source_metadata(); no live project/catalog mutation. This tests validator behavior, not evidence that the parser produces these errors in real data.','unrelated_exception_controls_passed':12,'probes':[]}
for variant in ('valid','wrong_cell_and_group','duplicate_raw_epoch_omitted_by_parser','wrong_block','external_link_data_changed'):
 with tempfile.TemporaryDirectory(prefix='rieke-identity-') as folder:
  root=Path(folder);source=root/'fixture.h5';epoch_path=f'/experiment-{uid(1)}/epochGroups/group-{uid(3)}/epochBlocks/block-{uid(4)}/epochs/epoch-{uid(5)}';stream_path=epoch_path+'/responses/Amp1-'+uid(6)
  with h5py.File(source,'w') as h5:
   experiment=h5.create_group('/experiment-'+uid(1));experiment.attrs['uuid']=uid(1).encode();experiment.attrs['label']=b'Experiment';experiment.create_group('properties')
   animal=experiment.create_group('sources/animal-'+uid(7));animal.attrs['uuid']=uid(7).encode();animal['experiment']=experiment
   preparation=animal.create_group('sources/preparation-'+uid(8));preparation.attrs['uuid']=uid(8).encode()
   cell=h5.create_group(preparation.name+'/sources/cell-'+uid(2));cell.attrs['uuid']=uid(2).encode();cell.attrs['label']=b'Actual cell'
   group=h5.create_group(experiment.name+'/epochGroups/group-'+uid(3));group.attrs['uuid']=uid(3).encode();group['source']=cell
   block=h5.create_group(group.name+'/epochBlocks/block-'+uid(4));block.attrs['uuid']=uid(4).encode();block.attrs['protocolID']=b'example.Protocol';block.create_group('protocolParameters')
   epoch=h5.create_group(epoch_path);epoch.attrs['uuid']=uid(5).encode();epoch.create_group('protocolParameters')
   stream=h5.create_group(stream_path);stream.attrs['uuid']=uid(6).encode();stream.attrs['sampleRate']=10000.
   data=np.zeros(4,dtype=[('quantity','f8'),('units','S8')]);data['quantity']=np.arange(4);data['units']=b'pA';
   if variant=='external_link_data_changed':
    with h5py.File(root/'external.h5','w') as external:external.create_dataset('values',data=data)
    stream['data']=h5py.ExternalLink(str(root/'external.h5'),'/values')
   else:stream.create_dataset('data',data=data)
   if variant=='duplicate_raw_epoch_omitted_by_parser':
    duplicate=h5.create_group(block.name+'/epochs/duplicate-physical-epoch');duplicate.attrs['uuid']=uid(5).encode();duplicate.create_group('protocolParameters')
  epoch={'uuid':uid(5),'start_time':'09/29/2026 12:00:00:000000','parameters':{},'properties':{},'attributes':{},'responses':{'Amp1':{'uuid':uid(6),'h5path':stream_path,'sampleRate':10000.,'sampleRateUnits':'Hz'}},'stimuli':{}}
  block={'uuid':uid(4),'protocolID':'example.Protocol','epochs':[epoch]};group={'uuid':uid(3),'epoch_blocks':[block]};cell={'uuid':uid(2),'label':'Actual cell','start_time':'09/29/2026 11:00:00:000000','epoch_groups':[group]}
  if variant=='wrong_cell_and_group':cell.update(uuid=uid(100),label='Wrong cell');group['uuid']=uid(101)
  if variant=='wrong_block':block['uuid']=uid(104)
  raw={'uuid':uid(1),'rig_type':'PATCH','animals':[{'uuid':uid(7),'preparations':[{'uuid':uid(8),'cells':[cell]}]}]}
  sha=workspace.digest(source);project=root/'project';cache=project/'imports'/('fixture-'+sha[:12]);cache.mkdir(parents=True);raw_path=cache/'metadata.raw.json';workspace.write_json(raw_path,raw)
  workspace.write_json(cache/'parse-manifest.json',{'status':'parsed','sha256':sha,'metadata_sha256':workspace.digest(raw_path),'parser_sha256':workspace.digest(parser_path)})
  outcome={'variant':variant,'actual_h5_cell_uuid':uid(2),'actual_h5_group_uuid':uid(3),'actual_h5_epoch_objects':2 if variant=='duplicate_raw_epoch_omitted_by_parser' else 1}
  try:
   experiment,rows,manifest,location=workspace.prepare(source,project,Path('.rieke-runtime/retinanalysis').resolve())
   outcome.update(prepare='accepted',parsed_epochs=manifest['counts']['epochs'],parsed_cell_uuid=rows[0]['cell_uuid'],parsed_group_uuid=rows[0]['group_uuid'])
   service=WorkspaceService.__new__(WorkspaceService)
   stat=source.stat();signature=(str(source),stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
   record={'manifest':manifest,'source_sha256':sha}
   projection=service._read_source_metadata(record,experiment,source,signature)
   outcome['read_model']='accepted';outcome['read_model_cell_uuid']=projection['rows'][uid(5)]['cell_uuid']
   if variant=='external_link_data_changed':
    trace_row=projection['rows'][uid(5)];trace_stream=trace_row['streams'][0]
    before=read_response_window(source,signature,trace_row,trace_stream,count=4)['values']
    with h5py.File(root/'external.h5','r+') as external:
     values=external['values'][:];values['quantity']+=1000;external['values'][:]=values
    outcome.update(source_sha_unchanged=workspace.digest(source)==sha,trace_before=before,trace_after=read_response_window(source,signature,trace_row,trace_stream,count=4)['values'])
  except Exception as error:
   outcome.update(error_type=type(error).__name__,error=str(error))
   outcome['expected_validation_error']=expected_validation_rejection(variant,error)
   outcome['unexpected_runtime_error']=not outcome['expected_validation_error']
   if 'prepare' not in outcome:outcome['prepare']='rejected'
   else:outcome['later_validation']='rejected'
  expected='accepted' if variant=='valid' else 'rejected'
  outcome['expected_prepare']=expected
  outcome['gate_passed']=outcome.get('prepare')==expected and (outcome.get('read_model')=='accepted' if variant=='valid' else outcome.get('expected_validation_error',False))
  results['probes'].append(outcome)
  print(json.dumps(outcome),flush=True)
results['strict']=args.strict
results['failed_gates']=[probe['variant'] for probe in results['probes'] if not probe['gate_passed']]
results['gate_result']='PASS' if not results['failed_gates'] else 'FAIL'
output='safety-identity-strict.json' if args.strict else 'safety-identity-probes.json'
(args.output or Path('docs/dev/scale-audit-2026-09-29',output)).write_text(json.dumps(results,indent=2)+'\n')
if args.strict and results['failed_gates']:sys.exit(1)
