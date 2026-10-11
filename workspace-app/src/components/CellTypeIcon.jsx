import NeuronIcon from './NeuronIcon.jsx';
import {cellTypePresentation} from '../cell-qc/cellTypes.js';

/** Decorative glyph: the adjacent recorded label remains the accessible identity. */
export default function CellTypeIcon({type,size=19,strokeWidth=1.7,style,...props}) {
  const {shape,color,polarity}=cellTypePresentation(type);
  const shared={width:size,height:size,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth,strokeLinecap:'round',strokeLinejoin:'round','aria-hidden':true,style:{color,...style},...props};
  if(shape==='ganglion' || shape==='midget')return <NeuronIcon size={size} compact={shape==='midget'} polarity={polarity} {...shared}/>;
  return <svg {...shared}>
    {shape==='bipolar'?<>
      <path d="M11.8 6c-.1-1.5-1.5-2.3-3-2.7S7.2 2.1 7 1.5M8.8 3.3l-2 .3M11.8 6c.9-1.5 2.3-1.9 3.3-2.2s1.1-1.3 1.6-1.8M13.6 4.5l-.3-2M15.1 3.8l2 .3"/>
      <ellipse cx="11.8" cy="8.5" rx="2.3" ry="2.5"/>
      <circle cx="11.8" cy="8.5" r=".65" fill="currentColor" stroke="none"/>
      <path d={polarity==='off'?"M11.8 11c.8 1.8-.5 3.3.2 5":"M11.8 11c.8 3-.5 6.3.2 9"}/>
      <g transform={`translate(0 ${polarity==='off'?-4:0})`}>
        <path d="M12 20c-1.4.5-2.3 1.2-4.5 1M10 20.9l-.2 1.6M12 20c1.1.6 2.4.7 4.5.2M14.6 20.5l.7 1.5"/>
      </g>
    </>:<>
      {shape==='cone'?<path d="M12 1.5 8.7 8h6.6L12 1.5ZM9.5 8v2c0 1 1 1.5 2.5 1.5s2.5-.5 2.5-1.5V8M10.4 5h3.2"/>:<path d="M10 9V3.5a2 2 0 0 1 4 0V9ZM10 4.5h4M10 7h4M10.5 9v2.5M13.5 9v2.5"/>}
      <path d="M12 11.5c-1.8 0-3 1.3-3 3s1.2 3 3 3 3-1.3 3-3-1.2-3-3-3ZM12 17.5V20"/>
      {shape==='cone'?<path d="M12 20c-2 0-3.5 1-4 2h8c-.5-1-2-2-4-2Z"/>:<circle cx="12" cy="21" r="1.3"/>}
      <circle cx="12" cy="14.5" r=".65" fill="currentColor" stroke="none"/>
    </>}
  </svg>;
}
