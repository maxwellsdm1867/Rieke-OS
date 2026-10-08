'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../main.cjs'),'utf8');
function fixture(){
  const handlers={},contents={},window={webContents:contents},origin='http://127.0.0.1:1234';
  const ownedSession={setPermissionRequestHandler(){},setPermissionCheckHandler(){},webRequest:{onBeforeRequest(){},onBeforeSendHeaders(){},onHeadersReceived(){}},on(name,callback){handlers[name]=callback;}};
  const context={session:{fromPartition:()=>ownedSession},windows:new Set([window]),supervisor:{origins:new Set([origin])},isOwnedURL:url=>new URL(url).origin===origin,path,app:{getPath:name=>{assert.equal(name,'downloads');return '/Users/Example User/Downloads';}}};
  vm.runInNewContext(source.slice(source.indexOf('function configureSession()'),source.indexOf('function restoreStartupWindow('))+'\nconfigureSession();',context);
  return {download:handlers['will-download'],contents};
}
test('owned export opens a browsable save dialog with an absolute Downloads destination',()=>{
 const f=fixture();let options;
 f.download({preventDefault(){assert.fail('owned export refused');}},{getURL:()=> 'http://127.0.0.1:1234/api/exports/id/download',getFilename:()=> '../../recordings.sqlite',setSaveDialogOptions:value=>{options=value;}},f.contents);
 assert.equal(options.title,'Save export');assert.equal(options.defaultPath,'/Users/Example User/Downloads/recordings.sqlite');
});
test('unowned contents and external downloads remain refused',()=>{
 const f=fixture();let refused=0;
 for(const [contents,url] of [[{},'http://127.0.0.1:1234/api/exports/id/download'],[f.contents,'https://example.com/file']]){
  f.download({preventDefault(){refused++;}},{getURL:()=>url,setSaveDialogOptions(){assert.fail('unexpected dialog');}},contents);
 }
 assert.equal(refused,2);
});
