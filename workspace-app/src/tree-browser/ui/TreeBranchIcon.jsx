import {Folder,FolderOpen} from 'lucide-react';
import CellTypeIcon from '../../components/CellTypeIcon.jsx';

// Only exact identity levels carry a cell symbol. Labels never classify a cell.
export default function TreeBranchIcon({node,field,opened=true}) {
  const identity=!node.components?.length&&(field==='cell'||field==='cell type');
  if(identity){
    const type=node.missing?'Unclassified':field==='cell type'?node.value:node.cell_type;
    return <span className="tree-cell-identity-icon"><CellTypeIcon type={typeof type==='string'?type:'Unclassified'} size={22}/></span>;
  }
  return <span className="tree-group-folder">{opened?<FolderOpen size={15}/>:<Folder size={15}/>}</span>;
}
