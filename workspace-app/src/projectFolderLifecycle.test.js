import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';
async function fixture({activate,confirm,closeStatus=200}={}){
 const dom=new JSDOM('<main></main>',{url:'http://127.0.0.1:41001/'}),events=[];
 const previous=Object.fromEntries(['window','document','localStorage','fetch'].map(key=>[key,globalThis[key]]));
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage});
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};dom.window.HTMLDialogElement.prototype.close=function(){this.open=false;};
 const identity={projectUuid:'project',path:'/owned/current'};
 window.riekeDesktop={async activateProject(url){events.push(['activate',url]);await activate?.();return {activated:true};},async prepareProjectClose(value){assert.deepEqual(value,identity);events.push(['prepare']);},async confirmProjectClosed(value){assert.deepEqual(value,identity);events.push(['confirm']);await confirm?.();return {closed:true};},async cancelProjectClose(){events.push(['cancel']);}};
 globalThis.fetch=async(url)=>{events.push([url]);const data=url==='/api/projects/inspect-folder'?{valid:true,kind:'project'}:url==='/api/projects/open-folder'?{url:'http://127.0.0.1:41002/'}:url==='/api/project/close'?closeStatus===200?{state:'closed',launcher_url:'http://127.0.0.1:41000/'}:{error:'Project busy'}:{};return new Response(JSON.stringify(data),{status:url==='/api/project/close'?closeStatus:200});};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const lifecycle=await server.ssrLoadModule('/src/desktopLifecycle.js');let releaseFence;
 const prepare=window.riekeDesktop.prepareProjectClose,cancel=window.riekeDesktop.cancelProjectClose;
 window.riekeDesktop.prepareProjectClose=async value=>{await prepare(value);releaseFence=lifecycle.beginProjectUnmount();};
 window.riekeDesktop.cancelProjectClose=async value=>{await cancel(value);releaseFence?.();};
 const {default:ProjectFolder}=await server.ssrLoadModule('/src/project-workspace/ui/ProjectFolder.jsx');const root=createRoot(document.querySelector('main'));let closed=0;
 await act(async()=>root.render(React.createElement(ProjectFolder,{project:{uuid:'project',path:'/owned/current',name:'Current',database_kind:'native-mysql'},initialDirectory:'/owned/other',onClose:()=>{closed++;}})));
 const button=label=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===label);
 return {events,button,get closed(){return closed;},async click(label){await act(async()=>{button(label).click();await new Promise(r=>setTimeout(r,10));});},async close(){releaseFence?.();await act(()=>root.unmount());await server.close();dom.window.close();for(const [key,value] of Object.entries(previous)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}};
}
test('folder opening completes the originating retained dialog only after native activation',async()=>{
 let release;const held=new Promise(r=>release=r);const h=await fixture({activate:()=>held});try{
 await h.click('Open project');assert.equal(h.closed,0);assert.equal(h.button('Open project').disabled,true);assert.deepEqual(h.events.at(-1),['activate','http://127.0.0.1:41002/']);
 await act(async()=>{release();await held;});assert.equal(h.closed,1);assert.equal(h.button('Open project').disabled,false);
 }finally{release();await h.close();}
});
test('refused native activation leaves folder dialog usable and surfaces the error',async()=>{
 const h=await fixture({activate:()=>{throw Error('Activation refused');}});try{await h.click('Open project');assert.equal(h.closed,0);assert.equal(h.button('Open project').disabled,false);assert.match(document.body.textContent,/Activation refused/);}finally{await h.close();}
});
test('native Close project prepares and confirms exact child exit before completing',async()=>{
 let release;const held=new Promise(r=>release=r);const h=await fixture({confirm:()=>held});try{
 await h.click('Close project');assert.deepEqual(h.events,[['prepare'],['/api/project/close'],['confirm']]);assert.equal(h.closed,0);
 await act(async()=>{release();await held;});assert.equal(h.closed,1);
 }finally{release();await h.close();}
});
test('a refused close cancels preparation but an uncertain exit stays fenced',async()=>{
 const refused=await fixture({closeStatus:409});try{await refused.click('Close project');assert.deepEqual(refused.events,[['prepare'],['/api/project/close'],['cancel']]);assert.equal(refused.closed,0);}finally{await refused.close();}
 const uncertain=await fixture({confirm:()=>{throw Error('Closure unconfirmed');}});try{await uncertain.click('Close project');assert.equal(uncertain.events.some(e=>e[0]==='cancel'),false);assert.equal(uncertain.closed,0);assert.match(document.body.textContent,/Closure unconfirmed/);}finally{await uncertain.close();}
});
