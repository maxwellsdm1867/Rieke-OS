import test from 'node:test';
import assert from 'node:assert/strict';
import {createProjectPreferenceClient,preferenceStorageKey} from './projectPreferences.js';
import {moveProtocolPreference} from './ordering.js';

const projectId='a5790c6c-ddc0-40c0-8a98-66f7a613e82b';
function backend(state={}){
  let receipt={format:'rieke-project-preferences',version:1,project_uuid:projectId,revisions:{recent_searches:0,protocol_shortcuts:0},state:structuredClone(state)};
  const calls=[];
  return {calls,read:()=>structuredClone(receipt),async request(path,options){
    calls.push({path,options});
    if(!options)return structuredClone(receipt);
    const {field,value,expected_revision}=options.body;
    if(expected_revision!==receipt.revisions[field])throw new Error('Project preferences changed; reload before saving.');
    receipt={...receipt,revisions:{...receipt.revisions,[field]:expected_revision+1},state:{...receipt.state,[field]:structuredClone(value)}};
    return structuredClone(receipt);
  }};
}
function storage(initial={}){const values=new Map(Object.entries(initial));return {getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value)};}
const search={id:'history',predicate:{field:'protocol',operator:'contains',value:'History'},splits:'date,cell',pinned:true};

test('received project wins over stale browser pins and recent searches',async()=>{
  const server=backend({recent_searches:[search],protocol_shortcuts:{received:{section:'pinned',rank:1}}});
  const local=storage({[preferenceStorageKey(projectId,'recent_searches')]:'[]',[preferenceStorageKey(projectId,'protocol_shortcuts')]:JSON.stringify({old:{section:'main',rank:0}})});
  const client=createProjectPreferenceClient({projectId,request:server.request,storage:local});
  await client.load();
  assert.deepEqual(client.get('recent_searches').value,[search]);
  assert.deepEqual(client.get('protocol_shortcuts').value,{received:{section:'pinned',rank:1}});
  assert.equal(server.calls.length,1);
});

test('earlier browser shortcuts migrate once and disjoint field writes survive',async()=>{
  const server=backend();
  const local=storage({[preferenceStorageKey(projectId,'recent_searches')]:JSON.stringify([search]),[preferenceStorageKey(projectId,'protocol_shortcuts')]:JSON.stringify({saved:{section:'pinned',rank:0}})});
  const client=createProjectPreferenceClient({projectId,request:server.request,storage:local});
  await Promise.all([client.load(),client.load()]);
  assert.deepEqual(server.read().state.recent_searches,[search]);
  assert.deepEqual(server.read().state.protocol_shortcuts,{saved:{section:'pinned',rank:0}});
  await client.reload();
  assert.equal(server.calls.filter(call=>call.options).length,2);
});

test('writes queued during hydration apply to received state in sequence',async()=>{
  const server=backend({recent_searches:[search]});
  let release;
  const gate=new Promise(resolve=>{release=resolve;});
  const client=createProjectPreferenceClient({projectId,request:async(...args)=>{if(!args[1])await gate;return server.request(...args);},storage:storage()});
  const first=client.update('recent_searches',previous=>[...previous,{...search,id:'second'}]);
  const second=client.update('recent_searches',previous=>[...previous,{...search,id:'third'}]);
  release();await Promise.all([first,second]);
  assert.deepEqual(server.read().state.recent_searches.map(item=>item.id),['history','second','third']);
});

test('concurrent browser conflict reloads then reapplies intent to fresh pins',async()=>{
  const server=backend({protocol_shortcuts:{existing:{section:'main',rank:0}}});
  const client=createProjectPreferenceClient({projectId,request:server.request,storage:storage()});
  await client.load();
  await server.request('/project-preferences',{method:'PUT',body:{field:'protocol_shortcuts',value:{existing:{section:'main',rank:0},other:{section:'pinned',rank:0}},expected_revision:0}});
  await client.update('protocol_shortcuts',previous=>({...previous,new:{section:'pinned',rank:1}}));
  assert.deepEqual(Object.keys(server.read().state.protocol_shortcuts),['existing','other','new']);
});

test('save failures remain visible and never claim portable persistence',async()=>{
  const server=backend({recent_searches:[]});
  let fail=true;
  const client=createProjectPreferenceClient({projectId,request:(path,options)=>options&&fail?Promise.reject(new Error('disk full')):server.request(path,options),storage:storage()});
  await assert.rejects(client.update('recent_searches',[search]),/disk full/);
  assert.match(client.get('recent_searches').error,/could not be saved to the project/);
  assert.deepEqual(client.get('recent_searches').value,[search]);
  assert.deepEqual(server.read().state.recent_searches,[]);
  fail=false;
  await client.update('recent_searches',previous=>previous);
  assert.equal(client.get('recent_searches').error,null);
  assert.deepEqual(server.read().state.recent_searches,[search]);
});

test('unavailable browser storage still saves project state and wrong identity is refused',async()=>{
  const server=backend();
  const client=createProjectPreferenceClient({projectId,request:server.request,storage:{getItem(){throw Error('no storage');},setItem(){throw Error('no storage');}}});
  await client.update('recent_searches',[search]);
  assert.deepEqual(server.read().state.recent_searches,[search]);
  const foreign=createProjectPreferenceClient({projectId,request:async()=>({...server.read(),project_uuid:'foreign'})});
  await assert.rejects(foreign.load(),/identity/);
  assert.equal(foreign.get('recent_searches').loading,false);
});

test('focus refresh and unrelated successful saves preserve an unsaved failed change',async()=>{
  const server=backend({recent_searches:[],protocol_shortcuts:{}});
  const client=createProjectPreferenceClient({projectId,request:(path,options)=>options?.body.field==='recent_searches'?Promise.reject(new Error('disk unavailable')):server.request(path,options),storage:storage()});
  await assert.rejects(client.update('recent_searches',[search]));
  await client.refresh();
  await client.update('protocol_shortcuts',{pinned:{section:'pinned',rank:0}});
  assert.deepEqual(client.get('recent_searches').value,[search]);
  assert.match(client.get('recent_searches').error,/could not be saved/);
  assert.deepEqual(server.read().state.recent_searches,[]);
});

test('failed legacy migration survives page refresh and unrelated writes until explicit save retry',async()=>{
  const server=backend();
  const searchKey=preferenceStorageKey(projectId,'recent_searches');
  const shortcutKey=preferenceStorageKey(projectId,'protocol_shortcuts');
  const earlierPins={earlier:{section:'pinned',rank:0}};
  const local=storage({[searchKey]:JSON.stringify([search]),[shortcutKey]:JSON.stringify(earlierPins)});
  let failSearch=true;
  const request=(path,options)=>options?.body.field==='recent_searches'&&failSearch?Promise.reject(new Error('disk full')):server.request(path,options);
  const client=createProjectPreferenceClient({projectId,request,storage:local});
  await client.load();
  assert.deepEqual(client.get('recent_searches').value,[search]);
  assert.match(client.get('recent_searches').error,/Earlier device shortcuts could not be saved/);
  assert.deepEqual(JSON.parse(local.getItem(searchKey)),[search]);
  assert.equal(Object.hasOwn(server.read().state,'recent_searches'),false);
  assert.deepEqual(server.read().state.protocol_shortcuts,earlierPins);
  await client.update('protocol_shortcuts',previous=>({...previous,another:{section:'main',rank:1}}));
  assert.deepEqual(client.get('recent_searches').value,[search]);
  assert.deepEqual(JSON.parse(local.getItem(searchKey)),[search]);
  // A completely new client models closing/reloading the page, rather than
  // relying on the first client's in-memory legacy copy.
  const refreshed=createProjectPreferenceClient({projectId,request,storage:local});
  await refreshed.load();
  assert.deepEqual(refreshed.get('recent_searches').value,[search]);
  assert.match(refreshed.get('recent_searches').error,/disk full/);
  assert.deepEqual(JSON.parse(local.getItem(searchKey)),[search]);
  failSearch=false;
  await refreshed.update('recent_searches',previous=>previous);
  assert.equal(refreshed.get('recent_searches').error,null);
  assert.deepEqual(server.read().state.recent_searches,[search]);
  assert.deepEqual(server.read().state.protocol_shortcuts,{...earlierPins,another:{section:'main',rank:1}});
  const reopened=createProjectPreferenceClient({projectId,request,storage:local});
  const before=server.calls.filter(call=>call.options).length;
  await reopened.load();
  assert.deepEqual(reopened.get('recent_searches').value,[search]);
  assert.equal(server.calls.filter(call=>call.options).length,before);
});

test('sidebar move intent preserves another window pin when its revision conflicts',async()=>{
  const protocols=[{protocol_uuid:'first',name:'Experiment A'},{protocol_uuid:'second',name:'Experiment B'},{protocol_uuid:'typing',name:'SingleSpot'}];
  const original={first:{section:'main',rank:0},second:{section:'main',rank:1},typing:{section:'support',rank:0},unloaded:{section:'pinned',rank:9}};
  const server=backend({protocol_shortcuts:original});
  const client=createProjectPreferenceClient({projectId,request:server.request,storage:storage()});
  await client.load();
  await server.request('/project-preferences',{method:'PUT',body:{field:'protocol_shortcuts',expected_revision:0,value:moveProtocolPreference(original,protocols,'second','pinned')}});
  await client.update('protocol_shortcuts',previous=>moveProtocolPreference(previous,protocols,'first','pinned'));
  const saved=server.read().state.protocol_shortcuts;
  assert.equal(saved.first.section,'pinned');
  assert.equal(saved.second.section,'pinned');
  assert.equal(saved.second.rank,0);
  assert.equal(saved.first.rank,1);
  assert.deepEqual(saved.typing,{section:'support',rank:0});
  assert.deepEqual(saved.unloaded,original.unloaded);
});

test('malformed legacy entries never render or migrate while raw cache survives a failed save',async()=>{
  const server=backend();
  const key=preferenceStorageKey(projectId,'recent_searches');
  const raw=JSON.stringify([null,{id:'missing-predicate'}, {...search,id:'bad-group',predicate:{all:'not an array'}},
    {...search,id:'bad-child',predicate:{not:null}}, {...search,id:'bad-label',name:{}}, {...search,id:'bad-count',cell_count:true}, search, search]);
  const local=storage({[key]:raw});
  const attempts=[];
  let fail=true;
  const request=(path,options)=>{
    if(options){attempts.push(structuredClone(options.body.value));if(fail)return Promise.reject(new Error('offline'));}
    return server.request(path,options);
  };
  const client=createProjectPreferenceClient({projectId,request,storage:local});
  await client.load();
  assert.deepEqual(client.get('recent_searches').value,[search]);
  assert.deepEqual(attempts,[[search]]);
  assert.equal(local.getItem(key),raw);
  assert.match(client.get('recent_searches').error,/offline/);
  const refreshed=createProjectPreferenceClient({projectId,request,storage:local});
  await refreshed.load();
  assert.deepEqual(refreshed.get('recent_searches').value,[search]);
  assert.equal(local.getItem(key),raw);
  fail=false;
  await refreshed.update('recent_searches',previous=>previous);
  assert.deepEqual(server.read().state.recent_searches,[search]);
  assert.deepEqual(JSON.parse(local.getItem(key)),[search]);
});
