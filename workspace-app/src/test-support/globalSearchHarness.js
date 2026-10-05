import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
import {createServer} from './isolatedVite.js';

// Small source-mounted fixture. No browser, backend, recording or native writes.
export async function createGlobalSearchHarness({module='/src/search-activation/GlobalSearch.jsx',baseline=false,cacheOptions={},workspaceOwner=false}={}){
  const before={window:globalThis.window,fetch:globalThis.fetch};
  const listeners=new Map(),requests=[];
  const window={addEventListener:(name,callback)=>{if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(callback);},removeEventListener:(name,callback)=>listeners.get(name)?.delete(callback),riekeDesktop:{onStatus:callback=>{listeners.set('desktop-status',new Set([callback]));return()=>listeners.delete('desktop-status');}}};
  globalThis.window=window;
  const fixture={requests,result:{results:[{kind:'cell',id:'cell-a',cell_uuid:'cell-a',label:'Synthetic cell A',detail:'One recording'}],total:1}};
  const profileKey=`__searchProfileFixture${Math.random().toString(36).slice(2)}`;
  if(workspaceOwner){fixture.profile={profileUuid:'author-a',loading:false,error:''};globalThis[profileKey]=fixture;}
  globalThis.fetch=async(url,options={})=>{requests.push({url,method:options.method||'GET',signal:options.signal});
    const value=fixture.respond?await fixture.respond(url,options):fixture.result;
    return {ok:!value?.fixtureStatus,status:value?.fixtureStatus||200,json:async()=>value};};
  const checkpoint=baseline?await readFile(new URL('./fixtures/globalSearch-checkpoint.jsx',import.meta.url),'utf8'):null;
  const plugins=baseline?[{name:'checkpoint-search',resolveId(id,importer){if(id==='/src/checkpoint-search.jsx')return id;if(importer==='/src/checkpoint-search.jsx'&&id==='../api.js')return fileURLToPath(new URL('../api.js',import.meta.url));if(importer==='/src/checkpoint-search.jsx'&&id==='./GlobalSearch.css')return fileURLToPath(new URL('../search-activation/GlobalSearch.css',import.meta.url));},load(id){if(id==='/src/checkpoint-search.jsx')return checkpoint;}}]:[];
  if(workspaceOwner)plugins.push({name:'search-profile-fixture',enforce:'pre',resolveId(id){if(id==='../annotationProfile.js')return '\0search-profile';},load(id){if(id==='\0search-profile')return `export const useAnnotationProfile=()=>globalThis[${JSON.stringify(profileKey)}].profile;`;}});
  const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins});
  let Component,Provider;
  try{({default:Component}=await server.ssrLoadModule(baseline?'/src/checkpoint-search.jsx':module));if(!baseline){const owners=await server.ssrLoadModule('/src/search-activation/navigationReadCache.jsx');Provider=owners[workspaceOwner?'WorkspaceReadCacheOwner':'NavigationReadProvider'];const {createPageReadCache}=await server.ssrLoadModule('/src/search-activation/pageReadCache.js');fixture.cache=createPageReadCache({...cacheOptions,now:()=>fixture.at??performance.now()});}}
  catch(error){await server.close();delete globalThis[profileKey];globalThis.window=before.window;globalThis.fetch=before.fetch;throw error;}
  let rendered;
  const h={fixture,act,async render({projectId='synthetic-project-a',projectOpenIdentity='synthetic-open-a',actorId='synthetic-actor-a',...props}={}){await act(async()=>{let element=React.createElement(Component,props);if(Provider)element=React.createElement(Provider,{projectId,projectOpenIdentity,actorId,cache:fixture.cache},element);if(rendered)rendered.update(element);else rendered=TestRenderer.create(element,{createNodeMock:element=>element.type==='dialog'?{showModal(){},close(){},getBoundingClientRect:()=>({left:0,right:700,top:0,bottom:500})}:{focus(){}}});});},
    get root(){return rendered.root;},
    async waitFor(predicate){const until=Date.now()+1500;while(!predicate()){if(Date.now()>until)throw Error('Search fixture did not settle');await act(()=>new Promise(resolve=>setTimeout(resolve,10)));}},
    async unmount(){await act(async()=>{rendered?.unmount();rendered=null;});},
    async event(name,value){await act(async()=>{for(const callback of listeners.get(name)||[])callback(value);});},
    load:specifier=>server.ssrLoadModule(specifier),listenerCount:name=>listeners.get(name)?.size||0,
    async close(){await h.unmount();await server.close();delete globalThis[profileKey];globalThis.window=before.window;globalThis.fetch=before.fetch;},
  };
  return h;
}
