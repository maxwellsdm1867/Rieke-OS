'use strict';
// One owned timer and in-flight sample. Stop drains before another variant starts.
function startSampler(sample, interval=1000) {
 let stopped=false,timer=null,work=Promise.resolve();
 function tick(){if(stopped)return;work=Promise.resolve().then(sample).finally(()=>{if(!stopped)timer=setTimeout(tick,interval);});}
 tick();
 return async()=>{stopped=true;if(timer!==null)clearTimeout(timer);await work;};
}
module.exports={startSampler};
