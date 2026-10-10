import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkspacePresentationSessions} from './workspacePresentationSessions.js';
const route=(page,key=page,details={})=>({page,key,...details});
const protocol=(key='protocol-route',id='protocol-A')=>route('protocol',key,{protocol:id});

test('remember retains exact routes and updates only each destination fallback',()=>{
 const owner=createWorkspacePresentationSessions();
 const stores={marker:'stores'},explorer={marker:'explorer'},qc={marker:'qc'},first={marker:'first'},second={marker:'second'};
 owner.remember(route('stores'),stores);owner.remember(route('explore'),explorer);owner.remember(route('cell-qc'),qc);
 owner.remember(protocol(),first);owner.remember(protocol('other-route'),second);
 assert.equal(owner.read(route('stores')).session,stores);assert.equal(owner.read(route('stores','fresh')).session,stores);
 assert.equal(owner.read(route('explore')).session,explorer);
 assert.equal(owner.read(route('explore','fresh',{resumeExplorer:true})).session,explorer);
 assert.equal(owner.read(route('explore','fresh')).session,null);
 assert.equal(owner.read(route('cell-qc')).session,qc);assert.equal(owner.read(route('cell-qc','fresh')).session,undefined);
 assert.deepEqual(owner.read(protocol()),{session:first,restoreSession:true});
 assert.deepEqual(owner.read(protocol('fresh')),{session:second,restoreSession:false});
 assert.deepEqual(owner.read(protocol('fresh','protocol-B')),{session:undefined,restoreSession:false});
});

test('lookup preserves route truthiness and protocol presence as distinct facts',()=>{
 for(const value of [null,undefined,false,0,'',NaN]){
  const owner=createWorkspacePresentationSessions(),fallback={marker:'fallback'};
  owner.restore({sessions:[['present',value]],protocolSessions:[['protocol-A',fallback]],lastExplorerSession:fallback,lastStoresSession:fallback});
  assert.deepEqual(owner.read(protocol('present')),{session:fallback,restoreSession:true});
  assert.deepEqual(owner.read(protocol('absent')),{session:fallback,restoreSession:false});
  assert.equal(owner.read(route('stores','present')).session,fallback);
  assert.equal(owner.read(route('explore','present',{resumeExplorer:true})).session,fallback);
  assert.equal(owner.read(route('explore','present',{resumeExplorer:false})).session,null);
  assert.ok(Object.is(owner.read(route('cell-qc','present')).session,value));
 }
 const owner=createWorkspacePresentationSessions(),exact={marker:'exact'},fallback={marker:'fallback'};
 owner.restore({sessions:[['present',exact]],protocolSessions:[['protocol-A',fallback]],lastExplorerSession:fallback,lastStoresSession:fallback});
 for(const page of ['stores','explore','cell-qc','protocol'])assert.equal(owner.read(route(page,'present',{protocol:'protocol-A',resumeExplorer:true})).session,exact);
});

test('remember uses the supplied route owner and does not infer a later destination',()=>{
 const owner=createWorkspacePresentationSessions(),older=protocol('older','protocol-A'),newer=protocol('newer','protocol-B');
 owner.remember(older,{marker:'first'});owner.remember(newer,{marker:'current'});owner.remember(older,{marker:'late original'});
 assert.equal(owner.read(newer).session.marker,'current');assert.equal(owner.read(protocol('fresh','protocol-B')).session.marker,'current');
 assert.equal(owner.read(older).session.marker,'late original');assert.equal(owner.read(protocol('fresh','protocol-A')).session.marker,'late original');
 owner.remember(protocol('empty',''),{marker:'empty protocol'});
 assert.equal(owner.read(protocol('empty','')).session.marker,'empty protocol');assert.equal(owner.read(protocol('fresh','')).session,undefined);
});

test('checkpoint preserves five-field shape and shallow values while copying entry lists',()=>{
 const owner=createWorkspacePresentationSessions(),requested=protocol(),value={nested:{marker:'shared'}};
 owner.remember(requested,value);owner.remember(route('explore'),value);owner.remember(route('stores'),value);
 const first=owner.checkpoint(requested),second=owner.checkpoint(requested);
 assert.deepEqual(Object.keys(first),['route','sessions','protocolSessions','lastExplorerSession','lastStoresSession']);
 assert.equal(first.route,requested);assert.equal(first.sessions[0][1],value);assert.equal(first.protocolSessions[0][1],value);
 assert.equal(first.lastExplorerSession,value);assert.equal(first.lastStoresSession,value);
 assert.notEqual(first.sessions,second.sessions);assert.notEqual(first.sessions[0],second.sessions[0]);
 first.sessions[0][1]={marker:'replacement only in entry list'};first.protocolSessions.length=0;
 assert.equal(owner.read(requested).session,value);assert.equal(owner.read(protocol('fresh')).session,value);
 value.nested.marker='same referenced value';assert.equal(second.sessions[0][1].nested.marker,'same referenced value');
});

test('invalid non-object restore throws before changing any presentation state',()=>{
 const owner=createWorkspacePresentationSessions(),current=protocol(),value={marker:'retained'};
 owner.remember(current,value);owner.remember(route('stores'),value);owner.remember(route('explore'),value);
 const before=owner.checkpoint(current);
 for(const invalid of [null,undefined,false,true,0,1,'', 'invalid',()=>{},Symbol('invalid')]){
  assert.throws(()=>owner.restore(invalid),/The saved workspace view is invalid/);
  assert.deepEqual(owner.checkpoint(current),before);assert.equal(owner.read(current).session,value);
 }
});

test('restore accepts arrays and plain empty objects, replaces stores and returns the requested route unchanged',()=>{
 const owner=createWorkspacePresentationSessions();
 for(const empty of [[],{}]){
  owner.remember(protocol(),{marker:'discard'});owner.remember(route('stores'),{marker:'discard'});owner.remember(route('explore'),{marker:'discard'});
  assert.equal(owner.restore(empty),undefined);
  assert.deepEqual(owner.checkpoint(null),{route:null,sessions:[],protocolSessions:[],lastExplorerSession:null,lastStoresSession:null});
 }
 const invalidRoute={page:'unknown',key:'keep invalid route for navigation owner'};
 const value={marker:'restored'};
 assert.equal(owner.restore({route:invalidRoute,sessions:[['qc',value]]}),invalidRoute);
 assert.equal(owner.read(route('cell-qc','qc')).session,value,'stores are replaced without validating the requested route');
 assert.equal(owner.restore({route:false}),false);
});

test('one malformed pair clears its complete collection independently of the other collection',()=>{
 const invalidCollections=[null,undefined,{},'entries',[null],[['key']],[['key',1,'extra']],[[23,1]],[['valid',1],['bad']]];
 for(const invalid of invalidCollections){
  const owner=createWorkspacePresentationSessions(),valid={marker:'valid'};
  owner.restore({sessions:invalid,protocolSessions:[['protocol-A',valid]]});
  assert.deepEqual(owner.checkpoint(null).sessions,[]);assert.equal(owner.read(protocol('fresh')).session,valid);
  owner.restore({sessions:[['route',valid]],protocolSessions:invalid});
  assert.deepEqual(owner.checkpoint(null).protocolSessions,[]);assert.equal(owner.read(route('cell-qc','route')).session,valid);
 }
});

test('restore keeps duplicate-key last values and unrestricted entry values without normalizing them',()=>{
 const owner=createWorkspacePresentationSessions(),value={marker:'last'},callable=()=>{},token=Symbol('value');
 const entries=[['duplicate',1],['duplicate',value],['undefined',undefined],['false',false],['zero',0],['empty',''],['function',callable],['symbol',token],['empty-array',[]]];
 owner.restore({sessions:entries,protocolSessions:[['protocol-A',1],['protocol-A',value]]});
 assert.equal(owner.read(route('cell-qc','duplicate')).session,value);assert.equal(owner.read(protocol('fresh')).session,value);
 for(const [key,expected] of entries.slice(2))assert.equal(owner.read(route('cell-qc',key)).session,expected);
 assert.equal(owner.checkpoint(null).sessions.length,entries.length-1);
 entries[1][1]='changed input entry';entries.push(['later','not imported']);
 assert.equal(owner.read(route('cell-qc','duplicate')).session,value);assert.equal(owner.read(route('cell-qc','later')).session,undefined);
});

test('restore normalizes only last-session truthiness while remember retains its exact value',()=>{
 const owner=createWorkspacePresentationSessions();
 for(const value of [undefined,null,false,0,'',NaN]){
  owner.restore({lastStoresSession:value,lastExplorerSession:value});
  assert.equal(owner.checkpoint(null).lastStoresSession,null);assert.equal(owner.checkpoint(null).lastExplorerSession,null);
  owner.remember(route('stores'),value);owner.remember(route('explore'),value);
  assert.ok(Object.is(owner.checkpoint(null).lastStoresSession,value));assert.ok(Object.is(owner.checkpoint(null).lastExplorerSession,value));
 }
 for(const value of [{},[],1,'truthy']){
  owner.restore({lastStoresSession:value,lastExplorerSession:value});
  assert.equal(owner.checkpoint(null).lastStoresSession,value);assert.equal(owner.checkpoint(null).lastExplorerSession,value);
 }
});

test('source deletion prunes both route and protocol entries plus last explorer, clears last stores and leaves route alone',()=>{
 const owner=createWorkspacePresentationSessions();
 const value=marker=>({marker,selected:['gone-epoch','keep'],focused:'gone-cell',nested:{'gone-cell':true,keep:['gone-cell','keep']}});
 const routeValue=value('route'),protocolValue=value('protocol'),explorerValue=value('explorer'),storesValue=value('stores');
 owner.restore({sessions:[['qc',routeValue]],protocolSessions:[['protocol-A',protocolValue]],lastExplorerSession:explorerValue,lastStoresSession:storesValue});
 const current={page:'stores',key:'current',recipe:{epoch_uuid:'gone-epoch'},inspection:{cell_uuid:'gone-cell'}};
 owner.pruneDeleted({removedEpochs:['gone-epoch'],removedCells:['gone-cell']});
 const expected=marker=>({marker,selected:['keep'],focused:null,nested:{keep:['keep']}});
 assert.deepEqual(owner.read(route('cell-qc','qc')).session,expected('route'));
 assert.deepEqual(owner.read(protocol('fresh')).session,expected('protocol'));
 assert.deepEqual(owner.read(route('explore','fresh',{resumeExplorer:true})).session,expected('explorer'));
 assert.equal(owner.read(route('stores','fresh')).session,null);
 assert.equal(owner.checkpoint(current).route,current);assert.equal(current.recipe.epoch_uuid,'gone-epoch');
 assert.deepEqual(routeValue,value('route'),'pruning does not mutate prior shallow checkpoints or caller values');
});

test('source deletion with missing identity lists still clears last stores and preserves other values',()=>{
 const owner=createWorkspacePresentationSessions(),value={marker:'kept'};
 owner.remember(route('stores'),value);owner.remember(route('explore'),value);owner.pruneDeleted({});
 assert.equal(owner.read(route('stores','fresh')).session,null);
 assert.deepEqual(owner.read(route('stores')).session,value);assert.deepEqual(owner.read(route('explore','fresh',{resumeExplorer:true})).session,value);
});

test('independent owner instances share no retained presentation state',()=>{
 const first=createWorkspacePresentationSessions(),second=createWorkspacePresentationSessions(),value={marker:'first'};
 first.remember(protocol(),value);first.remember(route('stores'),value);
 assert.equal(second.read(protocol()).session,undefined);assert.equal(second.read(route('stores')).session,null);
 second.restore({sessions:[['qc',{marker:'second'}]]});second.pruneDeleted({removedEpochs:['first']});
 assert.equal(first.read(protocol()).session,value);assert.equal(first.read(route('cell-qc','qc')).session,undefined);
});

test('protocol viewing preference follows the latest choice while history retains its own focus',()=>{
 const owner=createWorkspacePresentationSessions();
 const whole={kind:'whole',start:0,count:20000},sample={kind:'sample',start:30000,count:1000};
 const older={inspector:{focused:'old'},tracePreference:whole},latest={inspector:{focused:'new'},tracePreference:sample};
 owner.remember(protocol('old'),older);owner.remember(protocol('new'),latest);
 const restored=owner.read(protocol('old')).session;
 assert.equal(restored.inspector,older.inspector);assert.equal(restored.tracePreference,sample);
 assert.equal(older.tracePreference,whole,'read must not mutate historical snapshots');
 assert.equal(owner.read(protocol('new')).session,latest);
 assert.equal(owner.read(protocol('other','protocol-B')).session,undefined);
 const restoredOwner=createWorkspacePresentationSessions();restoredOwner.restore(owner.checkpoint(protocol('old')));
 assert.equal(restoredOwner.read(protocol('old')).session.tracePreference,sample);
 owner.remember(protocol('new'),{...latest,tracePreference:whole});assert.equal(owner.read(protocol('old')).session.tracePreference,whole);
});
