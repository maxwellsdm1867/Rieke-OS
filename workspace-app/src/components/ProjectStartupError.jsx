import {useState} from 'react';

export default function ProjectStartupError({message,className}){
  const [copy,setCopy]=useState(null);
  if(!message)return null;
  const diagnostic=message.startsWith('Disco could not open this project. ');
  async function copyDetails(){
    try{await navigator.clipboard.writeText(message);setCopy({message,text:'Details copied'});}
    catch{setCopy({message,text:'Copy unavailable. Select the message and recovery log location to copy them.'});}
  }
  return <div className={className} role="alert"><span style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',userSelect:'text'}}>{message}</span>{diagnostic&&<><div><button type="button" onClick={copyDetails}>Copy recovery details</button></div>{copy?.message===message&&<small role="status">{copy.text}</small>}</>}</div>;
}
