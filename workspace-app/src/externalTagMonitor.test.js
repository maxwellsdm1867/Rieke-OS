import test from 'node:test';
import assert from 'node:assert/strict';
import {startExternalTagMonitor} from "./annotations/externalTagMonitor.js";
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('the startup baseline does not reload; unchanged scans do not reload; changed revisions refresh',async()=>{
  let changes=0,revision='a';const timers=[];
  const monitor=startExternalTagMonitor({scan:async()=>({revision,receipts:[{addition_count:3,received_at:'2026-01-01T00:00:00Z'}]}),onChange:()=>changes++,onStatus:()=>{},onError:assert.fail,schedule:fn=>{timers.push(fn);return fn;},cancel:()=>{},startedAt:Date.parse('2026-10-18T00:00:00Z')});
  await flush();assert.equal(changes,0,'receipts from earlier sessions are already in every read');
  await monitor.check();assert.equal(changes,0);
  revision='b';await monitor.check();assert.equal(changes,1);monitor.stop();
});
test('a first scan that ingested messages this session refreshes once',async()=>{
  let changes=0;const startedAt=Date.parse('2026-10-18T00:00:00Z');
  const monitor=startExternalTagMonitor({scan:async()=>({revision:'a',receipts:[{addition_count:2,received_at:'2026-10-18T00:00:01Z'},{addition_count:0,received_at:'2026-10-18T00:00:02Z'}]}),onChange:()=>changes++,onStatus:()=>{},onError:assert.fail,schedule:()=>1,cancel:()=>{},startedAt});
  await flush();assert.equal(changes,1);await monitor.check();assert.equal(changes,1);monitor.stop();
});
test('slow scans cannot overlap and late responses after unmount are discarded',async()=>{
  let resolve,calls=0;const changes=[];
  const monitor=startExternalTagMonitor({scan:()=>{calls++;return new Promise(r=>resolve=r);},onChange:()=>changes.push(1),onStatus:assert.fail,onError:assert.fail,schedule:assert.fail,cancel:()=>{}});
  await monitor.check();assert.equal(calls,1);monitor.stop();resolve({revision:'a'});await flush();assert.deepEqual(changes,[]);
});
test('errors back off, retain revision and recover on focus check',async()=>{
  let fail=true,changes=0;const delays=[],errors=[];
  const monitor=startExternalTagMonitor({scan:async()=>{if(fail)throw new Error('offline');return {revision:'a'};},onChange:()=>changes++,onStatus:()=>{},onError:message=>errors.push(message),schedule:(_,delay)=>{delays.push(delay);return 1;},cancel:()=>{}});
  await flush();assert.deepEqual(errors,['offline']);assert.equal(delays[0],6000);assert.equal(changes,0);
  fail=false;await monitor.check();assert.equal(changes,0,'first successful scan is the baseline');assert.equal(delays.at(-1),3000);monitor.stop();
});
