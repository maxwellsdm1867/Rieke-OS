import {lazy,Suspense,useCallback,useRef,useState} from 'react';
const ColumnTree=lazy(()=>import('./ColumnTree.jsx'));
import HierarchyTree from './HierarchyTree.jsx';
import './PagedTree.css';

// Both presentations share exact scope and bounded server pages.
export default function PagedTree(props){
  const [preferredView,setView]=useState(props.initialNavigation?.treeView||'tree');
  // A compact inspection sidebar must never restore a saved column layout.
  const view=props.presentation||preferredView;
  const remembered=useRef({hierarchyNavigation:props.initialNavigation?.hierarchyNavigation||null,columnNavigation:props.initialNavigation?.columnNavigation||props.initialNavigation||null});
  const callbacks=useRef(props);callbacks.current=props;
  const remember=useCallback(navigation=>{remembered.current[view==='tree'?'hierarchyNavigation':'columnNavigation']=navigation;callbacks.current.onNavigationChange?.({...remembered.current,treeView:view});},[view]);
  function changeView(next){setView(next);callbacks.current.onNavigationChange?.({...remembered.current,treeView:next});}
  return <div className="tree-view-workspace">{!props.presentation&&<div className="tree-view-switch" role="group" aria-label="Tree presentation"><button aria-pressed={view==='tree'} className={view==='tree'?'active':''} onClick={()=>changeView('tree')}>Expandable tree</button><button aria-pressed={view==='columns'} className={view==='columns'?'active':''} onClick={()=>changeView('columns')}>Columns</button></div>}{view==='tree'?<HierarchyTree {...props} initialNavigation={remembered.current.hierarchyNavigation} onNavigationChange={remember}/>:<Suspense fallback={<div className="pt-page-heading" role="status">Loading column view…</div>}><ColumnTree {...props} initialNavigation={remembered.current.columnNavigation} onNavigationChange={remember}/></Suspense>}</div>;
}
