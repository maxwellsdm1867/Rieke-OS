import NeuronIcon from './NeuronIcon.jsx';
import {Layers} from 'lucide-react';
export default function SelectionOverview({cell,count}){
  return <div className="selection-overview">{cell?<NeuronIcon size={28}/>:<Layers size={28}/>}<h2>{cell?cell.label||cell.cell_label:`${count} epochs`}</h2><p>{cell?`${cell.date} · ${cell.epochs} matching epochs`:'Selected across the epoch browser'}</p><p>{cell?'Cell details and tags are shown on the right.':'Add tags to this selection in the right panel.'}</p></div>;
}
