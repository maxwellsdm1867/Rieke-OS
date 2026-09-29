import test from 'node:test';
import assert from 'node:assert/strict';
import {explorerFocusState} from './explorerScope.js';
test('compact explorer scopes require an exact focused UUID and explicit membership result',()=>{
  const summary={focused_uuid:'previous',focused_in_scope:true};
  assert.equal(explorerFocusState(summary,'next'),'pending');
  assert.equal(explorerFocusState(summary,'previous',{loading:true}),'pending');
  assert.equal(explorerFocusState(summary,'previous'),'included');
  assert.equal(explorerFocusState({...summary,focused_in_scope:false},'previous'),'excluded');
  assert.equal(explorerFocusState({...summary,focused_in_scope:'true'},'previous'),'invalid');
  assert.equal(explorerFocusState(summary,'previous',{error:'Source changed'}),'error');
  assert.equal(explorerFocusState(summary,null),'none');
});
