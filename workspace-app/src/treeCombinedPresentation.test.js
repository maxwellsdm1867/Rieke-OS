import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createElement} from 'react';
import {renderToString} from 'react-dom/server';
import {createServer} from './test-support/isolatedVite.js';
import react from '@vitejs/plugin-react';
let server;
before(async()=>{server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,plugins:[react()],server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});});
after(async()=>{await server?.close();});
async function render(path,props){const {default:Component}=await server.ssrLoadModule(path);return renderToString(createElement(Component,props));}
test('saved combined fields stay readable without claiming missing registry definitions',async()=>{
 const id='joint/parameters%2Fhistory1+parameters%2Fhistory2+parameters%2Ftarget';
 const html=await render('/src/typed-query/ui/TreeBuilder.jsx',{value:[id],onChange(){},catalogData:{fields:[]},preview:{levels:[{field:id}]},loading:false});
 assert.match(html,/Combined settings/);
 assert.match(html,/>history1<|>history 1</);
 assert.match(html,/>history2<|>history 2</);
 assert.match(html,/>target</);
 assert.match(html,/Saved fields unavailable/);
 assert.match(html,/Separate history1 \+ history2 \+ target grouping/);
 assert.doesNotMatch(html,/<strong[^>]*>joint\//);
});
