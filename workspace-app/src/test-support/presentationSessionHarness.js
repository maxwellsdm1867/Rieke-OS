// App composition characterization: real navigation, Protocol and draft owners.
// Probes replace visual children, never App's stores or the navigation hook.
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from './isolatedVite.js';

export const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
async function bounded(promise,label){
 let timer;try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(`Presentation fixture timed out: ${label}`)),2000);})]);}finally{clearTimeout(timer);}
}
export const draft=value=>({format:'rieke-renderer-draft',version:1,projectId:'project',value});
export async function createPresentationSessionHarness({route={page:'overview',key:'initial'},saved=null,delayDraft=false}={}){
 const browser=new JSDOM('<!doctype html><html><body></body></html>',{url:'http://fixture/'});
 const old=Object.fromEntries(['window','document','localStorage','fetch','Event','CustomEvent'].map(key=>[key,globalThis[key]]));
 const load=deferred(),loaded=deferred(),requests=[],saves=[],unexpected=[];
 browser.window.history.replaceState({riekeWorkspace:{route,index:0}},'');
 browser.window.localStorage.setItem('rieke.undo.enabled','false');
 browser.window.riekeDesktop={
  loadDraft:()=>{loaded.resolve();return load.promise;},
  saveDraft:async value=>{saves.push(value);},
  onPrepareClose:()=>()=>{},
 };
 globalThis.Event=browser.window.Event;globalThis.CustomEvent=browser.window.CustomEvent;
 globalThis.window=browser.window;globalThis.document=browser.window.document;globalThis.localStorage=browser.window.localStorage;
 function response(path){
  if(path==='/projects')return {current_project_uuid:'project',projects:[{uuid:'project',path:'/owned-fixture',name:'Fixture',current:true}]};
  if(path==='/overview')return {project:{project_uuid:'project',name:'Fixture'},protocols:[{protocol_uuid:'protocol-A',name:'A'},{protocol_uuid:'protocol-B',name:'B'}],sources:[]};
  if(path==='/app/appearance')return {theme:'light'};
  if(path==='/protocol-suggestions')return {suggestions:[{protocol_uuid:'protocol-A',candidate_revision_uuid:'candidate',status:'pending',diff_counts:{added:1,removed:0,changed:0}}]};
  if(path==='/workbench/summary')return {workbench_counts:[]};
  if(path==='/jobs')return {jobs:[]};
  if(/^\/protocols\/protocol-[AB]$/.test(path))return {definition:{protocol_uuid:path.split('/').at(-1),name:'Fixture protocol'},binding:{revision_uuid:'binding'},cells:[],counts:{epochs:0,cells:0,included:0},filters:{},source_eligibility:{}};
  if(/^\/protocols\/protocol-[AB]\/workbench$/.test(path))return {contract_version:1,queue_revision:'queue',pending_epoch_count:0,pending_cell_count:0,candidates:[],capabilities:{cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}};
  throw Error(`Unexpected presentation request: ${path}`);
 }
 globalThis.fetch=async(input,options={})=>{
  const url=new URL(input,'http://fixture'),record={path:url.pathname.replace(/^\/api/,''),method:options.method||'GET',body:options.body?JSON.parse(options.body):undefined};
  requests.push(record);
  try{
   if(record.method!=='GET')throw Error(`Unexpected presentation request: ${record.method} ${record.path}`);
   const value=response(record.path);return {ok:true,status:200,json:async()=>value};
  }catch(error){unexpected.push(error.message);throw error;}
 };
 const generic="export default 'presentation-child';export const ProjectRail='project-rail',ImportSuggestions='import-suggestions',ExportDestination='export-destination',AppearanceButton='appearance-button';export const IMPORT_TERMINAL=new Set();";
 const rootPath=fileURLToPath(new URL('../..',import.meta.url));
 let server,rendered,App,Protocol,flushDesktopDrafts;
 const restoreGlobals=()=>{try{browser.window.close();}finally{for(const [key,value] of Object.entries(old)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}};
 try{
 server=await createServer({root:rootPath,configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{
  name:'presentation-session-probes',enforce:'pre',
  resolveId(id,importer){
   if(id.endsWith('/annotationProfile.js'))return '\0presentation-profile';
   if(importer?.endsWith('/App.jsx')){
    if(id==='./protocol-tree-layout/useProtocolTreeLayout.js')return '\0presentation-layout';
    if(id==='./useImportQueue.js')return '\0presentation-import-queue';
    if(id==='./components/ProtocolInfographic.jsx')return '\0presentation-lazy';
    const probes={'./components/Inspector.jsx':'inspector','./components/MetadataExplorer.jsx':'explorer','./components/DataStores.jsx':'stores','./components/CellQC.jsx':'qc','./components/Overview.jsx':'overview','./components/ProtocolSidebar.jsx':'sidebar','./components/DesktopDraftRecovery.jsx':'draft-recovery','./components/ProjectNavigator.jsx':'project-navigation','./components/ProjectUnmountDialog.jsx':'unmount'};
    if(probes[id])return `\0presentation-probe-${probes[id]}`;
    if(id.endsWith('.jsx')&&!['./tree-ancestors/treeBranchReads.jsx','./search-activation/navigationReadCache.jsx','./incoming-workbench/ui/IncomingWorkbench.jsx','./components/Common.jsx'].includes(id))return '\0presentation-child';
   }
  },
  load(id){
   if(id.startsWith('\0presentation-probe-'))return `export default ${JSON.stringify('presentation-'+id.split('probe-')[1])};export const ProjectRail='project-rail';`;
   if(id==='\0presentation-profile')return "export const AnnotationProfileProvider=({children})=>children;export const useAnnotationProfile=()=>({profileUuid:'author',loading:false});";
   if(id==='\0presentation-layout')return "const order=['date','cell'];export default ()=>({order,remember:()=>{},ready:true,save:{status:'saved',version:1},reload:()=>{}});";
   if(id==='\0presentation-import-queue')return 'export default ()=>({busy:false,remaining:0,active:false});';
   if(id==='\0presentation-lazy')return 'export default ()=>null;';
   if(id==='\0presentation-child')return generic;
  },
 }]});
 await server.ssrLoadModule('\0presentation-lazy');
 ({default:App,Protocol}=await server.ssrLoadModule('/src/App.jsx'));
 ({flushDesktopDrafts}=await server.ssrLoadModule('/src/desktopLifecycle.js'));
 }catch(error){try{await server?.close();}catch{}finally{try{restoreGlobals();}catch{}}throw error;}
 if(!delayDraft)load.resolve(saved);
 const h={requests,saves,unexpected,browser,act,
  get root(){return rendered.root;},
  get protocol(){return rendered.root.findByType(Protocol).props;},
  get route(){return browser.window.history.state.riekeWorkspace.route;},
  probe(name){return rendered.root.findByType(`presentation-${name}`).props;},
  async mount(){await act(async()=>{rendered=TestRenderer.create(React.createElement(App));});await bounded(loaded.promise,'draft load registration');await h.waitFor(()=>h.root.findAllByType('presentation-sidebar').length>0||h.root.findAllByType('presentation-draft-recovery').length>0);},
  async waitFor(predicate){const deadline=Date.now()+2000;while(!predicate()){if(Date.now()>deadline)throw Error('Presentation fixture did not settle');await act(()=>new Promise(resolve=>setTimeout(resolve,5)));}},
  async resolveDraft(value){await act(async()=>{load.resolve(value);await load.promise;});},
  async checkpoint(){await act(async()=>{await bounded(flushDesktopDrafts(),'draft checkpoint');});return saves.at(-1).value.value;},
  async click(label){const button=h.root.findAllByType('button').find(node=>node.props['aria-label']===label||node.children.filter(child=>typeof child==='string').join('').trim()===label);if(!button)throw Error(`Missing button: ${label}`);await act(()=>button.props.onClick());},
  async history(direction){
   let receive;const event=new Promise(resolve=>{receive=resolve;browser.window.addEventListener('popstate',receive,{once:true});});
   try{await act(async()=>{const label=direction==='back'?'Back to previous workspace':'Forward to next workspace';const button=h.root.findAllByProps({'aria-label':label})[0];if(button.props.disabled)throw Error(`History ${direction} is disabled`);button.props.onClick();await bounded(event,`history ${direction} popstate`);});}
   finally{browser.window.removeEventListener('popstate',receive);}
  },
  async close(){
   let failure;
   try{await act(async()=>{rendered?.unmount();});}catch(error){failure=error;}
   try{await server.close();}catch(error){failure??=error;}
   finally{try{restoreGlobals();}catch(error){failure??=error;}}
   if(failure)throw failure;
   if(unexpected.length)throw Error(unexpected.join('\n'));
  },
 };
 return h;
}
