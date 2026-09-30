// Real mounted InspectionCellTree and hooks, with network/page I/O replaced.
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

export function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
export const cells=[{cell_uuid:'cell-A',label:'Cell3',date:'2026-06-11',epochs:65},{cell_uuid:'cell-B',label:'Cell3',date:'2026-06-11',epochs:4}];
export const sourceA={kind:'protocol',protocolId:'protocol-A',query:'cell_type=ON',queryRevision:'query-A'};
export function pageAt(cell='cell-A',offset=0,revision='query-A',kind='protocol'){
  const total=cells.find(item=>item.cell_uuid===cell)?.epochs??65;
  return {offset,total,...(kind==='protocol'?{query_revision:revision}:{revision}),
    epochs:Array.from({length:Math.min(60,total-offset)},(_,index)=>({epoch_uuid:`${cell}-${offset+index}`,cell_uuid:cell,start_time:'06/11/2026 12:00:00:000000'}))};
}
export async function createInspectionHarness(){
  const key=`__inspectionTest${Math.random().toString(36).slice(2)}`;
  const network={api:()=>{throw Error('Unexpected API call');},page:(source,request)=>({loading:false,error:null,reload(){},
    data:pageAt(request.cellUuid,request.offset,source.kind==='protocol'?source.queryRevision:source.treeRevision,source.kind)})};
  globalThis[key]=network;
  const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,
    server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{
      name:'inspection-fixtures',enforce:'pre',
      resolveId(id,importer){if(importer?.endsWith('/components/InspectionCellTree.jsx')){
        if(id==='../api.js')return '\0inspection-api';
        if(id==='../useEpochBrowserPage.js')return '\0inspection-page';
        if(id==='./Common.jsx')return '\0inspection-common';
        if(id==='./EpochInclusionToggle.jsx')return '\0inspection-inclusion';
      }},
      load(id){
        if(id==='\0inspection-api')return `export const api=(...args)=>globalThis[${JSON.stringify(key)}].api(...args);export const number=String;export const humanize=value=>value||'';`;
        if(id==='\0inspection-page')return `export const useEpochBrowserPage=(...args)=>globalThis[${JSON.stringify(key)}].page(...args);`;
        if(id==='\0inspection-common')return 'export const Status=({children})=>children;';
        if(id==='\0inspection-inclusion')return 'export default ()=>null;';
      },
    }]});
  const {default:InspectionCellTree}=await server.ssrLoadModule('/src/components/InspectionCellTree.jsx');
  let root;
  const branches=()=>root.root.findAll(node=>node.type?.name==='CellBranch');
  return {network,
    async render(props){await act(async()=>{const element=React.createElement(InspectionCellTree,props);if(root)root.update(element);else root=TestRenderer.create(element);});},
    get branch(){return branches()[0].props;},
    get errors(){return root.root.findAllByProps({role:'alert'}).map(node=>node.children.join(''));},
    get selecting(){return root.root.findAllByProps({role:'status'}).some(node=>node.children.join('')==='Selecting epoch range…');},
    get summaries(){return root.root.findAllByType('summary').map(node=>node.props);},
    async act(callback){await act(callback);},
    async selectCell(cell=cells[0]){let work;await act(()=>{work=branches()[0].props.onSelectCell(cell);});return {work};},
    async selectEpoch(index,event={},cell='cell-A',page=pageAt(cell,Math.floor(index/60)*60)){
      let work;const epoch=page.epochs[index-page.offset];
      await act(()=>{work=branches()[0].props.onSelect(event,{cellUuid:cell,index,uuid:epoch.epoch_uuid},epoch,page);});return {work};
    },
    async unmount(){await act(async()=>{root?.unmount();});root=null;},
    async close(){await this.unmount();await server.close();delete globalThis[key];},
  };
}
