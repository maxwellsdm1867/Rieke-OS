import test from 'node:test';
import assert from 'node:assert/strict';
import {createPresentationSessionHarness,draft} from './test-support/presentationSessionHarness.js';
const checkpoint=(route,extra={})=>({route,sessions:[],protocolSessions:[],lastExplorerSession:null,lastStoresSession:null,...extra});
const savedProtocol=marker=>({tab:'inspect',filters:{},inspector:{focused:marker,marker,treeMode:true}});
const inspector=h=>h.waitFor(()=>h.root.findAllByType('presentation-inspector').length>0);
const goProtocol=(h,id)=>h.act(()=>h.probe('sidebar').onNavigate(id));

test('App restores the exact earlier protocol route before the latest protocol fallback',async()=>{
 const h=await createPresentationSessionHarness();
 try{
  await h.mount();await goProtocol(h,'protocol-A');await h.click('Inspect');await inspector(h);
  const firstKey=h.route.key;await h.act(()=>h.probe('inspector').onSessionChange({focused:'first',marker:'first',treeMode:true}));
  await goProtocol(h,'protocol-B');await goProtocol(h,'protocol-A');await inspector(h);
  const secondKey=h.route.key;assert.notEqual(secondKey,firstKey);
  assert.equal(h.probe('inspector').initialNavigation.marker,'first');
  assert.equal(h.probe('inspector').initialNavigation.treeMode,false,'fresh visit normalizes ordinary saved navigation');
  await h.act(()=>h.probe('inspector').onSessionChange({focused:'second',marker:'second',treeMode:false}));
  await h.history('back');await h.history('back');await inspector(h);
  assert.equal(h.route.key,firstKey);assert.equal(h.probe('inspector').initialNavigation.marker,'first');
  assert.equal(h.probe('inspector').initialNavigation.treeMode,true);
 }finally{await h.close();}
});

test('App preserves falsy route-entry presence while Protocol initializes from fallback before recipe',async()=>{
 const route={page:'protocol',protocol:'protocol-A',key:'falsy',recipe:{name:'recipe would export',filters:{tag:'recipe'}}};
 const fallback=savedProtocol('fallback');
 const h=await createPresentationSessionHarness({saved:draft(checkpoint(route,{sessions:[['falsy',null]],protocolSessions:[['protocol-A',fallback]]}))});
 try{
  await h.mount();await h.waitFor(()=>h.root.findAllByProps({'aria-label':'Protocol tools'}).length>0);
  assert.equal(h.root.findAllByType('presentation-inspector').length,1,'restoration presence must prefer fallback inspection over recipe export');
  assert.equal(h.protocol.restoreSession,true);assert.equal(h.protocol.session.inspector.marker,'fallback');
  assert.equal(h.probe('inspector').initialNavigation.marker,'fallback');
  assert.equal(h.root.findAllByProps({'aria-label':'Inspect'})[0].props['aria-selected'],true);
 }finally{await h.close();}
});

test('an old Inspector callback retains its original App route and protocol owner',async()=>{
 const h=await createPresentationSessionHarness();
 try{
  await h.mount();await goProtocol(h,'protocol-A');await h.click('Inspect');await inspector(h);
  const original=h.route.key,oldSave=h.probe('inspector').onSessionChange;
  await h.act(()=>oldSave({focused:'first',marker:'first'}));
  await goProtocol(h,'protocol-B');await h.click('Inspect');await inspector(h);
  const current=h.route.key;assert.notEqual(current,original);
  await h.act(()=>h.probe('inspector').onSessionChange({focused:'current',marker:'current'}));
  await h.act(()=>oldSave({focused:'late-original',marker:'late-original'}));
  const saved=await h.checkpoint();
  assert.equal(new Map(saved.sessions).get(current).inspector.marker,'current');
  assert.equal(new Map(saved.protocolSessions).get('protocol-B').inspector.marker,'current');
  assert.equal(new Map(saved.protocolSessions).get('protocol-A').inspector.marker,'late-original');
  await h.history('back');await inspector(h);assert.equal(h.route.key,original);
  assert.equal(h.probe('inspector').initialNavigation.marker,'late-original');
  await h.history('forward');await inspector(h);assert.equal(h.route.key,current);
  assert.equal(h.probe('inspector').initialNavigation.marker,'current');
 }finally{await h.close();}
});

for(const [page,value,fallback,resume,expected] of [
 ['stores',{marker:'exact-store'},{marker:'last-store'},false,'exact-store'],
 ['stores',false,{marker:'last-store'},false,'last-store'],
 ['explore',{marker:'exact-explore'},{marker:'last-explore'},true,'exact-explore'],
 ['explore',0,{marker:'last-explore'},true,'last-explore'],
 ['explore',null,{marker:'last-explore'},false,null],
 ['cell-qc',false,{marker:'must-not-fallback'},true,false],
])test(`App ${page} session lookup preserves value ${JSON.stringify(value)} with resume ${resume}`,async()=>{
 const route={page,key:'lookup',cell_uuid:'cell',resumeExplorer:resume};
 const h=await createPresentationSessionHarness({saved:draft(checkpoint(route,{sessions:[['lookup',value]],lastStoresSession:fallback,lastExplorerSession:fallback}))});
 try{await h.mount();await h.waitFor(()=>h.root.findAllByType(`presentation-${page==='cell-qc'?'qc':page==='explore'?'explorer':page}`).length>0);
  const actual=h.probe(page==='cell-qc'?'qc':page==='explore'?'explorer':page).session;
  assert.equal(actual?.marker??actual,expected);
 }finally{await h.close();}
});

test('source deletion prunes every presentation store but leaves the current route intact',async()=>{
 const route={page:'stores',key:'store-route',recipe:{epoch_uuid:'gone-epoch'},inspection:{cell_uuid:'gone-cell'}};
 const selection=marker=>({marker,selected:['gone-epoch','keep'],nested:{focused:'gone-cell','gone-cell':true,keep:true}});
 const h=await createPresentationSessionHarness({saved:draft(checkpoint(route,{
  sessions:[['store-route',selection('store')],['qc-route',selection('qc')]],
  protocolSessions:[['protocol-A',{...savedProtocol('protocol'),selection:selection('protocol')}]],
  lastExplorerSession:selection('explorer'),lastStoresSession:selection('last-store'),
 }))});
 try{
  await h.mount();await h.waitFor(()=>h.root.findAllByType('presentation-stores').length>0);
  await h.act(()=>h.probe('stores').onChange({kind:'source-deleted',removedEpochs:['gone-epoch'],removedCells:['gone-cell']}));
  const value=await h.checkpoint();assert.deepEqual(h.route,route);assert.deepEqual(value.route,route);
  const pruned=(actual,marker)=>{assert.equal(actual.marker,marker);assert.deepEqual(actual.selected,['keep']);assert.deepEqual(actual.nested,{focused:null,keep:true});};
  pruned(new Map(value.sessions).get('store-route'),'store');pruned(new Map(value.sessions).get('qc-route'),'qc');
  pruned(new Map(value.protocolSessions).get('protocol-A').selection,'protocol');pruned(value.lastExplorerSession,'explorer');assert.equal(value.lastStoresSession,null);
  await h.click('Project overview');await h.click('Data stores');assert.equal(h.probe('stores').session,null,'last stores must be cleared');
  await goProtocol(h,'protocol-A');await inspector(h);assert.equal(h.protocol.session.selection.nested.focused,null);
 }finally{await h.close();}
});

test('invalid restored route keeps real history while permissive checkpoint stores replace earlier values',async()=>{
 const route={page:'stores',key:'stays-here'};
 const h=await createPresentationSessionHarness({route,delayDraft:true});
 try{
  await h.mount();await h.act(()=>h.probe('stores').onSession({marker:'before'}));
  const history=h.browser.window.history.state;
  await h.resolveDraft(draft(checkpoint({page:'unknown',key:'invalid'},{
   sessions:[['stays-here',{marker:'valid-but-entire-list-clears'}],[23,'bad-key']],
   protocolSessions:[['protocol-A',false],['protocol-A',savedProtocol('duplicate-last')],['arbitrary',0]],
   lastStoresSession:{marker:'after-fallback'},lastExplorerSession:false,
  })));
  await h.checkpoint();assert.equal(h.probe('stores').session?.marker,'after-fallback','invalid route must not block store replacement');
  assert.deepEqual(h.browser.window.history.state,history);assert.deepEqual(h.route,route);
  const value=await h.checkpoint();assert.deepEqual(value.sessions,[]);assert.equal(value.lastExplorerSession,null);
  assert.equal(new Map(value.protocolSessions).get('arbitrary'),0);
  await goProtocol(h,'protocol-A');await inspector(h);assert.equal(h.probe('inspector').initialNavigation.marker,'duplicate-last');
 }finally{await h.close();}
});

test('real history away and back advances intent and refuses a delayed desktop draft',async()=>{
 const h=await createPresentationSessionHarness({delayDraft:true});
 try{
  await h.mount();const initial=h.route.key;
  await h.click('Data stores');await h.history('back');assert.equal(h.route.key,initial);
  await h.resolveDraft(draft(checkpoint({page:'stores',key:'stale-draft'},{lastStoresSession:{marker:'stale'}})));
  const value=await h.checkpoint();assert.equal(value.route.key,initial);assert.equal(h.route.page,'overview');assert.equal(value.lastStoresSession,null);
 }finally{await h.close();}
});

test('restored merge intent has no live consent; an explicit App request is consumed without scientific writes',async()=>{
 const route={page:'protocol',protocol:'protocol-A',key:'restored-merge',workbench:{merge_intent:{kind:'preview_all',request_uuid:'old-consent',project_uuid:'project',protocol_uuid:'protocol-A'}}};
 const h=await createPresentationSessionHarness({saved:draft(checkpoint(route))});
 try{
  await h.mount();await h.waitFor(()=>h.root.findAllByProps({role:'status'}).some(node=>node.children.join('').includes('No pending incoming recordings.')));
  assert.ok(h.root.findAllByProps({role:'status'}).some(node=>node.children.join('').includes('no longer active')),'restored merge intent must be refused without live consent');
  assert.equal(h.route.workbench.merge_intent,undefined,'restored intent is consumed even though consent is refused');
  assert.equal(h.requests.some(row=>row.path.includes('preview')),false);assert.deepEqual(h.requests.filter(row=>row.method!=='GET'&&/\/(?:preview|accept|exports|draft|decisions)(?:\/|$)/.test(row.path)),[],'presentation restoration cannot preview, accept, export, or save scientific draft decisions');
  await h.click('Project overview');await goProtocol(h,'protocol-A');
  await h.act(()=>assert.equal(h.protocol.onMergeIncoming('protocol-A'),true));
  await h.waitFor(()=>h.root.findAllByProps({role:'status'}).some(node=>node.children.join('').includes('No pending incoming recordings to merge')));
  assert.equal(h.route.workbench.merge_intent,undefined);assert.deepEqual(h.requests.filter(row=>row.method!=='GET'&&/\/(?:preview|accept|exports|draft|decisions)(?:\/|$)/.test(row.path)),[],'presentation restoration cannot preview, accept, export, or save scientific draft decisions');
  const consumed=await h.checkpoint();assert.equal(consumed.route.workbench.merge_intent,undefined);
 }finally{await h.close();}
});


test('App unmount saveView and desktop flush publish the same checkpoint shape',async()=>{
 const h=await createPresentationSessionHarness({route:{page:'stores',key:'shared-checkpoint'}});
 try{
  await h.mount();const remembered={marker:'same-view',selected:['keep']};
  await h.act(()=>h.probe('stores').onSession(remembered));
  const desktop=await h.checkpoint();assert.equal(desktop.sessions[0][1],remembered,'checkpoint retains shallow session values');
  const project={uuid:'project',path:'/owned-fixture',name:'Fixture',current:true};
  await h.act(()=>h.probe('project-navigation').onUnmount(project));
  let discard;await h.act(()=>{discard=h.probe('unmount').saveView();});
  const raw=h.browser.window.localStorage.getItem('workspace.unmount-view.project:/owned-fixture');
  assert.deepEqual(JSON.parse(raw).value,JSON.parse(JSON.stringify(desktop)));
  discard();assert.equal(h.browser.window.localStorage.getItem('workspace.unmount-view.project:/owned-fixture'),null);
 }finally{await h.close();}
});


test('an absent protocol route key lets recipe initialization precede the protocol fallback',async()=>{
 const route={page:'protocol',protocol:'protocol-A',key:'absent',recipe:{name:'Recipe name',filters:{tag:'recipe'}}};
 const h=await createPresentationSessionHarness({saved:draft(checkpoint(route,{protocolSessions:[['protocol-A',savedProtocol('fallback')]]}))});
 try{
  await h.mount();await h.waitFor(()=>h.root.findAllByType('input').some(node=>node.props.value==='Recipe name'));
  assert.equal(h.root.findAllByType('presentation-inspector').length,0);
  assert.ok(h.root.findAllByType('input').some(node=>node.props.value==='Recipe name'),'recipe export initializes without restoration presence');
 }finally{await h.close();}
});

test('an array checkpoint is accepted and clears stores while its missing route leaves history intact',async()=>{
 const route={page:'stores',key:'array-checkpoint'};
 const h=await createPresentationSessionHarness({route,delayDraft:true});
 try{
  await h.mount();await h.act(()=>h.probe('stores').onSession({marker:'before-array'}));
  await h.resolveDraft(draft([]));const value=await h.checkpoint();
  assert.deepEqual(h.route,route);assert.deepEqual(value.sessions,[]);assert.deepEqual(value.protocolSessions,[]);
  assert.equal(value.lastStoresSession,null);assert.equal(value.lastExplorerSession,null);assert.equal(h.probe('stores').session,null);
 }finally{await h.close();}
});

test('same route key and protocol preserve the App session callback across restored route objects',async()=>{
 const route={page:'protocol',protocol:'protocol-A',key:'stable-callback'};
 const h=await createPresentationSessionHarness({route,delayDraft:true});
 try{
  await h.mount();const remember=h.protocol.onSession;
  const next={...route,inspection:{epoch_uuid:'changed-route-detail'}};
  await h.resolveDraft(draft(checkpoint(next)));await h.checkpoint();
  assert.deepEqual(h.route,next);assert.equal(h.protocol.onSession,remember,'callback dependencies use key and protocol, not the route object');
 }finally{await h.close();}
});
