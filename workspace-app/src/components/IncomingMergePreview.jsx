import {ArrowRight,CheckSquare,Copy,GitMerge,Layers,Plus,ShieldCheck,TriangleAlert} from 'lucide-react';
import {number} from '../api.js';
import {workbenchPreviewCounts} from '../workbenchAuthority.js';
import NeuronIcon from './NeuronIcon.jsx';

export default function IncomingMergePreview({preview,context,children}){
  const counts=Object.fromEntries(workbenchPreviewCounts(preview).map(value=>[value.key,value]));
  const contextMatches=context?.candidate_scope_revision===preview.expected_candidate_scope_revision&&context?.draft?.draft_version===preview.expected_draft_version;
  const notes=contextMatches?[
    {key:'excluded_epochs',label:'Draft exclusions retained',Icon:ShieldCheck},
    {key:'conflicting_epochs',label:'Conflicts in incoming scope',Icon:TriangleAlert},
  ].filter(({key})=>Number.isSafeInteger(context.counts?.[key])&&context.counts[key]>0):[];
  const metric=(key,Icon,emphasis=false)=><dl className={`incoming-preview-metric ${emphasis?'is-addition':''}`} key={key}><dt><Icon size={16} aria-hidden="true"/>{counts[key].label}</dt><dd>{number(counts[key].count)}</dd></dl>;
  return <section className="incoming-merge-preview" aria-label="Additive acceptance preview">
    <header><div><GitMerge size={18} aria-hidden="true"/><h2>{preview.mode==='all'?'All eligible incoming additions':'Selected incoming additions'}</h2></div><div className="incoming-preview-actions">{children}</div></header>
    <div className="incoming-preview-flow" aria-label="Exact merge scope">
      {metric('retained_epoch_count',Layers)}<Plus size={18} aria-hidden="true"/>
      {metric('accepted_epoch_count',Plus,true)}<ArrowRight size={18} aria-hidden="true"/>
      {metric('next_epoch_count',GitMerge)}
    </div>
    <div className="incoming-preview-support">
      {metric('selected_epoch_count',CheckSquare)}{metric('accepted_cell_count',NeuronIcon)}{metric('already_present_epoch_count',Copy)}
      <span className="incoming-preview-preserved"><ShieldCheck size={14} aria-hidden="true"/>Main preserved · exclusions retained</span>
      {notes.map(({key,label,Icon})=><span className={`incoming-preview-note ${key==='conflicting_epochs'?'is-warning':''}`} key={key}><Icon size={14} aria-hidden="true"/>{label}<strong>{number(context.counts[key])}</strong></span>)}
    </div>
  </section>;
}
