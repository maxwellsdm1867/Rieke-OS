import {spawn, spawnSync} from 'node:child_process';
import {existsSync, readFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {dirname, resolve, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const appDir=dirname(fileURLToPath(import.meta.url));
const repository=resolve(appDir,'..');
const runtimeFile=join(repository,'.rieke-runtime/runtime.json');
let runtime={},selection={};
try {
  const selectionFile=process.env.RIEKE_INSTALLATION_ROOT?join(process.env.RIEKE_INSTALLATION_ROOT,'preferences/workspace-selection.json'):join(repository,'.rieke-runtime/workspace-selection.json');
  if(existsSync(selectionFile)){
    selection=JSON.parse(readFileSync(selectionFile,'utf8'));
    if(selection.version!==1||typeof selection.managed_root!=='string'||!selection.managed_root)throw new Error('Invalid saved workspace selection');
  }
  if(existsSync(runtimeFile)) {
    runtime=JSON.parse(readFileSync(runtimeFile,'utf8'));
    if(runtime.version!==1)throw new Error('Unsupported runtime configuration');
  }
} catch(error) {
  console.error(`Cannot read local runtime configuration: ${error.message}. Run python3 rieke.py setup.`);
  process.exit(1);
}
const retinanalysis=resolve(repository,process.env.RETINANALYSIS_DIR||runtime.retinanalysis||'.rieke-runtime/retinanalysis');
const managedRoot=process.env.RECORDING_WORKSPACE_ROOT||selection.managed_root||runtime.managed_root||(process.env.RECORDING_PROJECT_DIR?dirname(resolve(process.env.RECORDING_PROJECT_DIR)):join(homedir(),'Documents/RecordingWorkspace'));
const port=Number(process.env.RIEKE_LAUNCHER_PORT||8766);
const python=resolve(repository,process.env.RECORDING_PYTHON||runtime.python||'.rieke-runtime/venv/bin/python');
try{
  if(!Number.isInteger(port)||port<1||port>65535)throw new Error('Choose a launcher port between 1 and 65535.');
  if(!existsSync(python))throw new Error('Backend runtime is missing. Run python3 rieke.py setup from the repository root, or set RECORDING_PYTHON and RETINANALYSIS_DIR explicitly.');
  if(!existsSync(join(retinanalysis,'src/retinanalysis/utils/parse_data.py')))throw new Error('Parser checkout is missing. Run python3 rieke.py setup.');
  const probe=spawnSync(python,[join(repository,'rieke.py'),'doctor','--json'],{cwd:repository,encoding:'utf8',env:{...process.env,RECORDING_PYTHON:python,RETINANALYSIS_DIR:retinanalysis}});
  if(probe.error||probe.status!==0)throw new Error(`Backend readiness check failed. Run python3 rieke.py doctor.\n${probe.stdout||probe.stderr||probe.error?.message||''}`);
  if(process.env.RIEKE_INSTALLATION_ROOT){
    if(!existsSync(join(appDir,'dist/index.html')))throw new Error('The installed release has no built frontend. Restore or restage the release.');
  }else{
    const built=spawnSync('npm',['run','build'],{cwd:appDir,stdio:'inherit'});
    if(built.error||built.status!==0)throw new Error('The app build did not finish. Fix the reported build error before starting.');
  }
  console.log(`\nRieke OS: http://127.0.0.1:${port}\nProjects: ${managedRoot}\nChoose a project or create an empty one. Databases start only when opened.\n`);
  const server=spawn(python,[join(repository,'python/workspace_launcher.py'),'--managed-root',managedRoot,'--retinanalysis',retinanalysis,'--port',String(port)],{cwd:repository,stdio:'inherit'});
  for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>server.kill(signal));
  server.on('exit',code=>process.exit(code??0));
  server.on('error',error=>{console.error(error.message);process.exit(1);});
}catch(error){console.error(error.message);process.exit(1);}
