// Preparation builds display projections only. It supplies no edit/merge consent.
// Coalesce concurrent consumers within an exact project owner and resource. Keep
// no completed-result cache: only fresh reads can establish current readiness.
const owners=new Map();
const aborted=()=>Object.assign(new Error('View preparation cancelled'),{name:'AbortError'});

export function prepareView(owner,path,{request,signal}={}){
 if(signal?.aborted)return Promise.reject(aborted());
 let resources=owners.get(owner);
 if(!resources){resources=new Map();owners.set(owner,resources);}
 let operation=resources.get(path);
 if(!operation){
  const controller=new AbortController();
  operation={controller,users:0};resources.set(path,operation);
  operation.promise=Promise.resolve().then(()=>{
   if(controller.signal.aborted)throw aborted();
   return request(path,{method:'POST',body:{},signal:controller.signal});
  }).finally(()=>{
   if(resources.get(path)===operation)resources.delete(path);
   if(!resources.size&&owners.get(owner)===resources)owners.delete(owner);
  });
 }
 operation.users++;
 return new Promise((resolve,reject)=>{
  let done=false;
  const finish=(callback,value)=>{
   if(done)return;done=true;signal?.removeEventListener('abort',cancel);operation.users--;
   // StrictMode reconnects may rejoin in this turn. One departing consumer
   // cannot cancel a request still needed by another visible consumer.
   queueMicrotask(()=>{
    if(!operation.users&&resources.get(path)===operation){
     resources.delete(path);if(!resources.size&&owners.get(owner)===resources)owners.delete(owner);
     operation.controller.abort();
    }
   });
   callback(value);
  };
  const cancel=()=>finish(reject,aborted());
  signal?.addEventListener('abort',cancel,{once:true});
  operation.promise.then(value=>finish(resolve,value),error=>finish(reject,error));
 });
}
