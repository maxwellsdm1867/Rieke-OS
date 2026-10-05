import {recordedCellType,isUnclassifiedType} from '../cellTypes.js';

// A complete receipt owns the scope. Never count epoch rows, reused labels,
// or an incomplete cell list as distinct recorded cells.
export function incomingCellTypes(cells,expectedCount){
  if(!Array.isArray(cells)||!Number.isSafeInteger(expectedCount)||expectedCount<0)return null;
  const identities=new Map(),groups=new Map();
  for(const cell of cells){
    if(typeof cell?.cell_uuid!=='string'||!cell.cell_uuid)return null;
    const recorded=recordedCellType(cell),type=isUnclassifiedType(recorded)?'Unclassified':recorded.trim();
    if(identities.has(cell.cell_uuid)&&identities.get(cell.cell_uuid)!==type)return null;
    identities.set(cell.cell_uuid,type);
  }
  if(identities.size!==expectedCount)return null;
  for(const type of identities.values())groups.set(type,(groups.get(type)||0)+1);
  return [...groups].map(([type,count])=>({type,count})).sort((a,b)=>Number(a.type==='Unclassified')-Number(b.type==='Unclassified')||b.count-a.count||a.type.localeCompare(b.type));
}
