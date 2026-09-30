// Mounted React lifecycle recovery gate; never contacts a production API.
// Default writes diagnostic JSON; --strict fails on any stale publication.
import {writeFile} from 'node:fs/promises';
import {selectionRaceCases} from '../../../workspace-app/src/test-support/pagedTreeHarness.js';
const strict=process.argv.includes('--strict');
let output;
for(let i=2;i<process.argv.length;i++){
 if(process.argv[i]==='--strict')continue;
 if(process.argv[i]==='--output'&&process.argv[i+1]){output=process.argv[++i];continue;}
 throw Error('Usage: node frontend-selection-race.mjs [--strict] [--output path]');
}
const cases=await selectionRaceCases();
const filterCell=cases.find(item=>item.kind==='cell'&&item.change==='filter');
const failures=cases.flatMap(item=>item.assertions.filter(a=>!a.passed).map(a=>({case:`${item.kind}:${item.change}`,assertion:a.name})));
// Preserve the original default diagnostic keys for existing readers.
const result={kind:'Mounted PagedTree React lifecycle with deferred fake API, not browser E2E',started_filter:filterCell.started_filter,current_filter:filterCell.current_filter,
 old_request_aborted:filterCell.old_request_aborted,published_after_filter_change:filterCell.published_after_rerender.map(({phase,...rest})=>rest),
 lifecycle:'Real React mount, update, layout effects and unmount; child presentation and API are fixtures.',
 cases,gate:{strict,passed:failures.length===0,failures,description:'Late cell/range completion must retain current scope and exact UUIDs.'}};
console.log(JSON.stringify(result,null,2));
await writeFile(output||new URL(strict?'./frontend-selection-race.strict.json':'./frontend-selection-race.json',import.meta.url),JSON.stringify(result,null,2)+'\n');
if(strict&&failures.length)process.exitCode=1;
