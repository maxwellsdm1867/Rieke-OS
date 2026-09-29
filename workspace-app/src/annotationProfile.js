import {createContext,createElement,useContext,useEffect,useState} from 'react';
import {api,useResource} from './api.js';
const Context=createContext(null);
export function AnnotationProfileProvider({projectId,children}){
  const resource=useResource(projectId?'/annotation-profiles':null);
  const key=`workspace.annotation-profile.${projectId}`;
  const [selected,setSelected]=useState(''),[profileOpen,setProfileOpen]=useState(false);
  useEffect(()=>{try{setSelected(localStorage.getItem(key)||'');}catch{setSelected('');}},[key]);
  const profiles=resource.data?.profiles||[];
  const profile=profiles.find(item=>item.profile_uuid===selected);
  function selectProfile(uuid){if(!profiles.some(item=>item.profile_uuid===uuid))return;setSelected(uuid);try{localStorage.setItem(key,uuid);}catch{}}
  async function createProfile(display_name){const result=await api('/annotation-profiles',{method:'POST',body:{display_name}});const row=result.profile||result;setSelected(row.profile_uuid);try{localStorage.setItem(key,row.profile_uuid);}catch{}resource.reload();return row;}
  return createElement(Context.Provider,{value:{profileOpen,openProfile:()=>setProfileOpen(true),closeProfile:()=>setProfileOpen(false),profileUuid:profile?.profile_uuid||'',profileName:profile?.display_name||'',profiles,loading:!projectId||resource.loading,error:resource.error,selectProfile,createProfile,reload:resource.reload}},children);
}
export function useAnnotationProfile(){return useContext(Context)||{profiles:[],profileUuid:'',profileName:'',loading:false,error:'Tag profile is unavailable.'};}
