'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function page(initial){
 const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,{hidden:false,disabled:false,textContent:''});return elements.get(id);};let listener,installs=0;
 const bridge={status:async()=>initial,onStatus:fn=>{listener=fn;},installAndOpen:async()=>{installs++;return {ready:false,reason:'Another installed app is still running.'};},retryStartup:async()=>{},restorePreviousVersion:async()=>{},quit:async()=>{}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../recovery.js'),'utf8'),{window:{riekeDesktop:bridge},document:{getElementById:element}});
 return {element,get installs(){return installs;},emit:status=>listener(status),settle:()=>new Promise(resolve=>setImmediate(resolve)),click:async id=>element(id).onclick({target:element(id)})};
}
test('unsigned bootstrap explains Open Anyway only before installation and requires an explicit Install and Open',async()=>{
 const h=page({state:'Bootstrap',channel:'unsigned-testing',title:'Install Rieke OS',message:'Install this complete app in your Applications folder and open it.'});await h.settle();
 assert.equal(h.element('channel').hidden,false);assert.match(h.element('channel').textContent,/Unsigned testing/);
 assert.equal(h.element('gatekeeper').hidden,false);assert.match(h.element('gatekeeper').textContent,/Open Anyway/);
 assert.equal(h.installs,0);await h.click('install');assert.equal(h.installs,1);assert.match(h.element('detail').textContent,/still running/);
 h.emit({state:'Recovery',channel:'unsigned-testing'});assert.equal(h.element('install').hidden,true);assert.equal(h.element('gatekeeper').hidden,true);
});
test('signed bootstrap retains its signature guidance and never claims an unsigned exception',async()=>{
 const h=page({state:'Bootstrap',channel:'signed',detail:'Developer ID signature verification is required.'});await h.settle();
 assert.equal(h.element('channel').hidden,true);assert.equal(h.element('gatekeeper').hidden,true);
 assert.equal(h.element('detail').textContent,'Developer ID signature verification is required.');assert.equal(h.installs,0);
});
