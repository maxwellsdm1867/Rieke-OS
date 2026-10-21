import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {createSourceMerge} from './sourceMerge.js';
import {registerUnmountGuard} from '../desktopLifecycle.js';
export default function useSourceMerge({projectId,request,persist,ownerKey,onAccepted,onReviewed}){
 const latest=useRef({projectId,ownerKey,token:{},mounted:false,onAccepted,onReviewed});
 if(latest.current.projectId!==projectId||latest.current.ownerKey!==ownerKey)latest.current.token={};
 Object.assign(latest.current,{projectId,ownerKey,onAccepted,onReviewed});
 const [,render]=useState(0);
 const controller=useMemo(()=>createSourceMerge({projectId,request,persist,owner:()=>latest.current.token,onState:()=>render(n=>n+1)}),[projectId,request,persist]);
 useLayoutEffect(()=>{latest.current.mounted=true;controller.open();const stop=registerUnmountGuard(()=>['preparing','accepting','unconfirmed'].includes(controller.state.phase)?'Finish or recover the recording merge before unmounting.':null);return()=>{latest.current.mounted=false;latest.current.token={};stop();controller.close();};},[controller]);
 useEffect(()=>{if(controller.state.phase!=='error')return;const timer=setTimeout(()=>controller.dismiss(),8000);return()=>clearTimeout(timer);},[controller,controller.state]);
 const complete=async action=>{const token=latest.current.token,result=await action();if(latest.current.mounted&&latest.current.projectId===projectId){if(result.reviewFinished)latest.current.onReviewed?.(result.protocolId,result.receipt);else latest.current.onAccepted(result.protocolId,{navigate:latest.current.token===token},result.receipt);}return true;};
 return {state:controller.state,dismiss:controller.dismiss,snapshot:controller.snapshot,restore:controller.restore,start:(protocol,options)=>complete(()=>controller.start(protocol,options)),startAll:(protocol,options)=>complete(()=>controller.startAll(protocol,options)),finish:(protocol,options)=>complete(()=>controller.finish(protocol,options)),recover:()=>complete(()=>controller.recover()),retry:()=>complete(()=>controller.recover({retry:true}))};
}
