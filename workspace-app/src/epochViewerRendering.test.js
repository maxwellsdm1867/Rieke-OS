import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createElement} from 'react';
import {renderToString} from 'react-dom/server';
import {createServer} from 'vite';
import react from '@vitejs/plugin-react';

let server;
before(async()=>{
 server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,plugins:[react()],server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error'});
});
after(async()=>{await server?.close();});
function render(Component,props){
 const previous=console.error;
 // Layout effects intentionally wait for the browser; SSR still exercises
 // adapter render expressions (the null-epoch crash happened before effects).
 console.error=(message,...args)=>{if(!String(message).startsWith('Warning: useLayoutEffect does nothing on the server'))previous(message,...args);};
 try{return renderToString(createElement(Component,props));}finally{console.error=previous;}
}
test('opening a pinned inspector before any epoch is focused renders its empty state without dereferencing curation',async()=>{
 const {default:Inspector}=await server.ssrLoadModule('/src/components/Inspector.jsx');
 const html=render(Inspector,{protocol:{definition:{protocol_uuid:'fixture',name:'Variable History Noise'},cells:[]},filters:{},revision:0});
 assert.match(html,/Choose an epoch/);
 assert.match(html,/Epoch list controls/);
 assert.doesNotMatch(html,/Dataset-only tags:/);
 assert.doesNotMatch(html,/Include in analysis/);
});
test('opening Search results before any epoch is focused uses the same safe viewer empty state',async()=>{
 const {default:MatchingEpochs}=await server.ssrLoadModule('/src/components/MatchingEpochs.jsx');
 const html=render(MatchingEpochs,{predicate:{all:[]},splits:'date,cell',preview:{tree_revision:'fixture',catalog:{fields:[]}},viewFilters:{},onViewFilters:()=>{}});
 assert.match(html,/Choose an epoch/);
 assert.match(html,/Epoch list controls/);
 assert.doesNotMatch(html,/Include in analysis/);
});
test('shared viewer accepts no selected epoch and no source-specific extras',async()=>{
 const {default:EpochViewer}=await server.ssrLoadModule('/src/components/EpochViewer.jsx');
 const html=render(EpochViewer,{layout:{sizes:{columns:'minmax(0,1fr)',metadata:300},treeOpen:false,metadataOpen:false,onResize:()=>{}},epoch:null});
 assert.match(html,/Choose an epoch/);
 assert.doesNotMatch(html,/Include in analysis/);
});
test('common recorded scientific context preserves source facts and marks configured-only control history',async()=>{
 const {default:ScientificContext}=await server.ssrLoadModule('/src/components/ScientificContext.jsx');
 const html=render(ScientificContext,{epoch:{protocol_name:'example.VariableHistoryNoiseCurInject',cell_type:'On Parasol',source_filename:'fixture.h5',group_label:'[]',parameters:{isControl:1,history1:[0,675],history2:[0,50],target:[0,200]},metadata:{group:{properties:{externalSolutionAdditions:[]}}}}});
 assert.match(html,/Recording and condition context/);
 assert.match(html,/Control epoch · target only/);
 const text=html.replace(/<!--.*?-->/g,'').replace(/<[^>]*>/g,'');
 assert.match(text,/History 1 · configured only/);
 assert.match(html,/\[\] \(empty recorded field\)/);
 assert.match(text,/0 \/ 675/);
 assert.match(html,/fixture\.h5/);
});


test('shared designer puts its only Back to epochs control in the left tree pane',async()=>{
 const {default:EpochViewer}=await server.ssrLoadModule('/src/components/EpochViewer.jsx');
 const html=render(EpochViewer,{designMode:true,toolbar:{designMode:true,onBrowse:()=>{}},
  layout:{sizes:{columns:'320px 7px minmax(0,1fr)',tree:320,treeMax:560},treeOpen:true,metadataOpen:false,onResize:()=>{}},
  builder:{catalogData:{fields:[]},value:[],onChange:()=>{},preview:{count:0,levels:[]}},columnTree:{predicate:{all:[]},splits:''}});
 assert.equal((html.match(/Back to epochs/g)||[]).length,1);
 const leftPane=html.match(/<aside class="inspection-tree">([\s\S]*?)<\/aside>/)?.[1];
 assert.ok(leftPane);assert.match(leftPane,/Back to epochs/);
 assert.ok(leftPane.indexOf('Back to epochs')<leftPane.indexOf('Tree builder'));
});
