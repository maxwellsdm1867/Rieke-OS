import test from 'node:test';
import assert from 'node:assert/strict';
import {absoluteFolderPath,browseFolder,newFolderPath,readFolderListing,shouldCreateNewFolder} from './folderBrowser.js';

test('native existing selection returns its exact absolute folder and never invokes browser fallback',async()=>{
  let chosen=0;
  const result=await browseFolder({purpose:'existing',nativeBridge:{chooseProjectFolder:async()=>{chosen++;return '/Users/scientist/Study folder';}},chooseDialog:()=>assert.fail('Native choice must not start browser fallback')});
  assert.equal(result,'/Users/scientist/Study folder');assert.equal(chosen,1);
});

test('native cancel stays cancelled for existing, new and create without a second chooser',async()=>{
  for(const purpose of ['existing','new','create'])assert.equal(await browseFolder({purpose,nativeBridge:{chooseProjectFolder:async()=>null},chooseDialog:()=>assert.fail('Cancellation must not open another chooser')}),null);
});

test('browser fallback selects folders through an injected dialog without filesystem writes',async()=>{
  let options;
  const result=await browseFolder({directory:'/Volumes/Research',purpose:'existing',title:'Add a project',nativeBridge:null,chooseDialog:async value=>{options=value;return '/Volumes/Research/Received';}});
  assert.equal(result,'/Volumes/Research/Received');
  assert.equal(options.initialDirectory,'/Volumes/Research');
  assert.equal(options.purpose,'existing');
  assert.equal(options.title,'Add a project');
  assert.equal(await browseFolder({nativeBridge:null,chooseDialog:async()=>null}),null);
});

test('new native choice is a parent followed by an explicit child name, never the existing parent itself',async()=>{
  let options;
  const result=await browseFolder({purpose:'new',directory:'/old/location/Received study',nativeBridge:{chooseProjectFolder:async()=>'/selected/parent'},chooseDialog:async value=>{options=value;return {directory:value.initialDirectory,name:value.initialName};}});
  assert.equal(options.initialDirectory,'/selected/parent');
  assert.equal(options.initialName,'Received study');
  assert.equal(result,'/selected/parent/Received study');
  await assert.rejects(browseFolder({purpose:'new',nativeBridge:null,chooseDialog:async()=>'/existing/parent'}),/parent folder and name/);
});

test('browser new destination seeds its parent and supports naming without any path paste',async()=>{
  let options;
  const result=await browseFolder({purpose:'new',directory:'/research/My study',nativeBridge:null,chooseDialog:async value=>{options=value;return {directory:'/Volumes/Other drive',name:'Restored study'};}});
  assert.equal(options.initialDirectory,'/research');assert.equal(options.initialName,'My study');
  assert.equal(result,'/Volumes/Other drive/Restored study');
  await browseFolder({purpose:'new',suggestedName:'Shared study',nativeBridge:null,chooseDialog:async value=>{assert.equal(value.initialName,'Shared study');assert.equal(value.initialDirectory,'');return null;}});
});

test('create can use a native-selected empty root exactly or propose a child from a parent',async()=>{
  let options;
  const empty=await browseFolder({purpose:'create',suggestedName:'Study',nativeBridge:{chooseProjectFolder:async()=>'/research/Empty root'},chooseDialog:async value=>{options=value;return value.initialDirectory;}});
  assert.equal(options.initialDirectory,'/research/Empty root');
  assert.equal(empty,'/research/Empty root');
  const child=await browseFolder({purpose:'create',nativeBridge:null,suggestedName:'Study',chooseDialog:async()=>({directory:'/research',name:'Study'})});
  assert.equal(child,'/research/Study');
});

test('create preserves a missing proposed child when its nearest existing parent is empty',async()=>{
  const existingEmpty={directory:'/research/Empty root',empty:true,requested_exists:true};
  const missingChild={directory:'/research/Empty root',empty:true,requested_exists:false};
  assert.equal(shouldCreateNewFolder(existingEmpty),false);
  assert.equal(shouldCreateNewFolder(missingChild),true);
  assert.equal(shouldCreateNewFolder({empty:false,requested_exists:true}),true);
  const selected=await browseFolder({purpose:'create',directory:'/research/Empty root/NewStudy',nativeBridge:null,chooseDialog:async options=>shouldCreateNewFolder(missingChild)?{directory:missingChild.directory,name:options.initialName}:missingChild.directory});
  assert.equal(selected,'/research/Empty root/NewStudy');
});

test('an unfinished typed path does not block native or browser folder selection',async()=>{
  for(const directory of ['Study','~/Study','/folder\0unfinished']){
    assert.equal(await browseFolder({directory,nativeBridge:{chooseProjectFolder:async()=>'/research/Chosen'},chooseDialog:()=>assert.fail('Native choice must not open fallback')}),'/research/Chosen');
    assert.equal(await browseFolder({directory,purpose:'create',suggestedName:'Study',nativeBridge:null,chooseDialog:async options=>{assert.equal(options.initialDirectory,'');assert.equal(options.initialName,'Study');return {directory:'/research',name:options.initialName};}}),'/research/Study');
  }
  await assert.rejects(browseFolder({directory:'unfinished',nativeBridge:null,chooseDialog:async()=> 'relative selection'}),/absolute folder/);
});

test('invalid folder paths and child names fail before callers can mutate the filesystem',async()=>{
  for(const path of ['relative','~/Study','/folder\0secret',42])assert.throws(()=>absoluteFolderPath(path),/absolute folder/);
  for(const name of ['', '.', '..', '../outside','a/b','a\\b','bad\0name'])assert.throws(()=>newFolderPath('/parent',name),/folder name/);
  assert.equal(newFolderPath('/','Study'),'/Study');
  await assert.rejects(browseFolder({nativeBridge:{chooseProjectFolder:async()=> 'relative'},chooseDialog:()=>assert.fail()}),/absolute folder/);
  await assert.rejects(browseFolder({nativeBridge:{chooseProjectFolder:async()=>{throw Error('Chooser unavailable');}}}),/could not open: Chooser unavailable/);
});

test('folder listing uses only a paged GET path, preserves shortcuts and checks pagination metadata',async()=>{
  const reply={directory:'/research/Studies',parent:'/research',folders:[{name:'Study A',path:'/research/Studies/Study A'}],locations:[{name:'Home',path:'/Users/scientist'}],offset:200,limit:200,total:402,has_more:true,next_offset:400,empty:false,truncated:true};
  const paths=[];
  const result=await readFolderListing({directory:'/research/Studies',offset:200,request:async path=>{paths.push(path);return reply;}});
  const query=new URL(paths[0],'http://localhost/api');
  assert.equal(query.pathname,'/folders');assert.equal(query.searchParams.get('directory'),'/research/Studies');assert.equal(query.searchParams.get('offset'),'200');assert.equal(query.searchParams.get('limit'),'200');
  assert.equal(result,reply);assert.equal(result.truncated,true);
  await assert.rejects(readFolderListing({request:async()=>({...reply,next_offset:200})}),/next folder page/);
  await assert.rejects(readFolderListing({request:async()=>({...reply,empty:'yes'})}),/empty-folder/);
  await assert.rejects(readFolderListing({request:async()=>({...reply,requested_exists:'yes'})}),/requested-folder/);
});
