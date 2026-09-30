// Synthetic read-only comparison; no production API or recordings.
import assert from 'node:assert/strict';
import {performance} from 'node:perf_hooks';
import {writeFile} from 'node:fs/promises';
import {registeredMetadataField} from '../../../workspace-app/src/components/metadataValues.js';
const fields=Array.from({length:10000},(_,i)=>({id:`parameters/p${i}`}));
const paths=Array.from({length:100},(_,i)=>['parameters',`p${9900+i}`]);
function original(path,fields){return fields.find(field=>{
  if(!field.id.includes('/'))return path.length===1&&field.path===path[0];
  try{const parts=field.id.split('/').map(part=>decodeURIComponent(part).replace(/~1/g,'/').replace(/~0/g,'~'));return parts.length===path.length&&parts.every((part,index)=>part===path[index]);}catch{return false;}
});}
const measure=run=>{const start=performance.now();const found=paths.map(run);assert.deepEqual(found,fields.slice(9900));return performance.now()-start;};
const cold=measure(path=>registeredMetadataField(path,fields));
const samples=Array.from({length:5},()=>measure(path=>registeredMetadataField(path,fields)));
const originalSamples=Array.from({length:3},()=>measure(path=>original(path,fields)));
const median=values=>[...values].sort((a,b)=>a-b)[Math.floor(values.length/2)];
const result={measured_at:new Date().toISOString(),node:process.version,platform:process.platform,arch:process.arch,field_count:fields.length,lookup_count:paths.length,cold_index_and_lookups_ms:cold,warm_lookup_samples_ms:samples,warm_lookup_median_ms:median(samples),original_scan_samples_ms:originalSamples,original_scan_median_ms:median(originalSamples),exact_field_identity_order_preserved:true,limitations:['Synthetic helper measurement, not browser commit time or end-to-end latency.','Original comparator is the pre-change lookup expression; both implementations return the exact same 100 field objects.']};
console.log(JSON.stringify(result,null,2));
await writeFile(new URL('./metadata-field-index.fixed.json',import.meta.url),JSON.stringify(result,null,2)+'\n');
