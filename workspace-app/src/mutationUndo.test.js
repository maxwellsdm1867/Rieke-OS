import test from 'node:test';
import assert from 'node:assert/strict';
import {createUndoHistory,shouldUndoData} from "./undo/mutationUndo.js";
import {persistUndo,installUndoShortcuts} from "./undo/useMutationUndo.js";
const action=(revision=1,id='original')=>({kind:'annotations',operations:[{target_kind:'epoch',target_uuid:id,profile_uuid:'scientist',expected_revision:revision,before_revision:revision-1,tags_add:[],tags_remove:['chosen']}]});

test('undo targets original identities after navigation; repeated shortcuts cannot race',async()=>{
 const h=createUndoHistory();h.project('project-A');h.record(action());
 let resolve,calls=0;
 const first=h.undo(async original=>{calls++;assert.equal(original.operations[0].target_uuid,'original');await new Promise(done=>resolve=done);return {revisions:{'a:epoch:original:scientist':2}};});
 assert.equal(await h.undo(()=>assert.fail('No raced inverse')),false);resolve();
 assert.equal(await first,true);assert.equal(calls,1);assert.equal(h.view().count,0);
});
test('sequential undo rebases only the preceding own target revision',async()=>{
 const h=createUndoHistory();h.project('A');h.record(action(1));h.record(action(2));
 await h.undo(async()=>({revisions:{'a:epoch:original:scientist':3}}));
 await h.undo(async previous=>{assert.equal(previous.operations[0].expected_revision,3);return {revisions:{}};});
 assert.equal(h.view().count,0);
});
test('session memory enforces action and byte limits; oversized gestures clear whole undo steps',()=>{
 const h=createUndoHistory({actions:3,bytes:2500});h.project('A');
 for(let i=0;i<10000;i++)h.record(action(1,`epoch-${i}`));
 assert.ok(h.view().count<=3);assert.ok(h.view().bytes<=2500);
 h.record({...action(),operations:Array.from({length:1000},(_,i)=>({...action().operations[0],target_uuid:`epoch-${i}`}))});
 assert.equal(h.view().count,0);assert.equal(h.view().bytes,0);assert.match(h.view().message,/memory limits/);
});
test('in-flight, failed and no-op gestures cannot be undone; project switching clears session history',async()=>{
 const h=createUndoHistory();h.project('A');h.record(action());const token=h.begin();
 assert.equal(await h.undo(()=>assert.fail()),false);
 h.complete(token,{kind:'annotations',operations:[]});assert.equal(h.view().count,1);
 h.failed();assert.equal(h.view().count,0);h.record(action());h.project('B');assert.equal(h.view().count,0);
 assert.equal(await h.undo(()=>assert.fail()),false);
});
test('conflicts leave history intact and never auto-replay',async()=>{
 const h=createUndoHistory();h.project('A');h.record(action());let calls=0;
 assert.equal(await h.undo(()=>{calls++;throw Error('Original tag revision changed');}),false);
 assert.equal(calls,1);assert.equal(h.view().count,1);assert.match(h.view().message,/not confirmed/);
});
test('unfinished text keeps native undo; cleared saved tag input hands off exactly once',()=>{
 assert.equal(shouldUndoData({tagName:'INPUT',value:'unfinished',getAttribute:()=> 'true'}),false);
 assert.equal(shouldUndoData({tagName:'INPUT',value:'',getAttribute:()=>null}),false);
 assert.equal(shouldUndoData({tagName:'INPUT',value:'',getAttribute:()=> 'true'}),true);
 assert.equal(shouldUndoData({isContentEditable:true}),false);
 assert.equal(shouldUndoData({tagName:'BUTTON'}),true);
 assert.equal(shouldUndoData({tagName:'INPUT',readOnly:true,value:'/project'}),true);
 assert.equal(shouldUndoData({tagName:'INPUT',type:'checkbox'}),true);
});
test('curation undo reads only original targets and sends mixed minimal inverse in one mutation',async()=>{
 const a={kind:'curation',protocol_uuid:'p',operations:[{epoch_uuid:'first',expected_revision:2,changes:{included:true}},{epoch_uuid:'second',expected_revision:5,changes:{included:false,tags_add:['removed']}}]},calls=[];
 const result=await persistUndo(a,async(path,options)=>{calls.push({path,...options});return calls.length===1?{query_revision:'new',expected_binding_version:3,epochs:[{epoch_uuid:'first',curation_revision:2},{epoch_uuid:'second',curation_revision:5}]}:{curation:{first:{revision:3,included:true},second:{revision:6,included:false,tags:['removed']}}};});
 assert.equal(calls.length,2);assert.deepEqual(calls[0].body.epoch_uuids,['first','second']);
 assert.deepEqual(calls[1].body.per_epoch_changes,{first:{included:true},second:{included:false,tags_add:['removed']}});
 assert.equal(result.revisions['c:p:second'],6);
});
test('a stale original target prevents every inverse write in a batch',async()=>{
 let calls=0;
 await assert.rejects(persistUndo({kind:'curation',protocol_uuid:'p',operations:[{epoch_uuid:'first',expected_revision:2,changes:{included:true}}]},async()=>{calls++;return {epochs:[{epoch_uuid:'first',curation_revision:3}]};}),/changed/);
 assert.equal(calls,1);
});
test('temporary search inclusion undo is local and has no scientific mutation path',async()=>{
 const h=createUndoHistory();h.project('A');let included=false;
 h.local('viewer',value=>{included=value.prior;return {revisions:{}};});
 h.record({kind:'search-inclusion',viewer:'viewer',epoch_uuid:'original',prior:true,after:false});
 await h.undo(()=>assert.fail('No API mutation for local inclusion'));
 assert.equal(included,true);assert.equal(h.view().count,0);
});

test('browser and Electron use one authoritative gesture path, including delayed DOM delivery',async()=>{
 let listener=null,menu,data=0,text=0,prevented=0,stopped=0;
 const documentObject={activeElement:{tagName:'INPUT',value:'unfinished',getAttribute:()=>null},addEventListener:(name,fn)=>listener=fn,removeEventListener:()=>{listener=null;}};
 const bridge={onUndo:fn=>{menu=fn;return()=>menu=null;},undoText:()=>text++};
 const event=target=>({target,key:'z',metaKey:true,preventDefault:()=>prevented++,stopImmediatePropagation:()=>stopped++});
 let stop=installUndoShortcuts({documentObject,bridge,run:()=>data++,enabled:true});
 assert.equal(listener,null,'Electron menu owns the shortcut; DOM cannot double-handle it');
 menu();assert.equal(text,1);assert.equal(data,0);
 documentObject.activeElement={tagName:'INPUT',value:'',getAttribute:()=> 'true'};
 menu();await Promise.resolve();assert.equal(data,1);assert.equal(text,1);
 // A delayed DOM key event arrives after the first save completed. There is
 // no registered DOM handler, so even a fast successful inverse stays single.
 listener?.(event(documentObject.activeElement));assert.equal(data,1);
 stop();assert.equal(menu,null);
 stop=installUndoShortcuts({documentObject,bridge:null,run:()=>data++,enabled:true});
 listener(event(documentObject.activeElement));assert.equal(data,2);assert.equal(prevented,1);assert.equal(stopped,1);
 documentObject.activeElement={tagName:'INPUT',value:'unfinished',getAttribute:()=>null};
 listener(event(documentObject.activeElement));assert.equal(data,2);assert.equal(prevented,1);
 stop();assert.equal(listener,null);
});
test('compact 1000-target gestures fit the session budget without repeated tag or profile strings',async()=>{
 const h=createUndoHistory();h.project('A');
 const compact={kind:'annotations',target_kind:'epoch',profile_uuid:'scientist',patterns:[{tags_add:[],tags_remove:['tag']}],targets:Array.from({length:1000},(_,i)=>[`00000000-0000-0000-0000-${String(i).padStart(12,'0')}`,1,0,0])};
 h.record(compact);assert.equal(h.view().count,1);assert.ok(h.view().bytes<512*1024);
 await h.undo(value=>{assert.equal(value.patterns.length,1);assert.equal(value.targets.length,1000);return {revisions:{}};});
 assert.equal(h.view().bytes,0);
});

test('a confirmed SQL inverse with failed recovery is never offered for replay',async()=>{
 const h=createUndoHistory();h.project('A');h.record(action());
 const error=Object.assign(Error('Recovery copy failed'),{saved:true});
 await h.undo(()=>{throw error;});assert.equal(h.view().count,0);
 assert.match(h.view().message,/inverse edit was saved to the database/);
 let calls=0;assert.equal(await h.undo(()=>calls++),false);assert.equal(calls,0);
});
