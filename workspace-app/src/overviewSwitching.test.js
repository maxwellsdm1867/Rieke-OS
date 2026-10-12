import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
import {createOverviewCache} from './protocol-overview/overviewCache.js';
import {deferred} from './test-support/pagedTreeHarness.js';

const props={id:'protocol-A',projectId:'project',revision:0,structureRevision:0,onChange(){}};
const summary=h=>h.root.findAllByType('workflow-child').find(n=>n.props.data?.counts?.epochs!==undefined);

test('actual Protocol returns render the cached overview without a summary request or loading screen',async()=>{
 const h=await createWorkflowHarness(),cache=createOverviewCache();
 try{
  await h.mount(h.Protocol,{...props,overviewCache:cache});await h.waitFor(()=>summary(h));
  const count=h.fixture.requests.filter(r=>r.path==='/protocols/protocol-A/overview').length;
  assert.equal(summary(h).props.data.counts.epochs,500);
  await h.render('div',{});await h.render(h.Protocol,{...props,overviewCache:cache});
  assert.equal(summary(h).props.data.counts.epochs,500);
  assert.equal(h.root.findAllByProps({className:'status'}).length,0);
  assert.equal(h.fixture.requests.filter(r=>r.path==='/protocols/protocol-A/overview').length,count);
 }finally{await h.close();cache.clear();}
});

test('an invalidated overview retains its presentation while awaiting the correct changed count',async()=>{
 const h=await createWorkflowHarness(),cache=createOverviewCache(),pending=deferred();
 try{
  await h.mount(h.Protocol,{...props,overviewCache:cache});await h.waitFor(()=>summary(h));
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/overview')?pending.promise:fallback();
  await h.render(h.Protocol,{...props,revision:1,structureRevision:1,overviewCache:cache});
  assert.equal(summary(h).props.data.counts.epochs,500);
  const next={...summary(h).props.data,counts:{epochs:501,cells:1,included:501},query_revision:'query-1'};
  await h.act(()=>pending.resolve(next));await h.waitFor(()=>summary(h)?.props.data.counts.epochs===501);
  assert.equal(h.fixture.requests.filter(r=>r.path==='/protocols/protocol-A/overview').length,2);
 }finally{pending.resolve({});await h.close();cache.clear();}
});

test('project overview stays cached across protocol navigation in actual App',async()=>{
 const h=await createWorkflowHarness();
 h.fixture.route={page:'protocol',protocol:'protocol-A',key:'route-1'};
 try{
  await h.mount();await h.waitFor(()=>summary(h));
  const count=h.fixture.requests.filter(r=>r.path==='/overview').length;
  await h.act(()=>h.fixture.navigate('overview'));
  await h.act(()=>h.fixture.navigate('protocol',{protocol:'protocol-A'}));await h.waitFor(()=>summary(h));
  assert.equal(h.fixture.requests.filter(r=>r.path==='/overview').length,count);
  assert.equal(h.fixture.requests.filter(r=>r.path==='/protocols/protocol-A/overview').length,1);
 }finally{await h.close();}
});
