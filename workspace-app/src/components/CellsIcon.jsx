import NeuronIcon from './NeuronIcon.jsx';

/** Generic retinal ganglion-cell schematic for overview cell counts. */
export default function CellsIcon({size=24,strokeWidth=1.7,...props}){
  return <NeuronIcon size={size} strokeWidth={strokeWidth} somaOffset={-.75} {...props}/>;
}
