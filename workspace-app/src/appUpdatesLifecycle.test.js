import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

const testing = {state:'Current',installed:'0.1.3',channel:'unsigned-testing',manual_updates:true};
function text(node){if(typeof node==='string')return node;if(!node)return '';return (Array.isArray(node)?node:node.children||[]).map(text).join('');}
async function harness(initial=testing,{source=false}={}){
  const old={window:globalThis.window,document:globalThis.document,fetch:globalThis.fetch};
  const fixture={status:initial,downloads:0,restarts:0,checks:0,requests:[]};let listener;
  const bridge={status:async()=>fixture.status,onStatus:fn=>{listener=fn;return()=>{listener=null;};},
    checkForUpdates:async()=>{fixture.checks++;return fixture.checkResult||fixture.status;},
    downloadUpdate:async()=>{fixture.downloads++;if(fixture.downloadError)throw Error(fixture.downloadError);return fixture.downloadResult||fixture.status;},
    restartToUpdate:async()=>{fixture.restarts++;return fixture.restartResult||{ready:false,reason:'An import is still active.'};},openReleaseNotes:async()=>{}};
  globalThis.window=source?{}:{riekeDesktop:bridge};globalThis.document={body:{nodeType:1},visibilityState:'visible',addEventListener(){},removeEventListener(){}};
  if(source)globalThis.fetch=async(url,options)=>{
    fixture.requests.push({url,method:options.method,headers:options.headers});let value;
    if(url==='/api/app/updates/check'){fixture.checks++;value=fixture.status;}
    else if(url==='/api/app/updates/stage'){fixture.downloads++;value={state:'complete',result:{version:'1.2.0'}};}
    else throw Error('Unexpected source update endpoint');
    return {ok:true,json:async()=>value};
  };
  const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,
    server:{middlewareMode:true,hmr:false,ws:false},ssr:{noExternal:['react-dom']},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},
    plugins:[{name:'update-dialog-browser-boundary',enforce:'pre',resolveId:id=>id==='react-dom'?'\0update-portal':undefined,
      load:id=>id==='\0update-portal'?'export const createPortal=children=>children;':undefined}]});
  const {default:AppUpdates}=await server.ssrLoadModule('/src/components/AppUpdates.jsx');let renderer;
  await act(async()=>{renderer=TestRenderer.create(React.createElement(AppUpdates),{createNodeMock:node=>node.type==='dialog'?{showModal(){},close(){}}:null});});
  const h={fixture,get text(){return text(renderer.toJSON());},get buttons(){return renderer.root.findAllByType('button');},
    async click(name){const button=h.buttons.find(node=>text(node).trim()===name||node.props['aria-label']===name);assert.ok(button,`Button missing: ${name}`);await act(async()=>button.props.onClick());},
    async open(){await act(async()=>h.buttons.find(node=>node.props['aria-haspopup']==='dialog').props.onClick());},
    async emit(status){fixture.status=status;await act(async()=>listener(status));},
    async close(){try{await act(async()=>renderer.unmount());}finally{await server.close();for(const [key,value]of Object.entries(old)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}}};
  return h;
}
test('unsigned testing explains background checks and explicit downloads without promising automatic installation',async()=>{
  const h=await harness();try{await h.open();assert.match(h.text,/Unsigned testing/);assert.match(h.text,/checked automatically/);
    assert.match(h.text,/choose when to download/i);assert.doesNotMatch(h.text,/download quietly|download automatically/);
    assert.equal(h.fixture.downloads,0);assert.equal(h.fixture.restarts,0);
  }finally{await h.close();}
});
test('a background release notification shows its version without downloading or restarting',async()=>{
  const h=await harness();try{
    await h.emit({...testing,state:'Available',available:'0.1.4',can_download:true});
    assert.match(h.text,/0\.1\.4/);assert.equal(h.fixture.downloads,0);assert.equal(h.fixture.restarts,0);
  }finally{await h.close();}
});
test('checking offers a download and only an explicit download prepares the desktop update',async()=>{
  const h=await harness();try{
    h.fixture.checkResult={...testing,state:'Available',available:'0.1.4',can_download:true};
    h.fixture.downloadResult={...testing,state:'Ready',available:'0.1.4',can_download:false};
    await h.open();await h.click('Check for updates');assert.equal(h.fixture.downloads,0);
    await h.click('Download update');assert.equal(h.fixture.downloads,1);assert.equal(h.fixture.restarts,0);
    assert.match(h.text,/Update ready/);
  }finally{await h.close();}
});
test('restart is explicit and an active import keeps the prepared update and dialog usable',async()=>{
  const h=await harness({...testing,state:'Ready',available:'0.1.4',can_download:false});try{
    await h.open();assert.equal(h.fixture.restarts,0);
    await h.click('Restart to update');assert.equal(h.fixture.restarts,1);
    assert.match(h.text,/An import is still active/);assert.match(h.text,/Update ready/);
    assert.equal(h.buttons.find(node=>text(node).trim()==='Restart to update').props.disabled,false);
    await h.click('Close updates');assert.doesNotMatch(h.text,/An import is still active/);
  }finally{await h.close();}
});
test('successful restart handoff disables further update actions while the app installs',async()=>{
  const h=await harness({...testing,state:'Ready',available:'0.1.4',can_download:false});try{
    h.fixture.restartResult={ready:true,installing:true};await h.open();await h.click('Restart to update');
    assert.match(h.text,/Restarting to update/);assert.equal(h.buttons.find(node=>text(node).trim()==='Check for updates').props.disabled,true);
    assert.equal(h.buttons.some(node=>text(node).trim()==='Restart to update'),false);
  }finally{await h.close();}
});
test('source installation preserves its authorized HTTP staging flow and next-launch instructions',async()=>{
  const h=await harness({state:'update_available',installed:'1.1.0',available:'1.2.0',can_stage:true,update_token:'source-update-token'},{source:true});
  try{await h.open();assert.doesNotMatch(h.text,/Unsigned testing/);await h.click('Download update');
    assert.match(h.text,/next launch will use this version/);assert.equal(h.fixture.restarts,0);
    assert.equal(h.buttons.some(node=>text(node).trim()==='Restart to update'),false);
    const request=h.fixture.requests.find(request=>request.url==='/api/app/updates/stage');
    assert.equal(request.method,'POST');assert.equal(request.headers['X-Rieke-Update-Token'],'source-update-token');
  }finally{await h.close();}
});
test('a failed desktop download reports the failure and never enables restart',async()=>{
  const h=await harness({...testing,state:'Available',available:'0.1.4',can_download:true});try{
    h.fixture.downloadError='The downloaded app failed checksum verification.';await h.open();await h.click('Download update');
    assert.match(h.text,/failed checksum verification/);assert.equal(h.fixture.restarts,0);
    assert.equal(h.buttons.some(node=>text(node).trim()==='Restart to update'),false);
    await h.click('Close updates');assert.match(h.text,/0\.1\.4/);
  }finally{await h.close();}
});
test('prepared testing update notice explains explicit restart rather than ordinary next launch',async()=>{
 const h=await harness({...testing,state:'Ready',available:'0.1.4'});try{
   const notice=h.buttons.find(node=>node.props['aria-haspopup']==='dialog');
   assert.match(notice.props.title,/choose Restart to update/);assert.doesNotMatch(notice.props.title,/next launch/);
 }finally{await h.close();}
});
