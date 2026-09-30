// Mount the actual component with real React hooks/effects. Only network and
// child presentation are replaced; selection callbacks run through its props.
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

export function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
export async function createPagedTreeHarness(){
  const key=`__pagedTreeTest${Math.random().toString(36).slice(2)}`;
  const network={api:()=>{throw Error('Unexpected API request');}};globalThis[key]=network;
  const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{
    name:'selection-fixtures',enforce:'pre',
    resolveId(id,importer){if(importer?.endsWith('/components/PagedTree.jsx')){
      if(id==='../api.js')return '\0selection-api';
      if(id==='./HierarchyTree.jsx'||id==='./ColumnTree.jsx')return '\0selection-tree';
    }},
    load(id){if(id==='\0selection-api')return `export const api=(...args)=>globalThis[${JSON.stringify(key)}].api(...args);`;
      if(id==='\0selection-tree')return `export default 'tree-probe';`;},
  }]});
  const {default:PagedTree}=await server.ssrLoadModule('/src/components/PagedTree.jsx');
  let root;
  return {
    network,
    async render(props){await act(async()=>{const element=React.createElement(PagedTree,props);if(root)root.update(element);else root=TestRenderer.create(element);});},
    get tree(){return root.root.findByType('tree-probe').props;},
    get errors(){return root.root.findAllByProps({role:'alert'}).map(node=>node.children.join(''));},
    async act(callback){await act(callback);},
    async unmount(){await act(async()=>{root?.unmount();});root=null;},
    async close(){await this.unmount();await server.close();delete globalThis[key];},
  };
}
export const scopeA={protocolId:'same-protocol',filters:{cell_type:'A'},splits:'cell',revision:'view-A',selectedEpochs:[]};
export const pageAt=offset=>({kind:'epochs',revision:'old-revision',path:['opaque-cell-A'],offset,epochs:Array.from({length:offset?1:60},(_,i)=>({epoch_uuid:`epoch-A-${offset+i}`,cell_uuid:'cell-A'}))});
export async function startSelection(h,kind){
  let work;
  if(kind==='cell')await h.act(()=>{work=h.tree.onSelectBranch({value:'cell-A',path:['opaque-cell-A']},{field:'cell'},'old-revision');});
  else{
    await h.act(()=>h.tree.onSelectEpoch('epoch-A-0',pageAt(0).epochs[0],{},pageAt(0),0));
    await h.act(()=>{work=h.tree.onSelectEpoch('epoch-A-60',pageAt(60).epochs[0],{shiftKey:true},pageAt(60),0);});
  }
  return {work};
}
export async function selectionRaceCases(){
  const h=await createPagedTreeHarness(),cases=[];
  try{
    for(const kind of ['cell','range'])for(const change of ['unchanged','filter','revision','splits','predicate','protocol','expectedRevision']){
      const pending=deferred(),published=[],requests=[];let phase='initial';
      h.network.api=async(path,options)=>{requests.push({path,body:options.body,signal:options.signal});return pending.promise;};
      const before={...scopeA,onSelectCell:(cell,epoch)=>published.push({phase,cell,epoch_uuid:epoch.epoch_uuid}),setSelectedEpochs:ids=>published.push({phase,epoch_uuids:ids})};
      const updates={unchanged:{filters:{cell_type:'A'}},filter:{filters:{cell_type:'B'}},revision:{revision:'view-B'},splits:{splits:'date,cell'},predicate:{predicate:{all:[{field:'tag',operator:'eq',value:'B'}]}},protocol:{protocolId:'other-protocol'},expectedRevision:{expectedRevision:'new-revision'}};
      const after={...before,...updates[change]};
      await h.render(before);const {work}=await startSelection(h,kind);
      await h.render(after);phase='completed-after-rerender';
      await h.act(async()=>{pending.resolve(kind==='cell'?{...pageAt(0),epochs:[{epoch_uuid:'epoch-A',cell_uuid:'cell-A'}]}:pageAt(0));await work;});
      const late=published.filter(item=>item.phase===phase),expectedRange=Array.from({length:61},(_,i)=>`epoch-A-${i}`);
      const assertions=[
        {name:'scope change aborts pending request',passed:change==='unchanged'||requests[0].signal.aborted},
        {name:'scope change forbids publication from an old source identity',passed:change==='unchanged'||late.length===0},
        {name:'unchanged scope keeps exact UUID selection and order',passed:change!=='unchanged'||(late.length===1&&(kind==='cell'?late[0].cell==='cell-A'&&late[0].epoch_uuid==='epoch-A':JSON.stringify(late[0].epoch_uuids)===JSON.stringify(expectedRange)))},
        {name:'no unexplained callback error',passed:h.errors.length===0},
      ];
      cases.push({kind,change,started_filter:before.filters,current_filter:after.filters,started_revision:before.revision,current_revision:after.revision,old_request_aborted:requests[0].signal.aborted,published_after_rerender:late,requests:requests.map(({signal,...request})=>request),errors:h.errors,assertions});
      await h.unmount();
    }
    return cases;
  }finally{await h.close();}
}
