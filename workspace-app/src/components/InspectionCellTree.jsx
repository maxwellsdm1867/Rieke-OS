import {useMemo,useState} from 'react';
import {MessageCircle} from 'lucide-react';
import {humanize,number} from '../api.js';
import {inspectionDates} from '../inspectionCellTree.js';
import {annotationIndicator} from '../annotationTags.js';
import {datedCellLabel} from '../recordingIdentity.js';
import {Status} from './Common.jsx';
import './InspectionCellTree.css';
import {useEpochBrowserPage} from '../useEpochBrowserPage.js';

function CellEpochs({cell,source,revision,focused,onFocus,targets,setTargets,disabled}){
  const [offset,setOffset]=useState(0);
  const page=useEpochBrowserPage(source,{cellUuid:cell.cell_uuid,offset},revision);
  return <Status {...page} retry={page.reload}>
    <div className="cell-epoch-actions"><button disabled={disabled||page.loading} onClick={()=>setTargets(old=>[...new Set([...old,...(page.data?.epochs||[]).map(e=>e.epoch_uuid)])])}>Select this page</button></div>
    {(page.data?.epochs||[]).map((epoch,index)=>{const tags=annotationIndicator(epoch);return <div key={epoch.epoch_uuid} className={`epoch-row cell-tree-epoch ${focused===epoch.epoch_uuid?'active':''}`}>
      <input type="checkbox" disabled={disabled||page.loading} checked={targets.includes(epoch.epoch_uuid)} aria-label={`Select ${datedCellLabel(cell,true)} epoch ${offset+index+1}`} onChange={event=>setTargets(old=>event.target.checked?[...new Set([...old,epoch.epoch_uuid])]:old.filter(uuid=>uuid!==epoch.epoch_uuid))}/>
      <button disabled={disabled||page.loading} aria-current={focused===epoch.epoch_uuid?'true':undefined} onClick={()=>onFocus(epoch.epoch_uuid,epoch)} aria-label={`Inspect ${datedCellLabel(cell,true)} epoch ${offset+index+1}`}>
        <strong>Epoch {offset+index+1} <time>{epoch.start_time?.split(/[T ]/)[1]?.slice(0,8)||''}</time></strong>
        <span>{humanize(epoch.protocol_name?.split('.').at(-1))||'Protocol not recorded'}</span>
        <small className="cell-tree-meta"><span>{humanize(epoch.cell_type)||'Type not recorded'}{epoch.curation&&` · ${epoch.curation.included===false?'Excluded':'Included'}`}</span>{tags.count>0&&<span className="cell-tree-tags" title={tags.title} aria-label={`${tags.count} tags. ${tags.title}`}><MessageCircle size={12} aria-hidden="true"/>{tags.count}</span>}</small>
      </button>
    </div>;})}
    {page.data&&<div className="pagination"><button aria-label={`Previous epochs for ${datedCellLabel(cell,true)}`} disabled={disabled||page.loading||!offset} onClick={()=>setOffset(Math.max(0,offset-60))}>Previous</button><span>{page.data.total?offset+1:0}–{Math.min(offset+60,page.data.total)} of {number(page.data.total)}</span><button aria-label={`Next epochs for ${datedCellLabel(cell,true)}`} disabled={disabled||page.loading||offset+60>=page.data.total} onClick={()=>setOffset(offset+60)}>Next</button></div>}
  </Status>;
}
function CellBranch({cell,dateOpen,...props}){
  const [open,setOpen]=useState(false);
  return <details className="cell-tree-cell" open={open} onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary><strong>{cell.label||cell.cell_label||'Unlabeled cell'}</strong><small>{number(cell.epochs)} epochs · {humanize(cell.cell_type)||'Type not recorded'}</small></summary>
    {dateOpen&&open&&<CellEpochs cell={cell} {...props}/>}
  </details>;
}
function DateBranch({group,...props}){
  const [open,setOpen]=useState(false);
  return <details className="cell-tree-date" open={open} onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary><strong>{group.date}</strong><small>{number(group.cells.length)} cells · {number(group.epochs)} epochs</small></summary>
    {group.cells.map(cell=><CellBranch key={cell.cell_uuid} cell={cell} dateOpen={open} {...props}/>)}
  </details>;
}
export default function InspectionCellTree({cells,...props}){
  const dates=useMemo(()=>inspectionDates(cells),[cells]);
  return <div className="inspection-cell-tree" aria-label="All matching dates, cells and epochs"><p>{number(cells?.length)} cells · {number(dates.length)} dates. Expand a date, then a cell to browse epochs.</p>{dates.map(group=><DateBranch key={group.date} group={group} {...props}/>)}</div>;
}
