import test from 'node:test';
import assert from 'node:assert/strict';
import {createGlobalSearchHarness} from './test-support/globalSearchHarness.js';

test('checkpoint GlobalSearch rereads the same bounded query on reopen',async()=>{
  const h=await createGlobalSearchHarness({baseline:true});
  try{
    await h.render({revision:0});
    const open=()=>h.root.findByProps({'aria-label':'Search project metadata and UUIDs'}).props.onClick();
    const close=()=>h.root.findByProps({'aria-label':'Close search'}).props.onClick();
    await h.act(open);
    await h.act(()=>h.root.findByProps({'aria-label':'Search UUID, field, or typed value'}).props.onChange({target:{value:'CellA'}}));
    await h.waitFor(()=>h.fixture.requests.length===1&&h.root.findAllByProps({className:'global-search-result'}).length===1);
    await h.act(close);await h.act(open);
    await h.waitFor(()=>h.fixture.requests.length===2&&h.root.findAllByProps({className:'global-search-result'}).length===1);
    assert.deepEqual(h.fixture.requests.map(row=>row.url),['/api/search?q=CellA&limit=20','/api/search?q=CellA&limit=20']);
    assert.ok(h.fixture.requests.every(row=>row.method==='GET'));
  }finally{await h.close();}
});
