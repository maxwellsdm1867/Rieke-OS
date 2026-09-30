import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

export async function createInspectorHarness(){
  const key=`__inspectorTest${Math.random().toString(36).slice(2)}`;
  const fixture={api:()=>{throw Error('Unexpected API request');},epoch:{epoch_uuid:'epoch-A',cell_uuid:'cell-A',curation:{tags:[],included:true,review_state:'unreviewed'}}};
  globalThis[key]=fixture;
  const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{
    name:'inspector-fixtures',enforce:'pre',
    resolveId(id,importer){if(importer?.endsWith('/components/Inspector.jsx')){
      if(id==='../api.js')return '\0inspector-api';
      if(id==='./NavigationLoading.jsx')return '\0inspector-loading';
      if(id==='./Common.jsx')return '\0inspector-common';
      if(id.endsWith('.jsx'))return '\0inspector-child:'+id;
    }},
    load(id){
      if(id==='\0inspector-api')return `
        const fixture=globalThis[${JSON.stringify(key)}];
        export const api=(...args)=>fixture.api(...args);
        export {resolveCurationTargets,number,humanize} from '/src/api.js';
        export const useEpochPrefetch=()=>{};
        export const useResource=path=>({path,loading:false,error:null,reload:()=>{},data:path?.includes('/epochs?')?{offset:0,total:1,epochs:[fixture.epoch],cells:fixture.protocol.cells||[],query_revision:fixture.protocol.query_revision,expected_binding_version:fixture.protocol.expected_binding_version??0,...fixture.page}:{fields:[]}});
        export const useEpochResource=path=>({path,loading:false,error:null,reload:()=>{},data:path?fixture.epoch:null});`;
      if(id==='\0inspector-loading')return 'export const NavigationLoadingProvider=({children})=>children;';
      if(id==='\0inspector-common')return "export const SourceEligibilityNotice='source-notice',Badge='badge';";
      if(id.startsWith('\0inspector-child:'))return `export default ${JSON.stringify(id.includes('EpochViewer.jsx')?'inspector-viewer':'inspector-child')};`;
    },
  }]});
  const {default:Inspector}=await server.ssrLoadModule('/src/components/Inspector.jsx');let root;
  return {fixture,
    async render(props){fixture.protocol=props.protocol;await act(async()=>{const element=React.createElement(Inspector,props);if(root)root.update(element);else root=TestRenderer.create(element);});},
    get viewer(){return root.root.findByType('inspector-viewer').props;},
    get tags(){return this.viewer.tags.props.children.props;},
    async act(callback){await act(callback);},
    async close(){await act(async()=>root?.unmount());await server.close();delete globalThis[key];},
  };
}
