import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

async function setup(){
 const h=await createWorkflowHarness();
 h.fixture.respond=(url,options,fallback)=>{
  const route=url.pathname.replace('/api','');
  if(route==='/cells/cell-0/qc')return {cell:{cell_uuid:'cell-0',label:'Cell 0',date:'2026-10-07',cell_type:'RGC/ON-parasol'},counts:{epochs:2},families:[{id:'a',label:'Family A',epoch_count:1},{id:'b',label:'Family B',epoch_count:1}]};
  if(route==='/cells/cell-0/qc/epochs'){
   const id=['a','default'].includes(url.searchParams.get('family'))?'epoch-0':'epoch-1';
   const result={family:id==='epoch-0'?'a':'b',epochs:[{epoch_uuid:id,epoch_number:id==='epoch-0'?1:2}],total:1};
   return h.fixture.holdRows?.(url,options,result)??result;
  }
  if(route==='/cells/cell-0/qc/response'){
   const result={cell_uuid:'cell-0',epoch_uuid:url.searchParams.get('epoch_uuid'),statistics:{pre:{mean:1},stim:{mean:2},delta_mean:1,units:'mV'}};
   return h.fixture.holdSummary?.(url,options,result)??result;
  }
  return fallback();
 };
 const Component=await h.component('CellQC');await h.mount(Component,{cellUuid:'cell-0',revision:0});
 const frame=()=>h.root.findByProps({className:'stable-content qc-recording-frame'});
 await h.waitFor(()=>frame().props['aria-busy']===false&&h.root.findAllByProps({className:'qc-trace-identity'}).length>0);
 return {h,Component,frame,family:name=>h.root.findByProps({className:'qc-families'}).findAllByType('button').find(n=>n.findByType('span').children.join('')===name)};
}

test('QC renders the exact new trial without waiting for a delayed response summary',async()=>{
 const {h,frame,family}=await setup();let release;
 try{
  const identity=h.root.findByProps({className:'qc-cell-type'});
  assert.equal(identity.findByType('h1').children.join(''),'Cell 0');
  assert.equal(identity.findByProps({className:'qc-cell-date'}).children.join(''),'2026-10-07');
  assert.equal(h.root.findAllByProps({className:'qc-heading'}).length,0);
  assert.ok(h.root.findByProps({className:'qc-toolbar'}).findByProps({'aria-label':'Copy cell UUID'}));
  assert.ok(identity.findAllByType('svg').some(node=>node.props.style?.color==='var(--cell-on)'&&node.props['aria-hidden']===true));
  const list=h.root.findByProps({className:'qc-trial-list'}),recording=h.root.findByProps({className:'qc-recording'});
  h.fixture.holdSummary=(url,options,value)=>value.epoch_uuid==='epoch-1'?new Promise(resolve=>release=()=>resolve(value)):value;
  await h.act(()=>family('Family B').props.onClick());await h.waitFor(()=>!!release);
  assert.equal(h.root.findByProps({className:'qc-trial-list'}),list);
  assert.equal(h.root.findByProps({className:'qc-recording'}),recording);
  await h.waitFor(()=>!frame().props['aria-busy']);
  assert.equal(h.root.findByProps({className:'qc-trace-identity'}).findByType('code').children.join(''),'epoch-1');
  assert.equal(h.root.findAllByProps({className:'qc-response-stats'}).length,0,'Old trial statistics cannot accompany the new trace');
  await h.act(()=>release());await h.waitFor(()=>!frame().props['aria-busy']);
  assert.equal(h.root.findByProps({className:'qc-recording'}),recording);
  assert.equal(h.root.findByProps({className:'qc-trace-identity'}).findByType('code').children.join(''),'epoch-1');
  const start=h.fixture.requests.length;await h.act(()=>family('Family B').props.onClick());
  assert.equal(h.fixture.requests.length,start);
 }finally{release?.();await h.close();}
});

test('late QC family responses cannot overwrite latest intent and authority refresh cannot reuse the old frame',async()=>{
 const {h,Component,frame,family}=await setup();let pending;
 try{
  h.fixture.holdRows=(url,options,value)=>url.searchParams.get('family')==='b'?new Promise(resolve=>pending={signal:options.signal,resolve:()=>resolve(value)}):value;
  await h.act(()=>family('Family B').props.onClick());await h.waitFor(()=>!!pending);
  await h.act(()=>family('Family A').props.onClick());await h.waitFor(()=>!frame().props['aria-busy']);
  assert.equal(pending.signal.aborted,true);await h.act(()=>pending.resolve());
  assert.equal(h.root.findByProps({className:'qc-trace-identity'}).findByType('code').children.join(''),'epoch-0');
  h.fixture.holdRows=(_url,_options,value)=>new Promise(resolve=>pending={resolve:()=>resolve(value)});
  await h.render(Component,{cellUuid:'cell-0',revision:1});
  assert.equal(h.root.findAllByProps({className:'qc-trace-identity'}).length,0);
 }finally{pending?.resolve();await h.close();}
});

test('a tag-only change reloads the epoch detail but not samples, QC summaries or trial pages',async()=>{
 const {h,Component}=await setup();
 try{
  await h.render(Component,{cellUuid:'cell-0',revision:0,structureRevision:0});
  const start=h.fixture.requests.length;
  await h.render(Component,{cellUuid:'cell-0',revision:1,structureRevision:0});
  await h.waitFor(()=>h.fixture.requests.slice(start).some(r=>r.path.startsWith('/epochs/epoch-0')));
  await h.waitFor(()=>h.root.findAllByProps({className:'qc-trace-identity'}).length>0);
  const paths=h.fixture.requests.slice(start).map(r=>r.path.split('?')[0]);
  assert.ok(paths.includes('/epochs/epoch-0'),'Epoch detail carries annotations and follows tag edits');
  assert.deepEqual(paths.filter(path=>path.startsWith('/cells/')||path.includes('/trace')),[],paths.join(', '));
  const before=h.fixture.requests.length;
  await h.render(Component,{cellUuid:'cell-0',revision:2,structureRevision:1});
  await h.waitFor(()=>h.fixture.requests.slice(before).some(r=>r.path.startsWith('/cells/cell-0/qc?')||r.path==='/cells/cell-0/qc'));
 }finally{await h.close();}
});

test('a confirmed QC tag is shown from its write receipt with no rereads',async()=>{
 const {h,Component}=await setup();const changes=[];
 try{
  await h.render(Component,{cellUuid:'cell-0',revision:0,structureRevision:0,annotationRevision:0,onAnnotationsChanged:(result,confirmed)=>changes.push(confirmed)});
  const tags=h.root.findAllByType('button').find(node=>node.findAllByType('svg').length&&node.children.some(child=>child==='Tags'||child?.includes?.('Tags')));
  await h.act(()=>tags.props.onClick());
  const input=()=>h.root.findAllByType('input').find(node=>node.props['aria-label']?.startsWith('Tag ')&&!node.props['aria-label'].startsWith('Tag to add'));
  await h.waitFor(()=>{try{return !!input()&&!input().props.disabled;}catch{return false;}});
  const before=h.fixture.requests.length;
  await h.act(()=>input().props.onChange({target:{value:'qc-tag'}}));
  await h.act(()=>input().parent.props.onSubmit({preventDefault(){}}));
  await h.waitFor(()=>changes.length===1);
  await new Promise(resolve=>setTimeout(resolve,200));
  assert.deepEqual(h.fixture.requests.slice(before).map(row=>row.method+' '+row.path.split('?')[0]),['POST /annotations']);
  assert.equal(changes[0]?.version,1,'The confirmed receipt is passed to the app');
  const text=JSON.stringify(h.root.findByProps({className:'page cell-qc'}).findAll(node=>typeof node.children?.[0]==='string').map(node=>node.children.join('')));
  assert.match(text,/qc-tag/);
 }finally{await h.close();}
});


test('legacy Other sessions restore the selected exact protocol and discard the combined-list offset',async()=>{
 const h=await createWorkflowHarness();
 try{
  h.fixture.respond=(url,options,fallback)=>{
   const route=url.pathname.replace('/api','');
   if(route==='/cells/cell-0/qc')return {cell:{cell_uuid:'cell-0',label:'Cell 0'},counts:{epochs:2},families:[
    {id:'protocol:lab.Movie',label:'Movie',epoch_count:1,protocol_names:['lab.Movie']},
    {id:'protocol:lab.Noise',label:'Noise',epoch_count:1,protocol_names:['lab.Noise']}]};
   if(route==='/cells/cell-0/qc/epochs')return {epochs:[{epoch_uuid:url.searchParams.get('family')==='protocol:lab.Noise'?'epoch-1':'epoch-0'}],total:1};
   if(route==='/cells/cell-0/qc/response')return {cell_uuid:'cell-0',epoch_uuid:url.searchParams.get('epoch_uuid'),statistics:{units:'mV'}};
   if(route==='/epochs/epoch-1')return {...fallback(),protocol_name:'lab.Noise'};
   return fallback();
  };
  const Component=await h.component('CellQC');
  await h.mount(Component,{cellUuid:'cell-0',revision:0,session:{family:'other',offset:40,selected:'epoch-1'}});
  const selected=()=>h.root.findByProps({className:'qc-families'}).findAllByType('button').find(node=>node.props['aria-pressed']);
  await h.waitFor(()=>selected()?.findByType('span').children.join('')==='Noise');
  await h.waitFor(()=>h.root.findAllByProps({className:'qc-trace-identity'}).some(node=>node.findByType('code').children.join('')==='epoch-1'));
  const pages=h.fixture.requests.filter(request=>request.path.includes('/qc/epochs?')).map(request=>new URL(request.path,'http://fixture').searchParams);
  assert.ok(pages.some(query=>query.get('family')==='protocol:lab.Noise'));
  assert.ok(pages.every(query=>query.get('offset')==='0'));
  assert.ok(pages.every(query=>query.get('family')!=='other'));
 }finally{await h.close();}
});


test('QC revisit reuses bounded reads while refresh and structure revisions renew them',async()=>{
 const {h,Component}=await setup();
 try{
  const props={cellUuid:'cell-0',revision:0,structureRevision:0};
  await h.render(Component,props);
  const before=h.fixture.requests.length;
  await h.render(Component,{...props,key:'revisit'});
  await h.waitFor(()=>h.root.findAllByProps({className:'qc-trace-identity'}).length>0);
  assert.deepEqual(h.fixture.requests.slice(before).filter(r=>r.path.startsWith('/cells/')),[]);
  await h.act(()=>h.root.findByProps({'aria-label':'Refresh cell quality'}).props.onClick());
  await h.waitFor(()=>h.fixture.requests.slice(before).filter(r=>r.path.startsWith('/cells/')).length===3);
  const refreshed=h.fixture.requests.length;
  await h.render(Component,{...props,key:'revisit',structureRevision:1});
  await h.waitFor(()=>h.fixture.requests.slice(refreshed).filter(r=>r.path.startsWith('/cells/')).length===3);
 }finally{await h.close();}
});

test('first trial reads precede a held overview and late default pages cannot replace explicit family choice',async()=>{
 const h=await createWorkflowHarness();let releaseOverview,pendingDefault,holdOverview=true,holdDefault=false;
 const overview={cell:{cell_uuid:'cell-0',label:'Cell 0'},counts:{epochs:2},families:[{id:'a',label:'Family A',epoch_count:1},{id:'b',label:'Family B',epoch_count:1}]};
 try{
  h.fixture.respond=(url,options,fallback)=>{
   const route=url.pathname.replace('/api','');
   if(route==='/cells/cell-0/qc')return holdOverview?new Promise(resolve=>releaseOverview=()=>resolve(overview)):overview;
   if(route==='/cells/cell-0/qc/epochs'){
    const family=url.searchParams.get('family')==='b'?'b':'a';
    const value={family,epochs:[{epoch_uuid:family==='a'?'epoch-0':'epoch-1'}],total:1};
    return holdDefault&&url.searchParams.get('family')==='default'?new Promise(resolve=>pendingDefault={signal:options.signal,release:()=>resolve(value)}):value;
   }
   if(route==='/cells/cell-0/qc/response')return {cell_uuid:'cell-0',epoch_uuid:url.searchParams.get('epoch_uuid'),statistics:{units:'mV'}};
   return fallback();
  };
  const Component=await h.component('CellQC');await h.mount(Component,{cellUuid:'cell-0',revision:0});
  await h.waitFor(()=>h.fixture.requests.some(r=>r.path.startsWith('/cells/cell-0/qc/response?')));
  assert.ok(releaseOverview,'Overview is still pending while the trial and response load');
  holdOverview=false;await h.act(()=>releaseOverview());
  await h.waitFor(()=>h.root.findAllByProps({className:'qc-trace-identity'}).length>0);
  holdDefault=true;await h.act(()=>h.root.findByProps({'aria-label':'Refresh cell quality'}).props.onClick());
  await h.waitFor(()=>!!pendingDefault);
  const button=h.root.findByProps({className:'qc-families'}).findAllByType('button').find(n=>n.findByType('span').children.join('')==='Family B');
  await h.act(()=>button.props.onClick());
  await h.waitFor(()=>h.root.findAllByProps({className:'qc-trace-identity'}).some(n=>n.findByType('code').children.join('')==='epoch-1'));
  await h.act(()=>pendingDefault.release());
  assert.equal(h.root.findByProps({className:'qc-trace-identity'}).findByType('code').children.join(''),'epoch-1');
 }finally{releaseOverview?.();pendingDefault?.release();await h.close();}
});


async function anchoredSetup({held=false}={}){
 const h=await createWorkflowHarness();let release;
 h.fixture.respond=(url,options,fallback)=>{
  const route=url.pathname.replace('/api','');
  if(route==='/cells/cell-0/qc')return {cell:{cell_uuid:'cell-0',label:'Cell 0'},counts:{epochs:101},families:[{id:'expanding_spots',label:'Spots',epoch_count:1,protocol_names:['Spots']},{id:'protocol:Test',label:'Test',epoch_count:100,protocol_names:['Test']}]};
  if(route==='/cells/cell-0/qc/epochs'){
   const anchor=url.searchParams.get('anchor_epoch_uuid'),family=anchor?'protocol:Test':url.searchParams.get('family');
   const offset=anchor?40:Number(url.searchParams.get('offset'));
   const epochs=family==='expanding_spots'?[{epoch_uuid:'epoch-0',epoch_number:1}]:Array.from({length:Math.min(40,100-offset)},(_,i)=>({epoch_uuid:`epoch-${offset+i}`,epoch_number:offset+i+1}));
   const page={family,offset,limit:40,total:family==='expanding_spots'?1:100,has_more:family!=='expanding_spots'&&offset+40<100,epochs,...(anchor?{anchor_epoch_uuid:anchor}:{})};
   if(anchor&&held)return new Promise(resolve=>release=()=>resolve(page));
   return page;
  }
  if(route==='/cells/cell-0/qc/response')return {cell_uuid:'cell-0',epoch_uuid:url.searchParams.get('epoch_uuid'),statistics:{pre:{mean:1},stim:{mean:2},delta_mean:1,units:'mV'}};
  return fallback();
 };
 const Component=await h.component('CellQC');await h.mount(Component,{cellUuid:'cell-0',initialEpochUuid:'epoch-73',revision:0});
 return {h,release:()=>release?.()};
}

test('epoch entry shows its exact trial and page before ordinary next-page navigation',async()=>{
 const {h}=await anchoredSetup();
 try{
  await h.waitFor(()=>h.fixture.requests.some(r=>r.path.includes('family=protocol%3ATest&offset=40')));
  await h.waitFor(()=>h.root.findByProps({className:'qc-trial-list'}).findAllByType('button').length===40);
  const trial=h.root.findByProps({className:'qc-trial-list'}).findAllByType('button').find(n=>n.props['aria-pressed']);
  assert.ok(trial);assert.match(trial.findByType('span').children.join(''),/Epoch 74$/);
  assert.equal(h.root.findByProps({className:'qc-trace-identity'}).findByType('code').children.join(''),'epoch-73');
  const footer=h.root.findByProps({className:'qc-trials'}).findByType('footer');
  assert.ok(footer.findByType('span').children.join('').includes('41'));
  await h.act(()=>footer.findAllByType('button').find(n=>n.children.includes('Next')).props.onClick());
  await h.waitFor(()=>h.root.findAllByProps({className:'qc-trace-identity'}).some(n=>n.findByType('code').children.join('')==='epoch-80'));
  assert.equal(h.fixture.requests.filter(r=>r.path.includes('anchor_epoch_uuid')).length,1);
 }finally{await h.close();}
});

test('explicit protocol choice wins over a late epoch-entry anchor response',async()=>{
 const {h,release}=await anchoredSetup({held:true});
 try{
  await h.waitFor(()=>h.root.findAllByProps({className:'qc-families'}).length>0);
  const spots=h.root.findByProps({className:'qc-families'}).findAllByType('button').find(n=>n.findByType('span').children.join('')==='Spots');
  await h.act(()=>spots.props.onClick());
  await h.waitFor(()=>h.root.findAllByProps({className:'qc-trace-identity'}).some(n=>n.findByType('code').children.join('')==='epoch-0'));
  await h.act(()=>release());
  assert.equal(h.root.findByProps({className:'qc-trace-identity'}).findByType('code').children.join(''),'epoch-0');
  assert.equal(h.root.findByProps({className:'qc-families'}).findAllByType('button').find(n=>n.props['aria-pressed']).findByType('span').children.join(''),'Spots');
 }finally{release();await h.close();}
});
