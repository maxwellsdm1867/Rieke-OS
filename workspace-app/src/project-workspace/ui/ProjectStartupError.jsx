import {useEffect,useRef,useState} from 'react';

export default function ProjectStartupError({message,className}){
  const [copy,setCopy]=useState(null);
  const generation=useRef(0);
  useEffect(()=>{generation.current++;setCopy(null);return()=>{generation.current++;};},[message]);
  if(!message)return null;
  const diagnostic=message.startsWith('Disco could not open this project. ');
  async function copyDetails(){
    const current=++generation.current;
    try{await navigator.clipboard.writeText(message);if(current===generation.current)setCopy({message,text:'Details copied'});}
    catch{if(current===generation.current)setCopy({message,text:'Copy unavailable. Select the message and recovery log location to copy them.'});}
  }
  return <div className={className} role="alert"><span style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',userSelect:'text'}}>{message}</span>{diagnostic&&<><div><button type="button" onClick={copyDetails}>Copy recovery details</button></div>{copy?.message===message&&<small role="status">{copy.text}</small>}</>}</div>;
}
