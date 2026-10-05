export default function SummaryPreferences({fields,preferences}){
  if(!preferences.enabled)return null;
  const byId=new Map(fields.map(field=>[field.id,field]));
  return <><details className="metadata-summary-preferences"><summary>Preferred summaries for this protocol</summary>
    <label>Add a field<select aria-label="Add preferred summary" value="" onChange={event=>{if(event.target.value)preferences.update([...preferences.value.fields,event.target.value]);}}><option value="">Choose metadata field</option>{fields.filter(field=>!preferences.value.fields.includes(field.id)&&!field.id.startsWith('joint/')).map(field=><option key={field.id} value={field.id}>{field.label||field.id}</option>)}</select></label>
    {preferences.value.fields.map(id=><div key={id}><span>{byId.get(id)?.label||id}</span><button type="button" aria-label={`Remove preferred summary ${id}`} onClick={()=>preferences.update(preferences.value.fields.filter(field=>field!==id))}>Remove</button></div>)}
  </details>{preferences.error&&<p role="alert">{preferences.error}</p>}</>;
}
