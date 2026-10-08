import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createElement} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {renderToString} from 'react-dom/server';
import {createServer} from './test-support/isolatedVite.js';
import react from '@vitejs/plugin-react';
let server;
before(async()=>{server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,plugins:[react()],server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});});
after(async()=>{await server?.close();});
async function render(path,props){const {default:Component}=await server.ssrLoadModule(path);return renderToString(createElement(Component,props));}
test('web tree arrangement keeps grouping controls without MATLAB GUI command controls',async()=>{
 const html=await render('/src/typed-query/ui/TreeBuilder.jsx',{value:['date'],onChange(){},catalogData:{fields:[{id:'date',label:'Date',category:'Common'}]},preview:{levels:[{field:'date'}],matlab_command:'legacy_epictree_command();'},loading:false});
 assert.match(html,/Arrange tree/);assert.match(html,/Ordered tree splits/);assert.doesNotMatch(html,/EpicTree|MATLAB|legacy_epictree_command|Copy EpicTree code/);
});

test('saved legacy search destination renders a selected standalone MAT data choice without a GUI handoff',async()=>{
 const html=await render("/src/exports/ui/CandidateExportPanel.jsx",{candidate:{revision_uuid:'candidate',recipe:{epoch_count:3,full_recipe_sha256:'sealed'}},defaultFormat:'epictree-mat'});
 assert.match(html,/MATLAB data \(\.mat\)/);assert.match(html.match(/<input[^>]*value="matlab-mat"[^>]*>/)?.[0]||'',/checked=""/);assert.doesNotMatch(html,/EpicTree|launcher|selection mask|MATLAB bundle/);
});

test('linked reference exports are selectable and explain the managed-source dependency',async()=>{
 const candidate=await render('/src/exports/ui/CandidateExportPanel.jsx',{candidate:{revision_uuid:'candidate',recipe:{epoch_count:3,full_recipe_sha256:'sealed'}},defaultFormat:'linked-sqlite'});
 assert.match(candidate,/Linked SQLite/);assert.match(candidate,/Python loader/);assert.match(candidate,/needs managed source folders/);
 assert.match(candidate.match(/<input[^>]*value="linked-sqlite"[^>]*>/)?.[0]||'',/checked=""/);
 const {ExportDestination}=await server.ssrLoadModule('/src/exports/ui/ProtocolExports.jsx');
 const html=renderToString(createElement(ExportDestination,{value:'linked-sqlite',onChange(){}}));
 assert.match(html.match(/<input[^>]*value="linked-sqlite"[^>]*>/)?.[0]||'',/checked=""/);
 assert.match(html,/MATLAB data/);assert.match(html,/Wheeler SQL/);
});


test('explicit export from a legacy saved search posts only the canonical MAT data format',async()=>{
 const prior=globalThis.fetch,calls=[],downloads=[];let root;
 const priorDocument=globalThis.document;globalThis.document={body:{appendChild(){}},createElement:()=>({click(){downloads.push(this.href);},remove(){}})};
 globalThis.fetch=async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return {ok:true,json:async()=>({format:'matlab-mat',name:'Saved selection',epoch_count:3,dataset_uuid:'dataset',event_uuid:'event',download_url:'/api/exports/dataset/download'})};};
 try{const {default:Candidate}=await server.ssrLoadModule("/src/exports/ui/CandidateExportPanel.jsx");
  await act(async()=>{root=TestRenderer.create(createElement(Candidate,{candidate:{revision_uuid:'candidate',recipe:{epoch_count:3,full_recipe_sha256:'sealed'}},defaultFormat:'epictree-mat'}));});
  assert.equal(calls.length,0);assert.deepEqual(downloads,[]);
  await act(async()=>root.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.deepEqual(calls,[{path:'/api/explore/revisions/candidate/exports',body:{format:'matlab-mat',expected_recipe_sha256:'sealed'}}]);
  assert.deepEqual(downloads,['/api/exports/dataset/download']);
  assert.equal(root.root.findByType('a').props.href,'/api/exports/dataset/download');
  assert.match(root.root.findByType('a').children.filter(x=>typeof x==='string').join(''),/MAT data/);
 }finally{if(priorDocument===undefined)delete globalThis.document;else globalThis.document=priorDocument;await act(async()=>root?.unmount());if(prior===undefined)delete globalThis.fetch;else globalThis.fetch=prior;}
});
