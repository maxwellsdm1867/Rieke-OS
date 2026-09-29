import test from 'node:test';
import assert from 'node:assert/strict';
import {uploadRecording} from './uploadRecording.js';

test('upload completion reports transfer completion, not import acceptance or parsing',async()=>{
  const oldXHR=globalThis.XMLHttpRequest,oldForm=globalThis.FormData;
  let xhr;globalThis.FormData=class {append(){}};
  globalThis.XMLHttpRequest=class {constructor(){xhr=this;this.upload={};}open(method,url){this.method=method;this.url=url;}setRequestHeader(){}send(){}};
  try{
    const updates=[];const promise=uploadRecording({name:'fixture.h5'},value=>updates.push(value));
    xhr.upload.onprogress({loaded:512,total:1024,lengthComputable:true});xhr.upload.onload();
    assert.deepEqual(updates,[{phase:'uploading',loaded:512,total:1024},{phase:'awaiting_job'}]);
    xhr.status=202;xhr.responseText=JSON.stringify({job_uuid:'job',status:'queued'});xhr.onload();
    assert.deepEqual(await promise,{job_uuid:'job',status:'queued'});
    assert.equal(xhr.method,'POST');assert.equal(xhr.url,'/api/imports');
  }finally{globalThis.XMLHttpRequest=oldXHR;globalThis.FormData=oldForm;}
});
test('upload connection errors are ambiguous and never retry the mutation automatically',async()=>{
  const oldXHR=globalThis.XMLHttpRequest,oldForm=globalThis.FormData;
  let xhr,sends=0;globalThis.FormData=class {append(){}};
  globalThis.XMLHttpRequest=class {constructor(){xhr=this;this.upload={};}open(){}setRequestHeader(){}send(){sends++;}};
  try{
    const promise=uploadRecording({},()=>{});xhr.onerror();
    await assert.rejects(promise,/may have received it/);assert.equal(sends,1);
  }finally{globalThis.XMLHttpRequest=oldXHR;globalThis.FormData=oldForm;}
});
test('server failures preserve ambiguous acceptance and inactive transfers have a bounded stop',async()=>{
  const oldXHR=globalThis.XMLHttpRequest,oldForm=globalThis.FormData;
  let xhr;globalThis.FormData=class {append(){}};
  globalThis.XMLHttpRequest=class {constructor(){xhr=this;this.upload={};}open(){}setRequestHeader(){}send(){}abort(){this.onabort();}};
  try{
    let promise=uploadRecording({},()=>{});
    xhr.status=503;xhr.responseText=JSON.stringify({error:'Server unavailable'});xhr.onload();
    await assert.rejects(promise,error=>error.requestRejected===false&&/acceptance is unconfirmed/.test(error.message));
    promise=uploadRecording({},()=>{},{inactivityMs:10});
    await assert.rejects(promise,/No upload or response progress/);
    promise=uploadRecording({},()=>{});
    xhr.status=413;xhr.responseText=JSON.stringify({error:'File too large'});xhr.onload();
    await assert.rejects(promise,error=>error.requestRejected===true);
  }finally{globalThis.XMLHttpRequest=oldXHR;globalThis.FormData=oldForm;}
});
