const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validateReceipt}=require('./render_receipts.cjs');
const valid=()=>({input:{type:'pointerdown',trusted:true},truth_checked:true,
 source_hash:'sealed-ui',generation_before:'one',generation_after:'one',
 allowed_generation_dimensions:[],event_to_stable_ms:20,cap_ms:45000});
test('read receipt requires unchanged source authority generation',()=>{
 assert.equal(validateReceipt(valid()).event_to_stable_ms,20);
 assert.throws(()=>validateReceipt({...valid(),generation_after:'two'}),/Generation changed/);
});
test('tagging explicitly records allowed generation transition',()=>{
 const generation_before={metadata:'one',source:'one',annotation:'one',typed:'one',publication:'one',binding:null};
 const generation_after={...generation_before,annotation:'two'};
 assert.equal(validateReceipt({...valid(),generation_before,generation_after,allowed_generation_dimensions:['annotation']}).generation_after.annotation,'two');
 assert.throws(()=>validateReceipt({...valid(),generation_before,generation_after:{...generation_after,source:'two'},allowed_generation_dimensions:['annotation']}),/Scientific source generation/);
 assert.throws(()=>validateReceipt({...valid(),generation_before,generation_after,allowed_generation_dimensions:['metadata']}),/cannot be waived/);
});
test('complete structured generation tokens compare by value, retaining every dimension',()=>{
 const generation_before={metadata:'one',source:'two',annotation:'three',publication:1};
 const generation_after={publication:1,annotation:'three',source:'two',metadata:'one'};
 assert.doesNotThrow(()=>validateReceipt({...valid(),generation_before,generation_after}));
 for(const key of Object.keys(generation_before))
  assert.throws(()=>validateReceipt({...valid(),generation_before,generation_after:{...generation_after,[key]:'changed'}}),/Generation changed/);
});
test('untrusted input and incomplete truth cannot qualify',()=>{
 assert.throws(()=>validateReceipt({...valid(),input:{trusted:false}}),/trusted UI/);
 assert.throws(()=>validateReceipt({...valid(),truth_checked:false}),/truth assertion/);
 assert.throws(()=>validateReceipt({...valid(),source_hash:null}),/source or generation/);
});
test('censored and invalid durations cannot qualify',()=>{
 for(const event_to_stable_ms of [null,NaN,-1,Infinity,45001])
  assert.throws(()=>validateReceipt({...valid(),event_to_stable_ms}));
});
