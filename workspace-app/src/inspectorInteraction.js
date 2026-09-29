export const PANE_GUTTER=7;
export function resourceForPath(resource,path){
  return resource.path===path?resource:{...resource,data:null,error:null,loading:true};
}
export function inspectorPaneSizes(width,requested={},treeOpen=true,metadataOpen=false){
  const available=Math.max(360,Number.isFinite(width)?width:1100);
  const overlay=metadataOpen&&available<990;
  const centerMin=300;
  const metadataMax=Math.max(240,Math.min(560,overlay?available-48:available-centerMin-(treeOpen?190+PANE_GUTTER:0)-PANE_GUTTER));
  const metadata=Math.round(Math.max(240,Math.min(metadataMax,Number.isFinite(requested.metadata)?requested.metadata:320)));
  const treeMax=Math.max(180,Math.min(560,available-centerMin-(metadataOpen&&!overlay?metadata+PANE_GUTTER:0)-PANE_GUTTER));
  const tree=Math.round(Math.max(180,Math.min(treeMax,Number.isFinite(requested.tree)?requested.tree:270)));
  const columns=[...(treeOpen?[`${tree}px`,`${PANE_GUTTER}px`]:[]),'minmax(0,1fr)',...(metadataOpen&&!overlay?[`${PANE_GUTTER}px`,`${metadata}px`]:[])].join(' ');
  return {tree,metadata,treeMax,metadataMax,overlay,columns};
}

// Epoch shortcuts stay in navigation regions; typing and native controls stay local.
export function epochShortcutDirection(event){
  if(event.isComposing||event.nativeEvent?.isComposing||event.defaultPrevented||event.altKey||event.ctrlKey||event.metaKey)return 0;
  if(event.target?.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="combobox"],[role="separator"],[role="dialog"],dialog,[role="listbox"],[role="menu"],[data-epoch-arrows="ignore"]'))return 0;
  if(event.key==='Tab'){
    const navigation=event.target===event.currentTarget||event.target?.closest?.('.epoch-row button,.epoch-leaf,.epoch-navigation,[data-epoch-navigation]');
    return navigation?(event.shiftKey?-1:1):0;
  }
  if(event.shiftKey||!['w','s'].includes(event.key))return 0;
  return event.key==='w'?-1:1;
}

export function nextEpochAction({epochs=[],offset=0,total=0,focused,direction,pageSize=60}){
  if(direction!==-1&&direction!==1)return {kind:'none'};
  const index=epochs.findIndex(epoch=>epoch.epoch_uuid===focused);
  if(index<0)return focused?{kind:'locate',epoch_uuid:focused,direction}:{kind:'none'};
  const next=index+direction;
  if(next>=0&&next<epochs.length)return {kind:'focus',epoch_uuid:epochs[next].epoch_uuid};
  const nextOffset=offset+direction*pageSize;
  if(nextOffset<0||nextOffset>=total)return {kind:'none'};
  return {kind:'page',offset:nextOffset,edge:direction<0?'last':'first'};
}
