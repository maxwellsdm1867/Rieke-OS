// Presentation only: grouping still uses the exact registered field identity.
export const COMMON_TREE_FIELDS=['date','cell','group','block','protocol','cell type','group label','block time'];
const labels={date:'Recording date',cell:'Cell',group:'Epoch group',block:'Epoch block',protocol:'Acquisition protocol','cell type':'Cell type','group label':'Epoch group label','block time':'Block start time'};
export const treeFieldLabel=field=>labels[field.id] || field.label || 'Saved metadata field';
export const treeFieldHint=field=>field.grouping_hint || ({
 date:'Separate recording days',cell:'Keep individual cells separate',
 group:'Keep each recorded epoch group separate',block:'Separate acquisition blocks by start time',
 protocol:'Group by the recorded acquisition protocol','cell type':'Group cells by their recorded type',
 'group label':'Combine groups with the same label, such as NBQX5um','block time':'Group by the exact recorded block start time',
}[field.id] || 'Split by this recorded metadata value');
export function treeFieldExamples(field) {
 return (field.examples||[]).slice(0,3).map(value=>{
   let text=String(value);
   try{const decoded=JSON.parse(text);if(typeof decoded==='string')text=decoded;}catch{}
   if(field.id==='protocol')text=text.split('.').at(-1).replace(/([a-z])([A-Z])/g,'$1 $2').replace(/Cur Inject/g,'current injection');
   if(field.id==='cell type')text=text.replace(/^RGC\\/,'');
   return text;
 }).join(' · ');
}
export function treeFieldMatches(field,{order=[],category='Common',suggestions=[],search=''}) {
 const query=search.trim().toLocaleLowerCase();
 if(order.includes(field.id))return false;
 if(category!=='All' && !(category==='Common'?COMMON_TREE_FIELDS.includes(field.id):category==='Suggested'?suggestions.includes(field.id):field.category===category))return false;
 return !query || [treeFieldLabel(field),treeFieldHint(field),field.id,field.path,field.category,treeFieldExamples(field)].join(' ').toLocaleLowerCase().includes(query);
}

export function groupingFieldRank(field) {
 const role=field.grouping_role;
 return role==='technical'?5:field.varying&&role==='primary'?0:field.varying&&role==='alternative'?1:field.varying?2:role==='primary'?3:4;
}
