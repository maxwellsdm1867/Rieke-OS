export default function ViewPreparation({resource}){
 const preparation=resource?.preparation||resource?.data?.preparation;
 if(!preparation&&!resource?.preparing&&!resource?.prepareError)return null;
 return <div className="view-preparation" role="status" aria-busy={resource.preparing||undefined}>
  <span>{resource.preparing?'Preparing this view…':preparation?.status==='failed'?'Exact duration is unavailable. Prepare this view to try again.':'This view needs preparation.'}</span>{' '}
  <button disabled={resource.preparing} onClick={()=>void resource.prepare()}>{resource.preparing?'Preparing…':'Prepare view'}</button>
  {resource.prepareError&&<p role="alert">{resource.prepareError}</p>}
 </div>;
}
