import {useEffect,useRef,useState} from 'react';
import {desktopBridge,registerDraftSaver} from '../desktopLifecycle.js';
import {createDesktopDraftSession} from './desktopDraftSession.js';
/**
 * Bind a real draft session to one mounted project's lifetime using the shared
 * desktop lifecycle registrar. Callbacks/busy/navigation intent are read live;
 * changing projectId closes/unregisters the old session and clears its 3s timer.
 * State from a previous project is hidden immediately. Returns visible draft
 * state plus startFresh, retry and quitPreserving; App owns recovery presentation.
 * No bridge or no project leaves the hook inactive. Cleanup does not cancel saves
 * already submitted to the native bridge, and restored views do not grant consent.
 */
export function useDesktopDraft({projectId,snapshot,restore,restoreRecovery,busy,navigationIdentity}){
  const current=useRef({snapshot,restore,restoreRecovery,busy,navigationIdentity});current.current={snapshot,restore,restoreRecovery,busy,navigationIdentity};
  const session=useRef(null),[state,setState]=useState({phase:'inactive'});
  useEffect(()=>{
    const bridge=desktopBridge();if(!bridge||!projectId)return;
    const draft=createDesktopDraftSession({bridge,projectId,snapshot:()=>current.current.snapshot(),navigationIdentity:()=>current.current.navigationIdentity?.(),restore:value=>current.current.restore(value),restoreRecovery:value=>current.current.restoreRecovery?.(value),isBusy:()=>current.current.busy,onState:setState});
    session.current=draft;
    const stop=registerDraftSaver(()=>draft.flush());
    const timer=setInterval(()=>{if(!current.current.busy)draft.flush().catch(()=>{});},3000);
    return()=>{draft.close();stop();clearInterval(timer);if(session.current===draft)session.current=null;};
  },[projectId]);
  return {...(state.projectId===projectId?state:{phase:'inactive'}),
    startFresh:()=>session.current?.fresh(),retry:()=>session.current?.retry(),
    async quitPreserving(){session.current?.preserveForQuit();return desktopBridge().quit();}};
}
