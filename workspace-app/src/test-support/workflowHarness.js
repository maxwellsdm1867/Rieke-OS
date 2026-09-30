// Mounted product hooks, Protocol, Inspector, annotation composer and cell tree.
// Browser layout/trace drawing and unrelated screens are deliberately omitted.
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
import path from 'node:path';

export async function createWorkflowHarness({total=500,baseline=false,delay=0,baselineRoot:configuredBaselineRoot=process.env.RIEKE_WORKFLOW_BASELINE_ROOT}={}){
  const rootPath=fileURLToPath(new URL('../..',import.meta.url));
  const key=`__workflow${Math.random().toString(36).slice(2)}`;
  const baselineRoot=configuredBaselineRoot?path.resolve(configuredBaselineRoot):path.resolve(rootPath,'../docs/dev/scale-audit-2026-09-29/frozen-100000-dense-recovery/snapshot/workspace-app/src');
  const fixture={total,generation:0,requests:[],nodes:new Map(),mounts:0,unmounts:0,failNextSave:false,delay,profile:{profileUuid:'author',profileName:'Scientist',loading:false},annotations:new Map(),cellAnnotations:new Map(),annotationVersions:new Map(),curations:new Map(),pending:new Set(),route:{page:'protocol',protocol:'protocol-A',key:'route-1',inspection:{epoch_uuid:'epoch-0'}}};
  globalThis[key]=fixture;
  const old={fetch:globalThis.fetch,window:globalThis.window,document:globalThis.document,localStorage:globalThis.localStorage};
  const memory=new Map();
  globalThis.localStorage={getItem:name=>memory.get(name)??null,setItem:(name,value)=>memory.set(name,value)};
  globalThis.window={innerWidth:1400,location:{href:'http://localhost/'}};
  globalThis.document={title:'',getElementById:()=>null,addEventListener:()=>{},removeEventListener:()=>{}};
  const targetReceipt=(kind,identity)=>({target_kind:kind,target_uuid:identity,
    tags:[...((kind==='cell'?fixture.cellAnnotations:fixture.annotations).get(identity)||[])].map(tag=>({tag,profile_uuid:'author',author_name:'Scientist',target_kind:kind,target_uuid:identity,revision:fixture.annotationVersions.get(`${kind}:${identity}`)||0})),
    revisions:fixture.annotationVersions.has(`${kind}:${identity}`)?{author:fixture.annotationVersions.get(`${kind}:${identity}`)}:{}});
  const annotations=identity=>{
    const cell=`cell-${Math.floor(Number(identity.split('-').at(-1))/500)}`,direct=targetReceipt('epoch',identity),inherited=targetReceipt('cell',cell);
    return {epoch_uuid:identity,cell_uuid:cell,cell_tags:inherited.tags,epoch_tags:direct.tags,effective_tags:[...inherited.tags,...direct.tags],revisions:{cell:inherited.revisions,epoch:direct.revisions}};
  };
  const epoch=number=>({epoch_uuid:`epoch-${number}`,cell_uuid:`cell-${Math.floor(number/500)}`,cell_label:`Cell ${Math.floor(number/500)}`,date:'2026-09-29',protocol_name:'Test',streams:[],curation:{tags:fixture.curations.get(`epoch-${number}`)||[],included:true,revision:fixture.generation},annotations:annotations(`epoch-${number}`)});
  function scope(query){
    const filtered=!!(query.get('tag')||query.get('tag_predicate')||query.get('tagged'));
    const second=(query.get('tag_predicate')||query.get('tag')||'').includes('B');
    const matches=(number,node)=>{
      if(node.all)return node.all.every(item=>matches(number,item));
      if(node.any)return node.any.some(item=>matches(number,item));
      if(node.not)return !matches(number,node.not);
      const value=annotations(`epoch-${number}`),scope=node.field.split('/')[1],tags=scope==='cell'?value.cell_tags:scope==='epoch'?value.epoch_tags:value.effective_tags;
      return node.operator==='contains'&&tags.some(item=>item.tag===node.value);
    };
    const ids=Array.from({length:fixture.total},(_,number)=>number).filter(number=>!filtered||(fixture.savedTagFilters?(query.get('tag_predicate')?matches(number,JSON.parse(query.get('tag_predicate'))):annotations(`epoch-${number}`).effective_tags.some(tag=>!query.get('tag')||tag.tag===query.get('tag'))):number%2===(second?1:0)));
    const cells=[],counts=new Map();
    for(const number of ids){const cell=Math.floor(number/500);counts.set(cell,(counts.get(cell)||0)+1);}
    for(const [cell,count] of counts)cells.push({cell_uuid:`cell-${cell}`,label:`Cell ${cell}`,date:'2026-09-29',cell_type:'ON',epochs:count});
    const selected=query.get('cell_uuid');return {cells,ids:selected?ids.filter(number=>`cell-${Math.floor(number/500)}`===selected):ids};
  }
  function result(url,options){
    const pathname=url.pathname.replace(/^\/api/,'');
    const body=options.body?JSON.parse(options.body):{};
    if(pathname==='/projects')return {current_project_uuid:'project',projects:[{uuid:'project',path:'/fixture',name:'Fixture',current:true}]};
    if(pathname==='/overview')return {project:{project_uuid:'project',name:'Fixture'},protocols:[{protocol_uuid:'protocol-A',name:'Test'}],sources:[]};
    if(pathname==='/protocol-suggestions')return {suggestions:[]};
    if(pathname==='/jobs')return {jobs:[]};
    if(pathname==='/metadata/status')return {status:'ready'};
    if(pathname==='/metadata/fields')return {fields:[]};
    if(pathname==='/annotation-tags'||pathname==='/tags')return {tags:[]};
    if(pathname==='/protocols/protocol-A'){
      const selected=scope(url.searchParams);
      return {definition:{protocol_uuid:'protocol-A',name:'Test'},query_revision:`query-${fixture.generation}`,expected_binding_version:2,cells:selected.cells,counts:{epochs:selected.ids.length,cells:selected.cells.length,included:selected.ids.length},filters:{},source_eligibility:{}};
    }
    if(pathname==='/protocols/protocol-A/epochs'){
      const selected=scope(url.searchParams),limit=Number(url.searchParams.get('limit')||60),anchor=url.searchParams.get('anchor_uuid');
      let offset=Number(url.searchParams.get('offset')||0);
      if(anchor){const index=selected.ids.indexOf(Number(anchor.split('-').at(-1)));offset=index<0?0:Math.floor(index/60)*60;}
      return {query_revision:`query-${fixture.generation}`,expected_binding_version:2,total:selected.ids.length,offset,limit,epochs:selected.ids.slice(offset,offset+limit).map(epoch),...(url.searchParams.get('include_cells')==='true'?{cells:selected.cells}:{})};
    }
    if(pathname==='/protocols/protocol-A/tree-fields')return {fields:[]};
    if(/^\/epochs\/epoch-\d+$/.test(pathname))return epoch(Number(pathname.split('-').at(-1)));
    if(/^\/epochs\/epoch-\d+\/annotations$/.test(pathname))return annotations(pathname.split('/')[2]);
    if(pathname==='/annotations/read')return {targets:Object.fromEntries(body.target_uuids.map(identity=>[identity,targetReceipt(body.target_kind,identity)]))};
    if(pathname==='/annotations'){
      if(fixture.failNextSave){fixture.failNextSave=false;return {failure:507,error:'Durable recovery copy failed; save unconfirmed'};}
      const storage=body.target_kind==='cell'?fixture.cellAnnotations:fixture.annotations;
      if(body.target_uuids.some(identity=>body.expected_revisions[identity]!==((fixture.annotationVersions.get(`${body.target_kind}:${identity}`))||0)))return {failure:409,error:'Annotation revision conflict'};
      let changed=0;
      for(const identity of body.target_uuids){const before=storage.get(identity)||[],values=new Set(before);for(const tag of body.tags_add)values.add(tag);for(const tag of body.tags_remove)values.delete(tag);const after=[...values].sort();if(JSON.stringify([...before].sort())!==JSON.stringify(after)){storage.set(identity,after);const key=`${body.target_kind}:${identity}`;fixture.annotationVersions.set(key,(fixture.annotationVersions.get(key)||0)+1);changed++;}}
      if(changed)fixture.generation++;
      return {changed,targets:Object.fromEntries(body.target_uuids.map(identity=>[identity,targetReceipt(body.target_kind,identity)]))};
    }
    if(pathname==='/protocols/protocol-A/curation/read')return {protocol_uuid:'protocol-A',query_revision:body.query_revision,expected_binding_version:body.expected_binding_version,epochs:body.epoch_uuids.map(identity=>({epoch_uuid:identity,cell_uuid:`cell-${Math.floor(Number(identity.split('-').at(-1))/500)}`,curation_revision:fixture.generation}))};
    if(pathname==='/protocols/protocol-A/curation'){
      if(fixture.failNextSave){fixture.failNextSave=false;return {failure:507,error:'Durable recovery copy failed; save unconfirmed'};}
      for(const identity of body.epoch_uuids){const tags=new Set(fixture.curations.get(identity)||[]);for(const tag of body.changes.tags_add||[])tags.add(tag);for(const tag of body.changes.tags_remove||[])tags.delete(tag);fixture.curations.set(identity,[...tags]);}
      fixture.generation++;return {changed:body.epoch_uuids.length};
    }
    if(pathname==='/protocols/protocol-A/exports')return {exports:[]};
    throw Error(`Unexpected mounted workflow request: ${pathname}`);
  }
  globalThis.fetch=async(input,options={})=>{
    const url=new URL(input,'http://fixture'),record={path:url.pathname.replace(/^\/api/, '')+url.search,method:options.method||'GET',body:options.body?JSON.parse(options.body):undefined,started:performance.now(),aborted:false};
    fixture.requests.push(record);fixture.pending.add(record);
    try{
      const latency=typeof fixture.delay==='function'?fixture.delay(record):fixture.delay;
      if(latency>0)await new Promise((resolve,reject)=>{const timer=setTimeout(resolve,latency);options.signal?.addEventListener('abort',()=>{clearTimeout(timer);reject(Object.assign(Error('Request cancelled'),{name:'AbortError'}));},{once:true});});
      if(options.signal?.aborted)throw Object.assign(Error('Request cancelled'),{name:'AbortError'});
      const value=fixture.respond?await fixture.respond(url,options,()=>result(url,options)):result(url,options);
      record.status=value?.failure||200;return {ok:!value?.failure,status:record.status,json:async()=>value};
    }catch(error){record.aborted=error.name==='AbortError';throw error;}
    finally{record.completed=performance.now();fixture.pending.delete(record);}
  };
  const generic=`export default 'workflow-child'; export const ProjectRail='project-rail',ImportSuggestions='import-suggestions',ExportDestination='export-destination';export const IMPORT_TERMINAL=new Set();`;
  const server=await createServer({root:rootPath,configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{
    name:'mounted-workflow',enforce:'pre',
    resolveId(id,importer){
      if(id.endsWith('/annotationProfile.js')||id==='./annotationProfile.js'||id==='../annotationProfile.js')return '\0workflow-profile';
      if(importer?.endsWith('/App.jsx')){
        if(id==='./useWorkspaceNavigation.js')return '\0workflow-navigation';
        if(id==='./useProtocolTreeLayout.js')return '\0workflow-layout';
        if(id==='./useImportQueue.js')return '\0workflow-import-queue';
        if(id.endsWith('.jsx')&&!['./components/Inspector.jsx','./components/Common.jsx','./components/MetadataRefresh.jsx'].includes(id))return id.includes('ProtocolExportDialog')?'\0workflow-dialog':'\0workflow-child';
      }
      if(importer?.endsWith('/components/Inspector.jsx')&&id.endsWith('.jsx')&&!['./AnnotationTags.jsx','./EpochTags.jsx','./Common.jsx','./NavigationLoading.jsx'].includes(id))return id==='./EpochViewer.jsx'?'\0workflow-viewer':'\0workflow-child';
    },
    async load(id){
      if(baseline&&['App.jsx','components/Inspector.jsx','components/AnnotationTags.jsx'].some(name=>id===path.join(rootPath,'src',name))){
        const code=await readFile(path.join(baselineRoot,path.relative(path.join(rootPath,'src'),id)),'utf8');
        return id.endsWith('/App.jsx')?code.replace('function Protocol(', 'export function Protocol('):code;
      }
      if(id==='\0workflow-profile')return `export const AnnotationProfileProvider=({children})=>children;export const useAnnotationProfile=()=>globalThis[${JSON.stringify(key)}].profile;`;
      if(id==='\0workflow-navigation')return `import {useState} from 'react';const f=globalThis[${JSON.stringify(key)}];export default function(){const [route,setRoute]=useState(f.route);f.navigate=(page,details={})=>setRoute({page,...details,key:page==='protocol'?'route-1':page});return {route,go:f.navigate,restore:setRoute,canBack:false,canForward:false};}`;
      if(id==='\0workflow-layout')return `const order=['date','cell','block'];export default ()=>({order,remember:()=>{},ready:true,save:{status:'saved',version:1},reload:()=>{}});`;
      if(id==='\0workflow-import-queue')return `export default ()=>({busy:false,remaining:0,active:false});`;
      if(id==='\0workflow-child')return generic;
      if(id==='\0workflow-dialog')return `import React from 'react';export default ({children,footer})=>React.createElement('workflow-dialog',null,children,footer);`;
      if(id==='\0workflow-viewer')return `import React,{useEffect} from 'react';import ProtocolViewFilter from '/src/components/ProtocolViewFilter.jsx';import InspectionCellTree from '/src/components/InspectionCellTree.jsx';const fixture=globalThis[${JSON.stringify(key)}];export default function Viewer(props){useEffect(()=>{fixture.mounts++;return()=>{fixture.unmounts++;};},[]);return React.createElement('workflow-viewer',props,React.createElement(ProtocolViewFilter,{filters:props.viewFilters,onChange:props.onViewFilters,revision:props.filterRevision,disabled:props.filterDisabled}),props.tags,props.before,React.createElement(InspectionCellTree,props.treePane.listProps));}`;
    },
  }]});
  const {default:App,Protocol}=await server.ssrLoadModule('/src/App.jsx');
  const {epochResourceCache}=await server.ssrLoadModule('/src/resourceCache.js');epochResourceCache.invalidate();
  let root;
  const harness={fixture,App,Protocol,async component(name){return (await server.ssrLoadModule(`/src/components/${name}.jsx`)).default;},
    async mount(component=App,props={}){await act(async()=>{root=TestRenderer.create(React.createElement(component,props),{createNodeMock:element=>{if(element.type==='input'){const node={focus:()=>{},closest:()=>null};fixture.nodes.set(element.props['aria-label'],node);return node;}return null;}});});},
    async render(component,props){await act(async()=>root.update(React.createElement(component,props)));},
    get root(){return root.root;},
    get viewer(){return root.root.findByType('workflow-viewer').props;},
    get tags(){return root.root.findByType('section').props;},
    async act(callback){await act(callback);},
    async settle(ms=230){await act(async()=>{await new Promise(resolve=>setTimeout(resolve,ms));});},
    async waitFor(predicate,{timeout=3000}={}){const end=performance.now()+timeout;while(!predicate()){if(performance.now()>end)throw Error('Mounted workflow condition timed out');await harness.settle(15);}},
    async close(){await act(async()=>root?.unmount());await server.close();delete globalThis[key];for(const [name,value] of Object.entries(old)){if(value===undefined)delete globalThis[name];else globalThis[name]=value;}},
  };
  return harness;
}
