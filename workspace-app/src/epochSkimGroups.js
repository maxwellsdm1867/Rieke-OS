// Keep the server's chronological order; identical display labels never merge UUIDs.
export function epochSkimGroups(epochs=[],offset=0){
  const groups=[];
  epochs.forEach((epoch,index)=>{
    let group=groups.at(-1);
    if(!group||group.date!==epoch.date||group.cellUuid!==epoch.cell_uuid){
      group={key:`${offset+index}:${epoch.cell_uuid}`,date:epoch.date,cellUuid:epoch.cell_uuid,label:epoch.cell_label,epochs:[]};
      groups.push(group);
    }
    group.epochs.push({epoch,position:offset+index+1});
  });
  return groups;
}
