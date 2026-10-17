import {spawnSync} from 'node:child_process';

// The architecture guard targets the packaged runtime (Python 3.11). A bare
// `python3` on developer machines is often an older Anaconda or system build,
// so prefer DISCO_PYTHON, then python3.11, then python3, and fail with a clear
// message instead of a confusing guard error when none is new enough.
let resolved;
export function guardPython(){
  if(resolved)return resolved;
  const candidates=[process.env.DISCO_PYTHON,'python3.11','python3'].filter(Boolean);
  for(const command of candidates){
    const run=spawnSync(command,['-c','import sys;print(sys.version_info>=(3,11))'],{encoding:'utf8'});
    if(!run.error&&run.stdout.trim()==='True')return resolved=command;
  }
  throw Error(`Architecture guard tests need Python 3.11+; tried ${candidates.join(', ')}. Set DISCO_PYTHON to a 3.11 interpreter.`);
}
