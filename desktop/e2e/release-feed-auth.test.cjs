'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {takeReleaseFeedToken,installReleaseFeedAuth,restoreReleaseFeedAuth}=require('./release-feed-auth.cjs');
test('credential is removed before child environment inheritance',()=>{
  const environment={GH_TOKEN:'test-only-token',HOME:'/owned'};
  assert.equal(takeReleaseFeedToken(environment),'test-only-token');
  assert.deepEqual({...environment},{HOME:'/owned'});
});
test('only exact release API receives auth; redirect and other requests retain original behavior',()=>{
  const calls=[],response={real_response:true},https={get(...args){calls.push(args);return response;}};
  const original=https.get,callback=()=>{};
  const endpoint='https://api.github.com/repos/maxwellsdm1867/Rieke-OS/releases?per_page=100&page=1';
  installReleaseFeedAuth({https},{token:'test-only-token'});
  const options={headers:{Accept:'application/vnd.github+json'}};
  assert.equal(https.get(endpoint,options,callback),response);
  assert.deepEqual(calls[0],[endpoint,{headers:{Accept:'application/vnd.github+json',Authorization:'Bearer test-only-token'}},callback]);
  assert.deepEqual(options,{headers:{Accept:'application/vnd.github+json'}});
  for(const url of ['https://objects.githubusercontent.com/release','https://api.github.com/repos/other/repo/releases',endpoint+'&extra=1','http://api.github.com/repos/maxwellsdm1867/Rieke-OS/releases?per_page=100&page=1']){
    https.get(url,options,callback);assert.deepEqual(calls.at(-1),[url,options,callback]);
  }
  assert.deepEqual(restoreReleaseFeedAuth({https}),{authenticated_requests:1,scope:endpoint});
  assert.equal(https.get,original);
  https.get(endpoint,options,callback);assert.deepEqual(calls.at(-1),[endpoint,options,callback]);
});
