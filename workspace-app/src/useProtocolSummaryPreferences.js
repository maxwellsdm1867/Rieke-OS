import {useEffect,useState} from 'react';
import {summaryPreferenceKey,summaryPreferences} from './requestedSummaries.js';

export function useProtocolSummaryPreferences(project,protocol,view='tree'){
  const key=project&&protocol?summaryPreferenceKey(project,protocol,view):null;
  const [state,setState]=useState({key:null,value:summaryPreferences(null),error:null});
  useEffect(()=>{
    if(!key){setState({key,value:summaryPreferences(null),error:null});return;}
    try{setState({key,value:summaryPreferences(JSON.parse(localStorage.getItem(key))),error:null});}
    catch{setState({key,value:summaryPreferences(null),error:'Summary preferences could not be read.'});}
  },[key]);
  const value=state.key===key?state.value:summaryPreferences(null);
  function update(fields){
    if(!key)return;
    const next=summaryPreferences({version:1,fields});
    try{localStorage.setItem(key,JSON.stringify(next));setState({key,value:next,error:null});}
    catch{setState({key,value:next,error:'Summary preferences could not be saved on this device.'});}
  }
  return {value,update,error:state.key===key?state.error:null,enabled:!!key};
}
