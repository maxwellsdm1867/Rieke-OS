'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {ProjectViews}=require('../project-views.cjs');
const deferred=()=>{let resolve;return {promise:new Promise(done=>{resolve=done;}),get resolve(){return resolve;}};};
const binding=id=>({project_uuid:id,project_path:`/owned/${id}`,origin:`http://127.0.0.1:${4000+id}`,pid:id,created_at:1,session_id:'s'});
function fixture({prepare=async()=>({ready:true}),load=async()=>{},limit=3,admit=()=>true}={}){
 const created=[],registered=new Set(),attached=new Set();
 let windowDestroyed=false;const contentView={addChildView:view=>attached.add(view),removeChildView:view=>attached.delete(view)};
 const window={get contentView(){if(windowDestroyed)throw TypeError('Object has been destroyed');return contentView;},isDestroyed:()=>windowDestroyed,getContentSize:()=>[900,700]};
 const views=new ProjectViews({window,prepare,admit,limit,onRegister:owner=>registered.add(owner),onDispose:owner=>registered.delete(owner),createView:()=>{
  const messages=[];let destroyed=false;const contents={loads:[],messages,isDestroyed:()=>destroyed,loadURL:async url=>{contents.loads.push(url);await load(url);},send:(channel,value)=>messages.push({channel,value}),focus(){},close(){destroyed=true;}};
  const view={webContents:contents,setBounds:value=>{view.bounds=value;}};created.push(view);return view;
 }});
 return {views,created,registered,attached,destroyHost:()=>{windowDestroyed=true;attached.clear();}};
}
test('A B A reuses the exact document and emits visibility without reloading',async()=>{
 const h=fixture();await h.views.activate(binding(1),'a');const first=h.views.active;first.webContents.localState={scroll:400,draft:'keep'};
 await h.views.activate(binding(2),'b');assert.equal(first.active,false);
 await h.views.activate(binding(1),'a');assert.equal(h.views.active,first);assert.deepEqual(first.webContents.loads,['a']);assert.equal(first.webContents.localState.draft,'keep');
 assert.equal(h.created.length,2);assert.equal(h.attached.size,1);assert.deepEqual(first.view.bounds,{x:0,y:0,width:900,height:700});
 assert.deepEqual(first.webContents.messages.map(v=>v.value.visible),[true,false,true]);
});
test('failed draft preparation preserves an inactive document beyond the soft cap',async()=>{
 const h=fixture({limit:1,prepare:async()=>({ready:false,reason:'busy'})});await h.views.activate(binding(1),'a');const first=h.views.active;
 await h.views.activate(binding(2),'b');await h.views.trimming;
 assert.equal(h.views.owners.size,2);assert.equal(first.isDestroyed(),false);assert.equal(first.webContents.messages.at(-1).channel,'desktop:project-resume');
});
test('clean LRU eviction acknowledges drafts and closes only the inactive document',async()=>{
 const prepared=[];const h=fixture({limit:1,prepare:async owners=>{prepared.push(...owners);return {ready:true};}});
 await h.views.activate(binding(1),'a');const first=h.views.active;await h.views.activate(binding(2),'b');await h.views.trimming;
 assert.equal(prepared[0],first);assert.equal(first.isDestroyed(),true);assert.equal(h.views.owners.size,1);assert.equal(h.views.active.binding.project_uuid,2);
});
test('activation wins over a delayed eviction acknowledgment',async()=>{
 const wait=deferred();const h=fixture({limit:1,prepare:()=>wait.promise});await h.views.activate(binding(1),'a');const first=h.views.active;
 await h.views.activate(binding(2),'b');await h.views.activate(binding(1),'a');wait.resolve({ready:true});await h.views.trimming;
 assert.equal(first.isDestroyed(),false);assert.equal(h.views.active,first);assert.equal(first.webContents.messages.at(-1).channel,'desktop:project-resume');
});
test('same port with changed process incarnation does not borrow a retained document',async()=>{
 const h=fixture();await h.views.activate(binding(1),'a');const first=h.views.active;
 await h.views.activate({...binding(1),created_at:2},'a');assert.notEqual(h.views.active,first);assert.equal(h.created.length,2);
});
test('target close flushes hidden owner, blocks activation and can resume after refusal',async()=>{
 const targets=[];const h=fixture({prepare:async owners=>{targets.push(...owners);return {ready:true};}});
 await h.views.activate(binding(1),'a');const first=h.views.active;await h.views.activate(binding(2),'b');const identity={projectUuid:1,path:'/owned/1'};
 await h.views.prepareClose(identity);assert.equal(targets[0],first);await assert.rejects(h.views.activate(binding(1),'a'),/closing/);
 h.views.cancelClose(identity);await h.views.activate(binding(1),'a');assert.equal(h.views.active,first);
});
test('late first load cannot resurrect a view cleared by recovery',async()=>{
 const wait=deferred(),h=fixture({load:()=>wait.promise});const pending=h.views.activate(binding(1),'a');await Promise.resolve();await Promise.resolve();
 h.views.clear();wait.resolve();await assert.rejects(pending,/cancelled/);assert.equal(h.registered.size,0);assert.equal(h.attached.size,0);
});

test('recovery fences queued and loading activation without discarding preserved documents',async()=>{
 const wait=deferred();let blocked=false;
 const h=fixture({load:url=>url==='b'?wait.promise:Promise.resolve(),admit:()=>!blocked});
 await h.views.activate(binding(1),'a');const first=h.views.active;
 const pending=h.views.activate(binding(2),'b');await Promise.resolve();await Promise.resolve();
 const queued=h.views.activate(binding(1),'a');blocked=true;h.views.cancelActivations();wait.resolve();
 await assert.rejects(pending,/cancelled/);await assert.rejects(queued,/cancelled/);
 assert.equal(h.views.active,null);assert.equal(first.isDestroyed(),false);assert.equal(h.views.owners.size,2);
 blocked=false;await h.views.activate(binding(1),'a');assert.equal(h.views.active,first);
});

test('closed native host disposes active and detached documents without touching destroyed window',async()=>{
 const h=fixture();await h.views.activate(binding(1),'a');const first=h.views.active;
 await h.views.activate(binding(2),'b');const second=h.views.active;
 h.destroyHost();assert.doesNotThrow(()=>h.views.clear());
 assert.equal(h.views.active,null);assert.equal(h.views.owners.size,0);assert.equal(h.registered.size,0);
 assert.equal(first.isDestroyed(),true);assert.equal(second.isDestroyed(),true);assert.equal(second.active,false);
});
test('suspending after host destruction preserves documents for their explicit lifecycle',async()=>{
 const h=fixture();await h.views.activate(binding(1),'a');const owner=h.views.active;
 h.destroyHost();assert.doesNotThrow(()=>h.views.suspend());
 assert.equal(h.views.active,null);assert.equal(owner.active,false);assert.equal(owner.isDestroyed(),false);
 assert.equal(h.registered.has(owner),true);h.views.clear();assert.equal(owner.isDestroyed(),true);
});
