import {createContext,createElement,useContext,useEffect,useState} from 'react';
import {api,useResource} from './api.js';
const Context=createContext(null);
export function AnnotationProfileProvider({projectId,children}){
  const resource=useResource(projectId?'/annotation-profiles':null,projectId);
  const key=`workspace.annotation-profile.${projectId}`;
  const [selected,setSelected]=useState(''),[profileOpen,setProfileOpen]=useState(false),[preferenceError,setPreferenceError]=useState('');
  useEffect(()=>{try{setSelected(localStorage.getItem(key)||'');}catch{setSelected('');}},[key]);
  const profiles=resource.data?.profiles||[];
  const profile=profiles.find(item=>item.profile_uuid===(resource.data?.selected_profile_uuid||selected));
  async function rememberChoice(uuid){
    const result=await api('/annotation-profiles/selected',{method:'POST',body:{profile_uuid:uuid}});
    setSelected(result.selected_profile_uuid);setPreferenceError('');
    try{localStorage.setItem(key,result.selected_profile_uuid);}catch{}
    resource.reload();return result.profile;
  }
  async function selectProfile(uuid){if(!profiles.some(item=>item.profile_uuid===uuid))throw new Error('Choose an existing tag author.');return rememberChoice(uuid);}
  async function createProfile(display_name){const result=await api('/annotation-profiles',{method:'POST',body:{display_name}});const row=result.profile||result;await rememberChoice(row.profile_uuid);return row;}
  // Adopt an existing browser choice once; future project addresses use the
  // selected author supplied by the machine preference, without another prompt.
  useEffect(()=>{
    if(resource.loading||resource.error||resource.data?.selected_profile_uuid||!selected||!profiles.some(item=>item.profile_uuid===selected))return;
    let cancelled=false;
    api('/annotation-profiles/selected',{method:'POST',body:{profile_uuid:selected}}).then(()=>{if(!cancelled)resource.reload();}).catch(error=>{if(!cancelled)setPreferenceError(error.message);});
    return()=>{cancelled=true;};
  },[resource.loading,resource.error,resource.data?.selected_profile_uuid,selected,projectId]);
  return createElement(Context.Provider,{value:{profileOpen,openProfile:()=>setProfileOpen(true),closeProfile:()=>setProfileOpen(false),profileUuid:profile?.profile_uuid||'',profileName:profile?.display_name||'',profiles,loading:!projectId||resource.loading,error:resource.error||preferenceError,selectProfile,createProfile,reload:resource.reload}},children);
}
export function useAnnotationProfile(){return useContext(Context)||{profiles:[],profileUuid:'',profileName:'',loading:false,error:'Tag profile is unavailable.'};}
