'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {isOwnedURL, validateSender, validateDraft, approvedReleaseURL} = require('../security.cjs');
test('only exact authenticated loopback origins and explicit recovery document are trusted', () => {
  const origins = new Set(['http://127.0.0.1:1234']);
  assert.equal(isOwnedURL('http://127.0.0.1:1234/api/project', origins), true);
  for (const url of ['http://localhost:1234/', 'http://127.0.0.1:1235/', 'https://127.0.0.1:1234/', 'javascript:alert(1)', 'file:///tmp/foreign.html']) assert.equal(isOwnedURL(url, origins), false);
  assert.equal(isOwnedURL('file:///tmp/recovery.html', origins, ['/tmp/recovery.html']), true);
});
test('privileged IPC rejects foreign renderer, subframe and origin', () => {
  const mainFrame = {url: 'http://127.0.0.1:1234/'}; const contents = {mainFrame};
  const window = {isDestroyed: () => false, webContents: contents};
  assert.equal(validateSender({sender: contents, senderFrame: mainFrame}, new Set([window]), 'http://127.0.0.1:1234'), window);
  assert.throws(() => validateSender({sender: {}, senderFrame: mainFrame}, [window], 'http://127.0.0.1:1234'));
  assert.throws(() => validateSender({sender: contents, senderFrame: {...mainFrame}}, [window], 'http://127.0.0.1:1234'));
  mainFrame.url = 'https://evil.example/';
  assert.throws(() => validateSender({sender: contents, senderFrame: mainFrame}, [window], 'http://127.0.0.1:1234'));
});
test('drafts reject path traversal, unknown fields, missing JSON and oversize', () => {
  assert.equal(validateDraft({projectId: 'launcher', value: {route: 'project'}}).projectId, 'launcher');
  for (const payload of [{projectId: '../../evil', value: {}}, {projectId: 'launcher', value: {}, path: '/tmp'}, {projectId: 'launcher', value: undefined}, {projectId: 'launcher', value: 'x'.repeat(2 * 1024 * 1024)}]) assert.throws(() => validateDraft(payload));
});
test('external URLs are restricted to canonical HTTPS release notes', () => {
  assert.equal(approvedReleaseURL('https://github.com/maxwellsdm1867/disco/releases/tag/v0.1.0'), true);
  for (const url of ['http://github.com/maxwellsdm1867/disco/releases', 'https://github.com.evil.example/maxwellsdm1867/disco/releases', 'https://github.com/user/other/releases', 'https://user:pass@github.com/maxwellsdm1867/disco/releases']) assert.equal(approvedReleaseURL(url), false);
});

test('sanitized clipboard writes require a focused owned scientific main frame and exact requesting origin',()=>{
 const {allowClipboardWrite}=require('../security.cjs');
 const origin='http://127.0.0.1:1234',other='http://127.0.0.1:1235';
 const contents={isDestroyed:()=>false,isFocused:()=>true,getURL:()=>origin+'/workspace',mainFrame:{url:origin+'/workspace'}};
 const window={isDestroyed:()=>false,webContents:contents},windows=new Set([window]),origins=new Set([origin,other]);
 const details={isMainFrame:true,requestingUrl:origin+'/workspace'};
 const allowed=(c=contents,p='clipboard-sanitized-write',d=details,w=windows,o=origin)=>allowClipboardWrite(c,p,d,w,origins,o);
 assert.equal(allowed(),true);
 assert.equal(allowClipboardWrite(contents,'clipboard-sanitized-write',details,windows,origins),true);
 for(const permission of ['clipboard-read','deprecated-sync-clipboard-read','media','geolocation','notifications','unknown'])assert.equal(allowed(contents,permission),false);
 for(const d of [undefined,{}, {...details,isMainFrame:false},{...details,requestingUrl:other+'/workspace'},{...details,requestingUrl:'file:///recovery.html'},{...details,requestingUrl:'http://evil.example/'}])assert.equal(allowClipboardWrite(contents,'clipboard-sanitized-write',d,windows,origins,origin),false);
 assert.equal(allowed(null),false);assert.equal(allowed(contents,'clipboard-sanitized-write',details,new Set()),false);
 assert.equal(allowed(contents,'clipboard-sanitized-write',details,windows,other),false);
 contents.isFocused=()=>false;assert.equal(allowed(),false);contents.isFocused=()=>true;
 contents.isDestroyed=()=>true;assert.equal(allowed(),false);contents.isDestroyed=()=>false;
 contents.mainFrame.url=other+'/workspace';assert.equal(allowed(),false);
 contents.mainFrame.url='file:///recovery.html';assert.equal(allowed(),false);
});
