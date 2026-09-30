import {useEffect,useRef,useState} from 'react';
import {desktopBridge,registerDraftSaver} from './desktopLifecycle.js';
import {createDesktopDraftSession} from './desktopDraftSession.js';
export function useDesktopDraft({projectId,snapshot,restore,busy}){
  const current=useRef({snapshot,restore,busy});current.current={snapshot,restore,busy};
  const session=useRef(null),[state,setState]=useState({phase:'inactive'});
  useEffect(()=>{
    const bridge=desktopBridge();if(!bridge||!projectId)return;
    const draft=createDesktopDraftSession({bridge,projectId,snapshot:()=>current.current.snapshot(),restore:value=>current.current.restore(value),isBusy:()=>current.current.busy,onState:setState});
    session.current=draft;
    const stop=registerDraftSaver(()=>draft.flush());
    const timer=setInterval(()=>{if(!current.current.busy)draft.flush().catch(()=>{});},3000);
    return()=>{draft.close();stop();clearInterval(timer);if(session.current===draft)session.current=null;};
  },[projectId]);
  return {...(state.projectId===projectId?state:{phase:'inactive'}),
    startFresh:()=>session.current?.fresh(),retry:()=>session.current?.retry(),
    async quitPreserving(){session.current?.preserveForQuit();return desktopBridge().quit();}};
}
