import {useId,useState,useMemo} from 'react';
import {ChevronDown} from 'lucide-react';
import NeuronIcon from './NeuronIcon.jsx';
import {CellList} from './Common.jsx';
import {distinctCells} from '../cellTypes.js';
import {number} from '../api.js';
import './CellListSection.css';

export default function CellListSection({cells,title='Cells',open,onOpenChange,toggleRef,panelRef,filters,actions,onInspect,onQC}) {
  const id=useId(),[localOpen,setLocalOpen]=useState(false),expanded=open??localOpen;
  const rows=useMemo(()=>distinctCells(cells),[cells]);
  return <section className="section cell-list-section" ref={panelRef} aria-label={title}>
    <div className="section-heading"><h2><button ref={toggleRef} className="cell-list-toggle" aria-expanded={expanded} aria-controls={id} onClick={()=>onOpenChange?onOpenChange(!expanded):setLocalOpen(!expanded)}>
      <ChevronDown size={16} aria-hidden="true"/><NeuronIcon size={16}/>{title}<span className="cell-list-count">{number(rows.length)}</span><small>{expanded?'Hide':'Show'} cell list</small>
    </button></h2>{filters}{actions}</div>
    <div id={id} hidden={!expanded}><CellList cells={rows} onInspect={onInspect} onQC={onQC}/>{!rows.length&&<div className="cell-list-empty">No cells in this scope.</div>}</div>
  </section>;
}
