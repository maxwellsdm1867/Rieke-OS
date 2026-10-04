import {useCallback,useRef,useState,useLayoutEffect} from 'react';
import ColumnTree from './ColumnTree.jsx';
import {createTreeSelectionReader} from '../treeSelectionReader.js';
import {mergeEpochSelection,toggleEpochSelection} from '../epochSelection.js';
import HierarchyTree from './HierarchyTree.jsx';
import './PagedTree.css';

const selectionReader=createTreeSelectionReader();

// Both presentations share exact scope and bounded server pages.
export default function PagedTree(props){
  const [preferredView,setView]=useState(props.initialNavigation?.treeView||'tree');
  // A compact inspection sidebar must never restore a saved column layout.
  const view=props.presentation||preferredView;
  const remembered=useRef({hierarchyNavigation:props.initialNavigation?.hierarchyNavigation||null,columnNavigation:props.initialNavigation?.columnNavigation||props.initialNavigation||null});
  const callbacks=useRef(props);callbacks.current=props;
  const remember=useCallback(navigation=>{remembered.current[view==='tree'?'hierarchyNavigation':'columnNavigation']=navigation;callbacks.current.onNavigationChange?.({...remembered.current,treeView:view});},[view]);
  function changeView(next){setView(next);callbacks.current.onNavigationChange?.({...remembered.current,treeView:next});}
  const anchor=useRef(null),selectionRequest=useRef(null);
  const [selectionError,setSelectionError]=useState('');
  const scopeKey=JSON.stringify({protocolId:props.protocolId,predicate:props.predicate,filters:props.filters||{},splits:props.splits||'',revision:props.revision??0,readContext:props.readContext,expectedRevision:props.expectedRevision,active:props.active,actionsDisabled:props.actionsDisabled});
  const selectionScope=useRef(null),generation=useRef(0);
  // Invalidate at commit, before a deferred request can publish into the new
  // scope. Cleanup also covers unmount and React's StrictMode effect replay.
  useLayoutEffect(()=>{
    selectionScope.current=scopeKey;generation.current++;
    selectionRequest.current?.abort();anchor.current=null;setSelectionError('');
    return()=>{generation.current++;selectionScope.current=null;selectionRequest.current?.abort();};
  },[scopeKey]);
  async function selectCell(item,field,revision){
    if(props.active===false||props.actionsDisabled||selectionScope.current!==scopeKey||field?.field!=='cell'||!props.onSelectCell)return;
    const request=new AbortController();selectionRequest.current?.abort();selectionRequest.current=request;
    const token=generation.current,isCurrent=()=>token===generation.current&&selectionRequest.current===request&&!request.signal.aborted;
    setSelectionError('');anchor.current=null;
    try{
      const epoch=await selectionReader.firstEpoch(props,{path:item.path,revision,signal:request.signal});
      if(isCurrent()&&epoch)callbacks.current.onSelectCell?.(item.value,epoch);
    }catch(error){if(isCurrent()&&error.name!=='AbortError')setSelectionError(error.message);}
  }
  async function selectEpoch(uuid,item,event,page,index){
    if(props.active===false||props.actionsDisabled||selectionScope.current!==scopeKey)return;
    selectionRequest.current?.abort();setSelectionError('');
    props.onSelectEpoch?.(uuid,item);
    if(!props.setSelectedEpochs||!event)return;
    const target={uuid,index:page.offset+index,path:page.path,revision:page.revision};
    const token=generation.current;
    let request;
    const isCurrent=()=>token===generation.current&&(!request||(selectionRequest.current===request&&!request.signal.aborted));
    try{
      if(event.shiftKey&&anchor.current){
        if(JSON.stringify(anchor.current.path)!==JSON.stringify(page.path)||anchor.current.revision!==page.revision)throw new Error('Select a range within one tree branch, or use Command/Ctrl-click across branches.');
        const lo=Math.min(anchor.current.index,target.index),hi=Math.max(anchor.current.index,target.index);
        request=new AbortController();selectionRequest.current=request;
        const before=JSON.stringify(props.selectedEpochs||[]);
        const result=selectionReader.rangeEpochIds(props,{page,firstIndex:lo,lastIndex:hi,signal:request.signal});
        // Same-page selection remains synchronous; fetched ranges await transport.
        const ids=Array.isArray(result)?result:await result;
        if(!isCurrent())return;
        if(JSON.stringify(callbacks.current.selectedEpochs||[])!==before)throw new Error('Selection changed while loading. Select the range again.');
        callbacks.current.setSelectedEpochs?.(mergeEpochSelection(callbacks.current.selectedEpochs||[],ids));
      }else{
        anchor.current=target;
        if(event.metaKey||event.ctrlKey)props.setSelectedEpochs(toggleEpochSelection(props.selectedEpochs||[],uuid));else if(!props.readContext)props.setSelectedEpochs([]);
      }
    }catch(error){if(isCurrent()&&error.name!=='AbortError')setSelectionError(error.message);}
  }
  const selectionProps={onSelectEpoch:selectEpoch,onSelectBranch:props.design?undefined:selectCell};
  return <div className="tree-view-workspace">{selectionError&&<p role="alert">{selectionError}</p>}{!props.presentation&&<div className="tree-view-switch" role="group" aria-label="Tree presentation"><button aria-pressed={view==='tree'} className={view==='tree'?'active':''} onClick={()=>changeView('tree')}>Expandable tree</button><button aria-pressed={view==='columns'} className={view==='columns'?'active':''} onClick={()=>changeView('columns')}>Columns</button></div>}{view==='tree'?<HierarchyTree {...props} {...selectionProps} initialNavigation={remembered.current.hierarchyNavigation} onNavigationChange={remember}/>:<ColumnTree {...props} {...selectionProps} initialNavigation={remembered.current.columnNavigation} onNavigationChange={remember}/>}</div>;
}
