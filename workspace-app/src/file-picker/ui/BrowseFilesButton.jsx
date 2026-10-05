import {useRef} from 'react';
import {FolderOpen} from 'lucide-react';

export default function BrowseFilesButton({label='Browse files…',accept,multiple=false,disabled=false,onChoose,className='button'}){
  const input=useRef(null);
  function choose(event){
    const files=Array.from(event.target.files||[]);
    event.target.value='';
    if(files.length)onChoose?.(files);
  }
  return <><input ref={input} type="file" accept={accept} multiple={multiple} disabled={disabled} hidden onChange={choose}/><button type="button" className={className} disabled={disabled} onClick={()=>input.current?.click()}><FolderOpen size={16}/>{label}</button></>;
}
