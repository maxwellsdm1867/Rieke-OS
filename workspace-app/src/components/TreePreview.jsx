import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, ChevronRight, CornerDownRight, FolderOpen, GitBranch, Home, List, Search, X } from 'lucide-react';
import { duration, number } from '../api.js';
import './TreePreview.css';
import {datedCellLabel} from '../recordingIdentity.js';
import {branchLabel,branchTooltip,componentLabel,componentValue,epochLeafLabel,readableField} from '../treeBranchPresentation.js';

export const treeNodeKey = node => String(node.key ?? JSON.stringify([node.missing===true,node.value]));
const cells = node => node.cell_count == null ? '—' : number(node.cell_count);

export default function TreePreview({tree,path=[],onPathChange,onSelectEpoch,loading=false,showHeading=true}) {
  const [picker,setPicker]=useState(false),[offset,setOffset]=useState(0),[groupLimits,setGroupLimits]=useState({});
  const columnsRef=useRef(null);
  const columns=[];
  let current=tree;
  const lineage=[];
  for(let depth=0;current;depth++) {
    columns.push({node:current,depth});
    const selected=current.children?.find(child=>treeNodeKey(child)===path[depth]);
    if(!selected)break;
    lineage.push(selected);current=selected;
  }
  const active=columns.at(-1)?.node;
  const pathKey=JSON.stringify(path);
  useEffect(()=>{setPicker(false);setOffset(0);},[pathKey,tree]);
  useEffect(()=>{const el=columnsRef.current;if(el)el.scrollTo({left:el.scrollWidth,behavior:'smooth'});},[columns.length]);
  function choose(node,depth) {
    const key=treeNodeKey(node);
    onPathChange(path[depth]===key?path.slice(0,depth):[...path.slice(0,depth),key]);
  }
  const leaves=active?.epochs || (active?.epoch_uuids || []).map(id=>({epoch_uuid:id}));
  return <section className="tree-preview" aria-label="Interactive tree preview">
    {showHeading&&<header className="tp-heading"><h2><GitBranch size={19}/> Tree preview</h2><span className="tp-live">{loading?'Updating…':'Grouping preview'}</span></header>}
    <div className="tp-total"><strong>{number(tree?.count)} epochs</strong><span>{cells(tree || {})} cells</span><span>{duration(tree?.duration_seconds)} recorded</span><small>Full scope · grouping does not change inclusion</small></div>
    <nav className="tp-path" aria-label="Preview group path">
      <button onClick={()=>onPathChange([])} title="Collapse to the root"><Home size={14}/> All matching epochs</button>
      {lineage.map((node,index)=><span key={`${index}:${treeNodeKey(node)}`}><ChevronRight size={12}/><button onClick={()=>onPathChange(path.slice(0,index+1))} title={branchTooltip(node,columns[index]?.node.field)}>{branchLabel(node,columns[index]?.node.field)}</button></span>)}
      {path.length>0&&<button className="tp-back" onClick={()=>onPathChange(path.slice(0,-1))}><ArrowLeft size={13}/> Back one level</button>}
    </nav>
    <div className="tp-columns" ref={columnsRef}>
      {columns.map(({node,depth})=>{
        const children=node.children || [];
        const terminal=!!node.epochs || !!node.epoch_uuids;
        const limitKey=`${depth}:${treeNodeKey(node)}`;
        const visibleGroups=groupLimits[limitKey] || 60;
        const combined=children.some(child=>child.components?.length);
        return <div className={`tp-column ${terminal?'tp-terminal':''} ${combined?'tp-combined-column':''}`} key={`${depth}:${treeNodeKey(node)}`}>
          <div className="tp-level-heading"><span>{depth+1}</span><div><strong title={node.field}>{terminal?'Epochs':readableField(node.field_label,node.field)}</strong><small>{terminal?`${number(node.count)} epochs in this group`:`${number(children.length)} ${children.length===1?'branch':'branches'}`}</small></div></div>
          <div className="tp-column-content">{children.slice(0,visibleGroups).map(child=>{
            const selected=path[depth]===treeNodeKey(child);
            const share=node.count>0?Math.max(0,Math.min(100,child.count/node.count*100)):0;
            return <button className={`tp-branch ${selected?'selected':''}`} key={treeNodeKey(child)} onClick={()=>choose(child,depth)}
              aria-expanded={selected} title={branchTooltip(child,node.field)}>
              <div className="tp-branch-title"><FolderOpen size={15}/><strong>{child.components?.length?'Matching combination':branchLabel(child,node.field)}</strong><ChevronRight size={14}/></div>
              {child.components?.length>0&&<dl className="tp-combination">{child.components.map((part,index)=><div key={part.field} className={`joint-color-${index%3}`}><dt title={part.field}>{componentLabel(part)}</dt><dd>{componentValue(part)}</dd></div>)}</dl>}
              <div className="tp-branch-counts"><span><b>{number(child.count)}</b> epochs</span><span>{cells(child)} cells</span></div>
              <div className="tp-distribution" aria-hidden="true"><span style={{width:`${share}%`}}/></div>
              <small>{share.toFixed(share<10?1:0)}% of parent · {duration(child.duration_seconds)}</small>
            </button>;
          })}
          {children.length>visibleGroups&&<button className="tp-more-groups" onClick={()=>setGroupLimits(previous=>({...previous,[limitKey]:visibleGroups+60}))}>Show {Math.min(60,children.length-visibleGroups)} more groups</button>}
          {terminal&&<div className="tp-terminal-content"><div className="tp-terminal-summary"><List size={23}/><strong>{number(node.count)} epochs</strong><span>{cells(node)} cells · {duration(node.duration_seconds)}</span><p>This is a final group in your current layout. Add another metadata field to split it further.</p></div>
            {!picker?<button className="primary tp-inspect" disabled={!leaves?.length} onClick={()=>setPicker(true)}><Search size={15}/> Inspect epochs</button>:<div className="tp-epoch-picker">
              <div className="tp-picker-heading"><strong>Choose an epoch</strong><button onClick={()=>setPicker(false)} aria-label="Close epoch list"><X size={13}/></button></div>
              <p>Choosing an epoch opens its raw recording.</p>
              {(leaves || []).slice(offset,offset+60).map(epoch=><button className="tp-epoch" key={epoch.epoch_uuid} title={epoch.epoch_uuid} onClick={()=>onSelectEpoch(epoch.epoch_uuid)}>
                <strong>{epoch.cell_label ? `${datedCellLabel(epoch)} · `:''}{epochLeafLabel(epoch)}</strong>
                <span>{epoch.date || epoch.start_time?.split(' ')[0] || 'Date not recorded'}<ArrowRight size={13}/></span>
              </button>)}
              <div className="tp-pagination"><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-60))} aria-label="Previous preview epochs"><ArrowLeft size={14}/></button><span>{offset+1}–{Math.min(offset+60,leaves.length)} / {number(leaves.length)}</span><button disabled={offset+60>=leaves.length} onClick={()=>setOffset(offset+60)} aria-label="Next preview epochs"><ArrowRight size={14}/></button></div>
            </div>}
          </div>}
          {!children.length&&!terminal&&<p className="tp-no-groups">No recorded groups in this scope.</p>}
          </div>
        </div>;
      })}
      {active?.children?.length>0&&<div className="tp-prompt"><CornerDownRight size={27}/><strong>Open a branch</strong><p>See the next grouping level and how its epochs are distributed.</p></div>}
    </div>
    <footer className="tp-footer"><span>{number(tree?.count)} epochs stay in the full scope.</span><span>Click a selected branch to collapse it. Raw traces load only when you inspect an epoch.</span></footer>
  </section>;
}
