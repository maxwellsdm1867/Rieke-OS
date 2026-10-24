export default function ViewPreparation({resource}){
 const preparation=resource?.preparation||resource?.data?.preparation;
 if(!preparation&&!resource?.preparing&&!resource?.prepareError)return null;
 return <div className="view-preparation" role="status" aria-busy={resource.preparing||undefined}>
  <span>{resource.preparing?'Loading this view…':'This view could not finish loading.'}</span>{' '}
  {!resource.preparing&&<button onClick={()=>void resource.prepare()}>Retry</button>}
  {resource.prepareError&&<p role="alert">{resource.prepareError}</p>}
 </div>;
}
