import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
for(const action of ['onHistory','onDefer'])test(`leaving held source via ${action} retires consent before reopening`,async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{name:'hold-navigation',enforce:'pre',resolveId(id,importer){if(importer?.endsWith('/IncomingWorkbench.jsx')&&id==='./FrozenIncomingReview.jsx')return '\0frozen';if(importer?.endsWith('/IncomingWorkbench.jsx')&&id==='../useWorkbenchQueue.js')return '\0queue';},load(id){if(id==='\0frozen')return `export default 'frozen-probe';`;if(id==='\0queue')return `export default ()=>({loading:false,data:{contract_version:1,queue_revision:'q',pending_epoch_count:1,pending_cell_count:1,candidates:[{candidate_revision_uuid:'candidate',protocol_uuid:'protocol',status:'pending'}],capabilities:{cumulative_pending_browse:true,additive_accept:true,frozen_browse:true,drafts:true}},reload(){}});`;}}]});
 let renderer;try{
 const {default:Workbench}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingWorkbench.jsx');
 await act(()=>{renderer=TestRenderer.create(React.createElement(Workbench,{projectId:'project',protocolId:'protocol',onClaimMergeIntent:()=>true,initialMergeIntent:{kind:'merge_source',request_uuid:'hold',project_uuid:'project',protocol_uuid:'protocol',candidate_revision_uuid:'candidate',source_sha256:'source'}}));});
 assert.equal(renderer.root.findByType('frozen-probe').props.mergeRequest.request_uuid,'hold');
 await act(()=>renderer.root.findByType('frozen-probe').props[action]());
 const button=renderer.root.findAllByType('button').find(node=>node.children.join('')==='Review first');assert.ok(button);await act(()=>button.props.onClick());
 assert.equal(renderer.root.findByType('frozen-probe').props.mergeRequest,null);
 }finally{await act(()=>renderer?.unmount());await server.close();}
});
