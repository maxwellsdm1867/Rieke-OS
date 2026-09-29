import { useState } from 'react';
import { Activity, Archive, ArrowLeft, ArrowRight, Clock3, Database, Download, GitBranch, RefreshCw, Search, ShieldCheck, Snowflake, MessageCircle, UserRound, Upload } from 'lucide-react';
import { api, useResource, humanize, time, number } from '../api.js';
import { Badge, Empty, Status } from './Common.jsx';
import './MasterLog.css';

function ActionIcon({action}) {
  const Icon = action?.includes('frozen') ? Snowflake : action?.includes('archived') ? Archive :
    action?.includes('import') ? Upload : action?.includes('export') ? Download :
    /curation|annotation/.test(action || '') ? MessageCircle : /query|protocol_dataset|explorer_revision/.test(action || '') ? GitBranch : Activity;
  return <Icon size={16} aria-hidden="true"/>;
}

function TagActivity({event}){
  const activity=event.tag_activity;
  if(!activity)return null;
  return <span className="log-tag-activity"><span className="log-authors">{activity.authors.map(author=><span className="log-author" key={author.profile_uuid||author.name} title={`Tag author profile: ${author.profile_uuid||'not recorded'}`}><UserRound size={12}/>{author.name}</span>)}{activity.author_count>activity.authors.length&&<small>+{activity.author_count-activity.authors.length} authors</small>}</span><span className="log-tag-changes">{activity.changes.map((change,index)=><span key={index} className={`log-tag-change ${change.operation}`} title={`${change.author} · ${change.targets} ${change.scope} targets`}><MessageCircle size={12}/>{change.operation==='removed'?'Removed':'Added'} “{change.tag}” <small>· {change.targets} {change.scope}{change.targets===1?'':'s'} · {change.author}</small></span>)}</span>{activity.change_count>activity.changes.length&&<small>+{activity.change_count-activity.changes.length} more changes in complete event</small>}</span>;
}

function EventDetails({id}) {
  const result = useResource(`/events/${id}`);
  const event = result.data?.event;
  return <Status {...result} retry={result.reload}>{event && <div className="log-detail">
    <p className="log-actor-note">Recorded by: {event.actor||'Actor not recorded'}. Tag author profiles are shown separately below.</p><TagActivity event={event}/><dl><div><dt>Event identity</dt><dd>{event.event_uuid}</dd></div>
      <div><dt>Operation identity</dt><dd>{event.audit_summary?.operation_uuid || 'Not recorded'}</dd></div>
      <div><dt>Version evidence</dt><dd>{event.audit_summary?.versioned ? 'Recorded at the time of this action' : 'Legacy record · code versions were not recorded'}</dd></div>
    </dl>
    <details><summary>Complete event · changes, inputs, outputs and versions</summary><pre>{JSON.stringify(event, null, 2)}</pre></details>
  </div>}</Status>;
}

export default function MasterLog({revision, onProtocol}) {
  const [offset, setOffset] = useState(0), [action, setAction] = useState('');
  const [search, setSearch] = useState(''), [expanded, setExpanded] = useState(null);
  const [error, setError] = useState('');
  const result = useResource(`/events?${new URLSearchParams({offset,limit:50,...(action?{action}:{})})}`, revision);
  const events = result.data?.events || [];
  const matching = events.filter(event => JSON.stringify(event).toLowerCase().includes(search.toLowerCase()));
  async function openSuggestion(suggestion) {
    setError('');
    try {
      if (suggestion.dataset_uuid) {
        const recipe = await api(`/exports/${suggestion.dataset_uuid}/reuse`);
        onProtocol(recipe.protocol_uuid, recipe);
      } else onProtocol(suggestion.protocol_uuid);
    } catch (e) {setError(e.message);}
  }
  return <div className="page master-log">
    <div className="page-heading"><div><div className="eyebrow">PROJECT RECORD</div><h1>Activity & logs</h1>
      <p>Who changed what, when it happened, and the recorded versions and source fingerprints.</p></div>
      <button onClick={result.reload}><RefreshCw size={15}/> Refresh</button></div>
    <div className="source-strip"><Database size={16}/><span>SQL action history · <code>recording_workspace.Event</code></span><Badge kind="info"><ShieldCheck size={12}/> Curation audited transactionally</Badge></div>
    <details className="log-note"><summary>What gets recorded?</summary><p>Imports, data store state, tags, inclusion, query revisions and exports retain their recorded evidence. Open an event for changes and versions. Data stores shows each recording’s linked history; Files & database contains parser and diagnostic logs. Browsing traces does not create a data-edit event.</p></details>
    {(result.data?.suggestions || []).length > 0 && <section className="section log-suggestions"><h2>Repeated workflows</h2><p>Suggestions from recorded actions. Open a workspace to review the query and scope before running it.</p>
      {result.data.suggestions.map(s=><div key={`${s.action}:${s.protocol_uuid}`}><Clock3 size={16}/><span><strong>{s.label}</strong><small>{number(s.count)} matching actions in this page of history</small></span><button onClick={()=>openSuggestion(s)}>Open for review <ArrowRight size={14}/></button></div>)}
    </section>}
    <div className="filter-bar log-filters"><label>Action<select aria-label="Filter history by action" value={action} onChange={e=>{setAction(e.target.value);setOffset(0);setExpanded(null);}}>
      <option value="">All actions</option><option value="shared_annotations_updated">Cell & epoch tags</option><option value="annotation_profile_created">Tag author profiles</option><option value="curation_updated">Tags, inclusion & review</option>
      <option value="dataset_revision_exported">Exports</option><option value="query_refreshed">Query comparisons</option><option value="explorer_revision_created">Predicate & tree revisions</option><option value="protocol_dataset_bound">Protocol dataset updates</option>
      <option value="imported">Source imports</option><option value="import_job_failed">Failed import jobs</option>
      <option value="data_store_query_excluded">Excluded from new queries</option><option value="data_store_query_included">Included in new queries</option><option value="import_job_duplicate">Duplicate import skipped</option><option value="data_store_frozen">Data store frozen</option><option value="data_store_unfrozen">Data store unfrozen</option><option value="data_store_archived">Data store archived</option><option value="data_store_restored">Data store restored</option><option value="storage_relocated">Storage moves</option>
    </select></label><label className="log-search"><Search size={15}/><input aria-label="Search this history page" placeholder="Search this page: author, tag, actor or event ID" value={search} onChange={e=>setSearch(e.target.value)}/></label></div>
    {error&&<div className="error" role="alert">{error}</div>}
    <section className="section"><Status {...result} retry={result.reload}>
      {matching.length ? <div className="log-events">{matching.map(event=><article key={event.event_uuid}>
        <button className="log-event" aria-expanded={expanded===event.event_uuid} onClick={()=>setExpanded(expanded===event.event_uuid?null:event.event_uuid)}>
          <span className="event-icon"><ActionIcon action={event.action}/></span><span className="log-event-title"><strong>{event.action==='shared_annotations_updated'?'Tags updated':event.action==='annotation_profile_created'?'Tag author created':humanize(event.action).replace(/_/g,' ')}</strong><small>Recorded by {event.actor} · {event.action?.startsWith('data_store_') ? '1 data store' : event.audit_summary?.entity_count != null ? `${number(event.audit_summary.entity_count)} ${event.action==='shared_annotations_updated'?'targets':'epochs'}` : event.event_uuid.slice(0,8)}</small><TagActivity event={event}/></span>
          <Badge kind={event.audit_summary?.outcome==='failed'?'warning':'neutral'}>{event.audit_summary?.outcome || 'Recorded'}</Badge>
          <Badge kind={event.audit_summary?.versioned?'success':'neutral'}>{event.audit_summary?.versioned?'Versioned':'Legacy'}</Badge>
          <time>{time(event.occurred_at)}</time></button>
        {expanded===event.event_uuid&&<EventDetails id={event.event_uuid}/>}
      </article>)}</div>:<Empty title={search?'No matches on this page':'No matching events'}>Change the action filter or browse another page of history.</Empty>}
      <div className="log-pagination"><span>Page {Math.floor(offset/50)+1} · {events.length} records{search?` · ${matching.length} shown`:''}</span><button disabled={offset===0||result.loading} onClick={()=>{setOffset(Math.max(0,offset-50));setExpanded(null);}}><ArrowLeft size={14}/> Newer</button><button disabled={!result.data?.has_more||result.loading} onClick={()=>{setOffset(offset+50);setExpanded(null);}}>Older <ArrowRight size={14}/></button></div>
    </Status></section>
  </div>;
}
