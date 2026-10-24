import {useAuthoredDraft} from '../../presentation/useAuthoredDraft.js';
import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {UserRound,Plus,X,Check} from 'lucide-react';
import {useAnnotationProfile} from '../annotationProfile.js';
import './TagExchange.css';
function authorInitials(name){
 const parts=(name||'').trim().split(/\s+/).filter(Boolean);
 return (parts.length>1?[parts[0],parts.at(-1)]:parts).map(part=>Array.from(part)[0]).join('').toUpperCase();
}
export default function AnnotationProfile(){
 const profile=useAnnotationProfile(),[prompted,setPrompted]=useState(false);
 const initials=authorInitials(profile.profileName);
 useEffect(()=>{if(!prompted&&!profile.loading&&!profile.error&&!profile.profileUuid){setPrompted(true);profile.openProfile();}},[prompted,profile.loading,profile.error,profile.profileUuid]);
 return <><button className="avatar annotation-profile-trigger" onClick={profile.openProfile} title={`Tag author: ${profile.profileName||'Choose profile'}`} aria-label="Choose tag author profile">{initials?<span aria-hidden="true">{initials}</span>:<UserRound size={17}/>}</button>{profile.profileOpen&&createPortal(<ProfileDialog profile={profile} onClose={profile.closeProfile}/>,document.body)}</>;
}
function ProfileDialog({profile,onClose}){
 const dialog=useRef(null),[name,setName]=useAuthoredDraft(['annotation-profile','new-author-name'],''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{const element=dialog.current;element.showModal();return()=>element.close();},[]);
 async function choose(uuid){if(busy)return;setBusy(true);setError('');try{await profile.selectProfile(uuid);onClose();}catch(error){setError(error.message);}finally{setBusy(false);}}
 async function create(event){event.preventDefault();if(busy||!name.trim())return;setBusy(true);setError('');try{await profile.createProfile(name.trim());setName('');onClose();}catch(error){setError(error.message);}finally{setBusy(false);}}
 return <dialog ref={dialog} className="tag-exchange-dialog profile-dialog" aria-labelledby="tag-profile-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}>
  <header><h2 id="tag-profile-title">Tag author</h2><button className="icon-button" disabled={busy} onClick={onClose} aria-label="Close tag author"><X size={18}/></button></header>
  <div className="tag-exchange-body">
   <p className="profile-intro">Choose who gets credit for new tags.</p>
   {profile.loading?<p role="status">Loading profiles…</p>:<div className="profile-choices" role="group" aria-label="Tag authors">
    {profile.profiles.map(item=><button className="profile-choice" key={item.profile_uuid} disabled={busy} aria-pressed={item.profile_uuid===profile.profileUuid} onClick={()=>choose(item.profile_uuid)}>
     <span className="profile-initials" aria-hidden="true">{authorInitials(item.display_name)||<UserRound size={16}/>}</span>
     <span className="profile-choice-name">{item.display_name}</span>
     {item.profile_uuid===profile.profileUuid&&<small><Check size={14} aria-hidden="true"/>Selected</small>}
    </button>)}
   </div>}
   <form className="profile-create" onSubmit={create}>
    <label htmlFor="new-author-name">Add author</label>
    <div className="profile-create-controls"><input id="new-author-name" aria-label="New author name" placeholder="Full name" value={name} maxLength={120} disabled={busy} onChange={event=>setName(event.target.value)}/><button disabled={busy||!name.trim()||profile.loading} aria-label="Create profile"><Plus size={15} aria-hidden="true"/>Add</button></div>
   </form>
   <details className="profile-help"><summary>About author profiles</summary><p>Your choice is remembered on this computer across projects. Existing tags keep their original author. Browsing does not require a profile.</p></details>
   {(error||profile.error)&&<p role="alert" className="tag-exchange-error">{error||profile.error}{profile.error&&<button onClick={profile.reload}>Retry profiles</button>}</p>}
  </div>
 </dialog>;
}
