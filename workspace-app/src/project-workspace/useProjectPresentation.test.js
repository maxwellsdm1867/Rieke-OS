import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import useProjectPresentation,{validProjectPresentation} from './useProjectPresentation.js';

const snapshot=(project_uuid,project_path)=>({available:true,format:'disco-project-presentation',version:1,project_uuid,project_path,observed_at:'2026-10-13T12:00:00Z',presentation_only:true,overview:{project:{project_uuid},counts:{epochs:12},cells:[],protocols:[],sources:[]}});
test('disk presentation requires exact project/path and a display-only versioned envelope',()=>{
 const value=snapshot('p','/p');assert.equal(validProjectPresentation(value,'p','/p'),true);
 for(const invalid of [{...value,project_path:'/copy'},{...value,project_uuid:'other'},{...value,presentation_only:false},{...value,version:2},{...value,overview:{...value.overview,project:{project_uuid:'other'}}}])assert.equal(validProjectPresentation(invalid,'p','/p'),false);
});
test('late previous-project disk reads cannot publish into the current project',async()=>{
 const oldFetch=globalThis.fetch,pending=[];let tree,current;
 globalThis.fetch=(path,options)=>new Promise(resolve=>pending.push({path,options,resolve}));
 function Probe({id,path,enabled=true}){current=useProjectPresentation(id,path,{enabled});return null;}
 const render=async props=>act(()=>{const element=React.createElement(Probe,props);tree?tree.update(element):tree=TestRenderer.create(element);});
 try{
  await render({id:'a',path:'/a'});await render({id:'b',path:'/b'});assert.equal(pending[0].options.signal.aborted,true);
  await act(()=>pending[0].resolve(new Response(JSON.stringify(snapshot('a','/a')))));assert.equal(current,null);
  await act(()=>pending[1].resolve(new Response(JSON.stringify(snapshot('b','/b')))));assert.equal(current.project_uuid,'b');
  await render({id:'b',path:'/b',enabled:false});assert.equal(pending.length,2);assert.ok(pending.every(call=>call.path==='/api/project/presentation'));
 }finally{await act(()=>tree.unmount());globalThis.fetch=oldFetch;}
});
