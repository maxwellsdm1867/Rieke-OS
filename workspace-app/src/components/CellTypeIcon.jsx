import NeuronIcon from './NeuronIcon.jsx';
import {cellTypePresentation} from '../cell-qc/cellTypes.js';

/** Decorative glyph: the adjacent recorded label remains the accessible identity. */
export default function CellTypeIcon({type,size=19,strokeWidth=1.7,style,...props}) {
  const {shape,color,polarity}=cellTypePresentation(type);
  const shared={width:size,height:size,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth,strokeLinecap:'round',strokeLinejoin:'round','aria-hidden':true,style:{color,...style},...props};
  if(shape==='generic' || shape==='ganglion' || shape==='midget')return <NeuronIcon size={size} compact={shape==='midget'} polarity={polarity} {...shared}/>;
  return <svg {...shared}>
    {shape==='amacrine'?<>
      <ellipse cx="12" cy="7" rx="2.6" ry="2.5"/>
      <circle cx="12" cy="7" r=".65" fill="currentColor" stroke="none"/>
      <path d="M12 9.5c-.2.7.2 1.3 0 2M12 11.5c-1.9 1.1-3.5 1.5-5.6 1.4S3.6 14 1.8 14.4M6.4 12.9c-.8 1.3-1.1 2.6-2.5 3.5M9.3 12.5c.1 1.8-1 3.3-2.3 4.5M12 11.5c1.7 1.3 3.5 1.4 5.3 1.6s3 1.4 4.9 1.8M17.3 13.1c.7 1.3 1.1 2.6 2.6 3.5M14.4 12.8c-.1 1.7 1.2 3.1 2.5 4.7M12 11.5c-.6 2.5.5 4.7-.3 7"/>
    </>:shape==='horizontal'?<>
      <ellipse cx="12" cy="14" rx="2.8" ry="2.3"/>
      <circle cx="12" cy="14" r=".65" fill="currentColor" stroke="none"/>
      <path d="M9.6 12.8C8 11.4 6.7 10 4.3 10S2.6 8.9 1.5 8.4M5.8 10.2 5 7.5M5.1 8.1 3.5 7M9.6 12.8C7 13.1 4.8 13.3 2 12.2M3.5 12.7l-1 1.6M14.4 12.8c1.6-1.4 3-3 5.2-3.1S21.3 8.5 22 8M18.1 10.1l.2-2.8M18.2 8.1l-1.5-1M14.4 12.8c2.6.4 4.8.2 7.6-1M20 12.5l1.4 1.6"/>
    </>:shape==='bipolar'?<>
      <path d="M11.8 6c-.1-1.5-1.5-2.3-3-2.7S7.2 2.1 7 1.5M8.8 3.3l-2 .3M11.8 6c.9-1.5 2.3-1.9 3.3-2.2s1.1-1.3 1.6-1.8M13.6 4.5l-.3-2M15.1 3.8l2 .3"/>
      <path d="M11.8 6c.15.7-.15 1.3 0 2"/>
      <ellipse cx="11.8" cy="10.5" rx="2.3" ry="2.5"/>
      <circle cx="11.8" cy="10.5" r=".65" fill="currentColor" stroke="none"/>
      <path d={polarity==='off'?"M11.8 13c.6 1-.4 2 .2 3":polarity==='on'?"M11.8 13c.8 2-.5 4.8.2 7":"M11.8 13c.7 1.5-.5 3.4.2 5"}/>
      <g transform={`translate(0 ${polarity==='off'?-4:polarity==='on'?0:-2})`}>
        <path d="M12 20c-1.4.5-2.3 1.2-4.5 1M10 20.9l-.2 1.6M12 20c1.1.6 2.4.7 4.5.2M14.6 20.5l.7 1.5"/>
        <path d="M12 20c-.5.8-1 1.5-1.1 2.4M12 20c.5.8 1 1.5 1.1 2.4"/>
      </g>
    </>:<>
      {shape==='cone'?<path d="M11.2 2.2Q12 .9 12.8 2.2L15 6.7Q15.7 8 14.2 8H9.8Q8.3 8 9 6.7ZM9.5 8v2c0 1 1 1.5 2.5 1.5s2.5-.5 2.5-1.5V8M10.4 5h3.2"/>:<path d="M10 9V3.5a2 2 0 0 1 4 0V9ZM10 4.5h4M10 7h4M10.5 9v2.5M13.5 9v2.5"/>}
      <path d="M12 11.5c-1.8 0-3 1.3-3 3s1.2 3 3 3 3-1.3 3-3-1.2-3-3-3ZM12 17.5V20"/>
      {shape==='cone'?<path d="M12 20c-2 0-3.5 1-4 2h8c-.5-1-2-2-4-2Z"/>:<circle cx="12" cy="21" r="1.3"/>}
      <circle cx="12" cy="14.5" r=".65" fill="currentColor" stroke="none"/>
    </>}
  </svg>;
}
