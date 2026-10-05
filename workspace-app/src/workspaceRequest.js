import {createContext,createElement,useContext,useMemo,useRef} from 'react';

const Context=createContext(null);
const unavailable=()=>Promise.reject(new Error('This workspace request port is unavailable.'));

// One immutable port per exact project/publication/scope. The adapter owns DTO
// authority and route admission; consumers never fall back from a supplied port.
export function WorkspaceRequestProvider({port,children}){
  const serial=useRef(0);
  // A scientific owner change retires all local read/action closures. Drafts and
  // presentation sessions live outside this lifetime and are supplied on restore.
  const lifetime=useMemo(()=>++serial.current,[port?.identity,port?.request]);
  const validIdentity=typeof port?.identity==='string'&&port.identity.trim().length>0;
  const value=useMemo(()=>({
    identity:port?.identity,
    authority:port?.authority,
    preparedTreeAuthority:port?.preparedTreeAuthority,
    shortcutCommands:port?.shortcutCommands,
    request:validIdentity&&typeof port?.request==='function'?port.request:unavailable,
    download:validIdentity&&typeof port?.download==='function'?port.download:unavailable,
    traceReadContext:port?.traceReadContext,
    pageSize:50,
  }),[port,validIdentity]);
  return createElement(Context.Provider,{value,key:lifetime},children);
}
export function useWorkspaceRequestScope(){return useContext(Context);}
export function useWorkspaceRequest(fallback){return useContext(Context)?.request??fallback;}
