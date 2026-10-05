import {createSharedReads} from '../resourceRequest.js';

// One tree owns this pool for one exact source/revision/request authority.
// Expansion and first-epoch selection may share work, never freshness receipts.
export function createEpochPageReads(request){
  const pool=createSharedReads(request);
  return {
    load(path,options={}){
      const {signal,...identity}=options,method=(options.method||'GET').toUpperCase();
      const pathname=path.split('?')[0];
      if(!(method==='GET'&&pathname.endsWith('/epochs')||method==='POST'&&pathname==='/explore/epochs'))return Promise.reject(new Error('Only epoch page reads can be shared'));
      return pool.load(JSON.stringify([path,identity]),path,options);
    },
    reload:request,
  };
}
