import {writeFile} from 'node:fs/promises';
import {createWorkflowHarness} from '../../../workspace-app/src/test-support/workflowHarness.js';
const rows=[];
for(const total of [500,100000])for(const enabled of [false,true,true,false]){
 const h=await createWorkflowHarness({total,enableUndo:enabled});
 const times=[],requests=[],sizes=[];
 try{
  h.fixture.respond=(url,options,fallback)=>{
   const value=fallback();if(url.pathname!=='/api/annotations')return value;
   const body=JSON.parse(options.body);
   if(enabled)value.undo={kind:'annotations',target_kind:body.target_kind,profile_uuid:body.profile_uuid,patterns:[{tags_add:[],tags_remove:body.tags_add}],targets:body.target_uuids.map(id=>[id,body.expected_revisions[id]+1,body.expected_revisions[id],0])};
   sizes.push(JSON.stringify(value).length);return value;
  };
  const input=()=>h.root.findByProps({'aria-label':'Tag this epoch'});
  const ready=()=>h.waitFor(()=>{try{return !!h.viewer.epoch&&!input().props.disabled;}catch{return false;}});
  await h.mount();await ready();
  for(let i=0;i<30;i++){
   await h.act(()=>input().props.onChange({target:{value:`tag-${i}`}}));
   const before=h.fixture.requests.length,start=performance.now();
   await h.act(()=>input().parent.props.onSubmit({preventDefault(){}}));await ready();
   times.push(performance.now()-start);
   requests.push(h.fixture.requests.slice(before).filter(row=>row.path==='/annotations'||row.path==='/annotations/read').length);
  }
  const sorted=[...times].sort((a,b)=>a-b);
  rows.push({total,enabled,repeats:times.length,median_ms:sorted[15],p95_ms:sorted[28],ordinary_annotation_requests:[...new Set(requests)],mean_receipt_bytes:sizes.reduce((a,b)=>a+b,0)/sizes.length});
 }finally{await h.close();}
}
await writeFile(new URL('./mounted.json',import.meta.url),JSON.stringify(rows,null,2));
console.log(JSON.stringify(rows));
