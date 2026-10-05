import {useEffect,useRef,useState} from 'react';
import {uploadRecording} from './uploadRecording.js';
import {isImportPending} from './importProgress.js';

// Keep the queue at app level so changing pages does not lose selected files.
export default function useImportQueue(monitor,setTransfer,onChange){
  const [files,setFiles]=useState([]),[waiting,setWaiting]=useState(null),[uploading,setUploading]=useState(false),[error,setError]=useState('');
  const submitting=useRef(false);
  const jobs=monitor.data?.jobs||[];
  const active=jobs.some(isImportPending);
  useEffect(()=>{
    const job=jobs.find(item=>item.job_uuid===waiting);
    if(!job||isImportPending(job))return;
    setWaiting(null);
    if(!['complete','completed','success','duplicate','complete_with_warnings'].includes(job.status)){
      setFiles([]);setError('Import stopped. Check import history before selecting the remaining files again.');
    }
  },[monitor.data,waiting]);
  useEffect(()=>{
    if(!files.length||waiting||active||monitor.loading||monitor.error||submitting.current)return;
    const file=files[0];submitting.current=true;setUploading(true);setFiles(rest=>rest.slice(1));
    setTransfer({phase:'uploading',filename:file.name,started_at:new Date().toISOString(),loaded:0,total:null,file_size:file.size});
    uploadRecording(file,update=>setTransfer(previous=>({...previous,...update}))).then(result=>{
      setWaiting(result.job_uuid);setTransfer(previous=>({...previous,phase:'accepted',job_uuid:result.job_uuid}));monitor.reload();onChange();
    }).catch(error=>{
      setFiles([]);setError(error.message+' Select any remaining files again after checking import history.');
      setTransfer(previous=>({...previous,phase:'error',error:error.message,requestRejected:!!error.requestRejected}));monitor.reload();
    }).finally(()=>{submitting.current=false;setUploading(false);});
  },[files,waiting,active,monitor.loading,monitor.error]);
  const busy=uploading||!!waiting||files.length>0;
  function enqueue(selected){
    if(busy||active||submitting.current)return;
    const batch=Array.from(selected||[]);
    if(!batch.length)return;
    if(batch.some(file=>!file.size||!/\.(h5|hdf5)$/i.test(file.name))){setError('Choose nonempty H5 or HDF5 files.');return;}
    setError('');setFiles(batch);
  }
  return {enqueue,busy,error,remaining:files.length,active:busy||active};
}
