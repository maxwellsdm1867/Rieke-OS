import {useLayoutEffect,useRef} from 'react';

// A retained Activity reconnect is not a new presentation identity. Run only
// when the explicit semantic identity/intent changes, including initial commit.
// The callback may synchronously reset presentation state or focus/scroll DOM.
// Never put requests, storage, subscriptions, cleanup, async work, or scientific
// authority/consent here: their ordinary effects must reconnect independently.
export function useSemanticReset(identity,resetPresentation){
  const committed=useRef({initialized:false,identity:null});
  useLayoutEffect(()=>{
    if(committed.current.initialized&&Object.is(committed.current.identity,identity))return;
    committed.current={initialized:true,identity};
    resetPresentation();
  },[identity,resetPresentation]);
}
