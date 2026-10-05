import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './isolatedVite.js';
import {fileURLToPath} from 'node:url';

export async function createInspectorHarness({liveMetadata=true}={}){
  // These fixtures exercise live-detail navigation unless a test opts into the
  // separate trace-only path. Product preference defaults are tested directly.
  const previousStorage=globalThis.localStorage;
  globalThis.localStorage={getItem:key=>key==='workspace.inspector.liveMetadata'?String(liveMetadata):previousStorage?.getItem(key)??null,setItem:(key,value)=>{if(key==='workspace.inspector.liveMetadata')liveMetadata=value==='true';else previousStorage?.setItem(key,value);}};
  const key=`__inspectorTest${Math.random().toString(36).slice(2)}`;
  const fixture={resources:[],api:()=>{throw Error('Unexpected API request');},epoch:{epoch_uuid:'epoch-A',cell_uuid:'cell-A',curation:{tags:[],included:true,review_state:'unreviewed'}}};
  globalThis[key]=fixture;
  const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{
    name:'inspector-fixtures',enforce:'pre',
    resolveId(id,importer){if(importer?.endsWith('/epoch-browser/useEpochInspection.js')&&id==='../api.js')return '\0inspector-api';
      if(importer?.endsWith('/epoch-browser/ui/Inspector.jsx')){
      if(id==='../../tree-ancestors/treeBranchReads.jsx')return '\0inspector-tree-owner';
      if(id==='../../api.js')return '\0inspector-api';
      if(id==='../../components/NavigationLoading.jsx')return '\0inspector-loading';
      if(id==='../../components/Common.jsx')return '\0inspector-common';
      if(id.endsWith('.jsx'))return '\0inspector-child:'+id;
    }},
    load(id){
      if(id==='\0inspector-tree-owner')return 'export const useTreeBranchReads=()=>null;';
      if(id==='\0inspector-api')return `
        const fixture=globalThis[${JSON.stringify(key)}];
        export const api=(...args)=>fixture.api(...args);
        export {resolveCurationTargets,number,humanize} from '/src/api.js';
        export const useEpochPrefetch=()=>{};
        export const useResource=(path,revision,delayMs=0)=>{fixture.resources.push({path,revision,delayMs});return fixture.resource?.(path,revision)||({path,loading:false,error:null,reload:()=>{},data:path?.includes('/epochs?')?{offset:0,total:1,epochs:[fixture.epoch],cells:fixture.protocol.cells||[],query_revision:fixture.protocol.query_revision,expected_binding_version:fixture.protocol.expected_binding_version??0,...fixture.page}:path?.includes('/epochs/')?fixture.epoch:{fields:[]}});};
        export const useEpochResource=path=>({path,loading:false,error:null,reload:()=>{},data:path?fixture.epoch:null});`;
      if(id==='\0inspector-loading')return 'export const NavigationLoadingProvider=({children})=>children;';
      if(id==='\0inspector-common')return "export const SourceEligibilityNotice='source-notice',Badge='badge';";
      if(id.startsWith('\0inspector-child:'))return `export default ${JSON.stringify(id.includes('EpochViewer.jsx')?'inspector-viewer':'inspector-child')};`;
    },
  }]});
  const {default:Inspector}=await server.ssrLoadModule('/src/epoch-browser/ui/Inspector.jsx');
  const {WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');let root;
  return {fixture,
    async render(props,{port}={}){fixture.protocol=props.protocol;await act(async()=>{const inspector=React.createElement(Inspector,props);const element=port===undefined?inspector:React.createElement(WorkspaceRequestProvider,{port},inspector);if(root)root.update(element);else root=TestRenderer.create(element);});},
    get viewer(){return root.root.findByType('inspector-viewer').props;},
    get tags(){return this.viewer.tags.props.children.props;},
    async act(callback){await act(callback);},
    async close(){await act(async()=>root?.unmount());await server.close();delete globalThis[key];if(previousStorage===undefined)delete globalThis.localStorage;else globalThis.localStorage=previousStorage;},
  };
}
