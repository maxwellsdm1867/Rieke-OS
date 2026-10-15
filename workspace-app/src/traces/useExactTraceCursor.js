import {useRetainedView} from '../retainedWorkspaceViews.js';
import {useLayoutEffect,useMemo,useRef,useState} from 'react';
import {readWholeTrace} from './readWholeTrace.js';

const TILE=20000,HOVER_DELAY=50;
// One mounted raw tile and one latest intent, never a background whole read.
export function useExactTraceCursor({enabled,identity,owner,request,epochUuid,sourceSha256,stream,readContext}){
 const retainedActive=useRetainedView()?.active!==false;
 const lifetime=useMemo(()=>({}),[enabled,identity,owner,request,retainedActive]);
 const active=useRef(null),tile=useRef(null),pending=useRef(null),latest=useRef(null),timer=useRef(null),failure=useRef(null);
 const [version,setVersion]=useState(0);
 useLayoutEffect(()=>{
  if(!retainedActive)return;
  active.current=lifetime;
  return()=>{active.current=null;clearTimeout(timer.current);pending.current?.controller.abort();pending.current=null;latest.current=null;tile.current=null;failure.current=null;};
 },[lifetime]);
 function sample(index){
  if(!enabled||!retainedActive||active.current!==lifetime)return {state:'pending'};
  const loaded=tile.current;
  if(loaded?.lifetime===lifetime&&index>=loaded.start&&index<loaded.start+loaded.count)return {state:'ready',value:loaded.values[index-loaded.start]};
  const failed=failure.current;
  return failed?.lifetime===lifetime&&index>=failed.start&&index<failed.start+failed.count?{state:'error',error:failed.error}:{state:'pending'};
 }
 function read(index,{immediate=false}={}){
  if(!enabled||!retainedActive||active.current!==lifetime||!Number.isSafeInteger(index)||index<0||index>=stream.sample_count)return;
  const start=Math.floor(index/TILE)*TILE,count=Math.min(TILE,stream.sample_count-start);
  latest.current={lifetime,index,start,count};clearTimeout(timer.current);
  if(sample(index).state==='ready'){if(pending.current?.start!==start){pending.current?.controller.abort();pending.current=null;}return;}
  if(pending.current?.lifetime===lifetime&&pending.current.start===start)return;
  const dispatch=()=>{
   const wanted=latest.current;if(active.current!==lifetime||wanted?.lifetime!==lifetime)return;
   pending.current?.controller.abort();tile.current=null;failure.current=null;
   const controller=new AbortController(),operation={lifetime,start:wanted.start,count:wanted.count,controller};pending.current=operation;
   readWholeTrace({request,epochUuid,sourceSha256,stream,readContext,signal:controller.signal,
    window:{start:wanted.start,count:wanted.count}}).then(value=>{
     if(active.current!==lifetime||controller.signal.aborted||pending.current!==operation)return;
     pending.current=null;if(latest.current?.start!==wanted.start)return;
     tile.current={...value,lifetime};setVersion(value=>value+1);
    },error=>{
     if(active.current!==lifetime||controller.signal.aborted||pending.current!==operation)return;
     pending.current=null;if(latest.current?.start!==wanted.start)return;
     failure.current={lifetime,start:wanted.start,count:wanted.count,error:error.message};setVersion(value=>value+1);
    });
  };
  if(immediate)dispatch();else timer.current=setTimeout(dispatch,HOVER_DELAY);
 }
 return {sample,read,version};
}
