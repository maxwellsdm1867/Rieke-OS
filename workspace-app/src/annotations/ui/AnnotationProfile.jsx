import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {UserRound,Plus,X} from 'lucide-react';
import {useAnnotationProfile} from '../annotationProfile.js';
import './TagExchange.css';
export default function AnnotationProfile(){
 const profile=useAnnotationProfile(),[prompted,setPrompted]=useState(false);
 useEffect(()=>{if(!prompted&&!profile.loading&&!profile.error&&!profile.profileUuid){setPrompted(true);profile.openProfile();}},[prompted,profile.loading,profile.error,profile.profileUuid]);
 return <><button className="avatar annotation-profile-trigger" onClick={profile.openProfile} title={`Tag author: ${profile.profileName||'Choose profile'}`} aria-label="Choose tag author profile"><UserRound size={17}/></button>{profile.profileOpen&&createPortal(<ProfileDialog profile={profile} onClose={profile.closeProfile}/>,document.body)}</>;
}
function ProfileDialog({profile,onClose}){
 const dialog=useRef(null),[name,setName]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{const element=dialog.current;element.showModal();return()=>element.close();},[]);
 async function choose(uuid){if(busy)return;setBusy(true);setError('');try{await profile.selectProfile(uuid);onClose();}catch(error){setError(error.message);}finally{setBusy(false);}}
 async function create(event){event.preventDefault();if(busy||!name.trim())return;setBusy(true);setError('');try{await profile.createProfile(name.trim());onClose();}catch(error){setError(error.message);}finally{setBusy(false);}}
 return <dialog ref={dialog} className="tag-exchange-dialog profile-dialog" aria-labelledby="tag-profile-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}><header><h2 id="tag-profile-title"><UserRound size={18}/> Tag author</h2><button className="icon-button" disabled={busy} onClick={onClose} aria-label="Close tag author"><X size={17}/></button></header><div className="tag-exchange-body"><p>Choose or create the author recorded on your tags. Your choice is remembered on this computer and used across projects. Existing tags keep their original author. You can browse without choosing; tagging requires a profile.</p>{profile.loading?<p role="status">Loading profiles…</p>:profile.profiles.map(item=><button className="profile-choice" key={item.profile_uuid} disabled={busy} aria-pressed={item.profile_uuid===profile.profileUuid} onClick={()=>choose(item.profile_uuid)}><UserRound size={15}/><span>{item.display_name}</span>{item.profile_uuid===profile.profileUuid&&<small>Current</small>}</button>)}<form onSubmit={create}><label>New author name<input value={name} maxLength={120} disabled={busy} onChange={event=>setName(event.target.value)}/></label><button disabled={busy||!name.trim()||profile.loading}><Plus size={14}/> Create profile</button></form>{(error||profile.error)&&<p role="alert" className="tag-exchange-error">{error||profile.error}{profile.error&&<button onClick={profile.reload}>Retry profiles</button>}</p>}</div></dialog>;
}
