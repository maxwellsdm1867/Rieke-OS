'use strict';
// Trusted AppKit view. It receives only sanitized display frames on stdin; it
// has no filesystem paths, installer capability, process control, or app IPC.
module.exports=String.raw`
ObjC.import('AppKit');ObjC.import('Foundation');
const app=$.NSApplication.sharedApplication;app.setActivationPolicy(1);
const window=$.NSWindow.alloc.initWithContentRectStyleMaskBackingDefer($.NSMakeRect(0,0,430,150),3,2,false);
window.title='Updating Disco';window.releasedWhenClosed=false;
const label=$.NSTextField.labelWithString('Preparing the update…');label.frame=$.NSMakeRect(22,98,386,28);
const detail=$.NSTextField.labelWithString('Please leave Disco closed while the update finishes.');detail.frame=$.NSMakeRect(22,24,386,32);detail.font=$.NSFont.systemFontOfSize(11);detail.textColor=$.NSColor.secondaryLabelColor;
const bar=$.NSProgressIndicator.alloc.initWithFrame($.NSMakeRect(22,70,386,16));bar.style=0;bar.minValue=0;bar.maxValue=100;bar.indeterminate=true;bar.startAnimation(null);
window.contentView.addSubview(label);window.contentView.addSubview(bar);window.contentView.addSubview(detail);window.center;window.makeKeyAndOrderFront(null);app.activateIgnoringOtherApps(true);
const input=$.NSFileHandle.fileHandleWithStandardInput;
let buffer='',terminal=false,closeAt=Infinity,lastFrame=Date.now(),successMs=2000,failureMs=20000,staleMs=120000;
const started=Date.now();
function interrupted(){if(terminal)return;terminal=true;label.stringValue='Update progress is unavailable';detail.stringValue='Please wait for Disco to reopen.';bar.stopAnimation(null);bar.hidden=true;closeAt=Date.now()+failureMs;}
function frame(value){
 if(!value||value.format!=='disco-progress-view'||value.version!==1||typeof value.label!=='string'||value.label.length>160||typeof value.detail!=='string'||value.detail.length>160)return interrupted();
 if(!['Running','Installed','Restored','Deferred'].includes(value.state))return interrupted();
 lastFrame=Date.now();label.stringValue=value.label;detail.stringValue=value.detail;
 if(value.timing){successMs=Math.max(100,Math.min(5000,value.timing.successMs||2000));failureMs=Math.max(100,Math.min(30000,value.timing.failureMs||20000));staleMs=Math.max(1000,Math.min(300000,value.timing.staleMs||120000));}
 if(value.state==='Running'){
  if(value.progress===null){bar.indeterminate=true;bar.startAnimation(null);}
  else if(typeof value.progress==='number'&&isFinite(value.progress)&&value.progress>=0&&value.progress<=100){bar.stopAnimation(null);bar.indeterminate=false;bar.doubleValue=value.progress;}
  else return interrupted();
 }else{terminal=true;bar.stopAnimation(null);bar.hidden=true;closeAt=Date.now()+(value.state==='Deferred'?failureMs:successMs);}
}
ObjC.registerSubclass({name:'DiscoUpdateProgressInput',superclass:'NSObject',methods:{'dataAvailable:':{types:['void',['id']],implementation:function(){
 try{const data=input.availableData;if(Number(data.length)===0){interrupted();return;}
  buffer+=$.NSString.alloc.initWithDataEncoding(data,$.NSUTF8StringEncoding).js;if(buffer.length>16384){interrupted();return;}
  let end;while((end=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,end);buffer=buffer.slice(end+1);frame(JSON.parse(line));}
  input.waitForDataInBackgroundAndNotify;
 }catch(error){interrupted();}
}}}});
const reader=$.DiscoUpdateProgressInput.alloc.init;
$.NSNotificationCenter.defaultCenter.addObserverSelectorNameObject(reader,'dataAvailable:',$.NSFileHandleDataAvailableNotification,input);input.waitForDataInBackgroundAndNotify;
while(window.isVisible&&Date.now()<closeAt&&Date.now()-started<20*60*1000){
 if(!terminal&&Date.now()-lastFrame>staleMs)interrupted();
 const event=app.nextEventMatchingMaskUntilDateInModeDequeue($.NSEventMaskAny,$.NSDate.dateWithTimeIntervalSinceNow(0.1),$.NSDefaultRunLoopMode,true);
 if(event&&!event.isNil())app.sendEvent(event);app.updateWindows;
}
$.NSNotificationCenter.defaultCenter.removeObserver(reader);window.orderOut(null);
`;
