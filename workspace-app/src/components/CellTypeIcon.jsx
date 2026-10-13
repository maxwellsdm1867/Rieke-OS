import UnknownCellDrawing from './UnknownCellDrawing.jsx';
import NeuronIcon from './NeuronIcon.jsx';
import {cellTypePresentation} from '../cell-qc/cellTypes.js';

/** Decorative schematic; adjacent recorded text remains the accessible identity. */
export default function CellTypeIcon({type,size=19,strokeWidth=1.7,style,...props}) {
  const {shape,color,polarity,variant}=cellTypePresentation(type);
  const shared={width:size,height:size,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth,strokeLinecap:'round',strokeLinejoin:'round','aria-hidden':true,style:{color,...style},...props};
  if(shape==='generic')return <svg {...shared} viewBox="1.25 0 21.5 21.5"><UnknownCellDrawing/></svg>;
  if(shape==='ganglion' || shape==='midget')return <NeuronIcon size={size} compact={shape==='midget'} parasol={shape==='ganglion' && Boolean(polarity)} somaOffset={-.75} polarity={polarity} {...shared}/>;
  return <svg {...shared}>
    {shape==='bistratified'?<>
      <path d="M12 13.75C11.4 12 12.8 9 12 5M12 5c-1.5-.8-2.9-.5-4.5-1.3M9 4.1 8.7 2.6M12 5c1.5-.9 3-.6 4.7-1.5M15 4.1l.3-1.7M12 10c-2-1.2-4.5-.5-7-1.7M7.8 9l-.4-1.8M5 8.3l-1.7.2M12 10c2-1.4 4.8-.7 7-2M16 9l.6-2M19 8l1.5.2"/>
      <path d="M12 13.75c-1.8 0-3 1.2-3 2.8s1.3 2.8 3 2.8 3-1.2 3-2.8-1.2-2.8-3-2.8ZM12 19.35c-.2 2.25.7 2.75 2.2 2.75H22"/>
      <circle cx="12" cy="16.55" r=".65" fill="currentColor" stroke="none"/>
    </>:shape==='amacrine'?<AmacrineGlyph variant={variant}/>:shape==='horizontal'?<>
      <ellipse cx="12" cy="14" rx="2.8" ry="2.3"/>
      <circle cx="12" cy="14" r=".65" fill="currentColor" stroke="none"/>
      <path d="M9.6 12.8C8 11.4 6.7 10 4.3 10S2.6 8.9 1.5 8.4M5.8 10.2 5 7.5M5.1 8.1 3.5 7M9.6 12.8C7 13.1 4.8 13.3 2 12.2M3.5 12.7l-1 1.6M14.4 12.8c1.6-1.4 3-3 5.2-3.1S21.3 8.5 22 8M18.1 10.1l.2-2.8M18.2 8.1l-1.5-1M14.4 12.8c2.6.4 4.8.2 7.6-1M20 12.5l1.4 1.6"/>
    </>:shape==='bipolar'?<BipolarGlyph polarity={polarity} variant={variant}/>:<PhotoreceptorGlyph shape={shape}/>}
  </svg>;
}

function BipolarGlyph({polarity,variant}) {
  const arborScale=variant==='midget'?.7:variant==='diffuse'?1.45:1;
  return <>
    {variant==='midget'?<path d="M11.8 6c-.3-1.3.5-2 0-3M11.8 3c-.8-.8-1.6-.5-2.1-1.3M11.8 3c.8-.8 1.7-.6 2.2-1.5"/>:
      <g transform={`translate(${11.8*(1-arborScale)} 0) scale(${arborScale} 1)`}>
        <path d="M11.8 6c-.1-1.5-1.5-2.3-3-2.7S7.2 2.1 7 1.5M8.8 3.3l-2 .3M11.8 6c.9-1.5 2.3-1.9 3.3-2.2s1.1-1.3 1.6-1.8M13.6 4.5l-.3-2M15.1 3.8l2 .3"/>
        {variant==='rod' && <path d="M11.8 6c-.7-1.2-.8-2.6-1.3-3.5"/>}
      </g>}
    <path d="M11.8 6c.15.7-.15 1.3 0 2"/>
    <ellipse cx="11.8" cy="10.5" rx="2.3" ry="2.5"/>
    <circle cx="11.8" cy="10.5" r=".65" fill="currentColor" stroke="none"/>
    <path d={polarity==='off'?"M11.8 13c.6 1-.4 2 .2 3":polarity==='on'?"M11.8 13c.8 2-.5 4.8.2 7":"M11.8 13c.7 1.5-.5 3.4.2 5"}/>
    {variant==='rod'?<>
      <path d="M12 20c-1.2.2-2.3-.7-3.8-.3M10.2 20l-.5 1.8M12 20c1.2-.1 2.2.7 3.5.5M13.6 20.4l.1 1.6"/>
      <path strokeWidth="2.1" d="m7.9 19.8.6-.1m.8 2.2.7-.1m5.2-1.3.6-.1m-2.4 1.8.6-.1"/>
    </>:<g transform={`translate(${12*(1-arborScale)} ${polarity==='off'?-4:polarity==='on'?0:-2}) scale(${arborScale} 1)`}>
      <path d="M12 20c-1.4.5-2.3 1.2-4.5 1M10 20.9l-.2 1.6M12 20c1.1.6 2.4.7 4.5.2M14.6 20.5l.7 1.5"/>
      <path d="M12 20c-.5.8-1 1.5-1.1 2.4M12 20c.5.8 1 1.5 1.1 2.4"/>
    </g>}
  </>;
}

function AmacrineGlyph({variant}) {
  // Side-view shorthand of the broad, shallow arbor; radial geometry is not shown.
  if(variant==='starburst')return <>
    <ellipse cx="12" cy="7" rx="2.6" ry="2.5"/>
    <circle cx="12" cy="7" r=".65" fill="currentColor" stroke="none"/>
    <path d="M12 9.5c-.3 1.2.4 2.2 0 3.5M12 13c-2.1.7-3.7 1.7-6 1.6S3 14 1.5 14.4M6 14.6c-1.1 1.2-2.6 1.3-4.1 1.6M8.8 14c-1 2.2-2.7 2.7-4.4 3.5M12 13c1.8.8 3.6 1.3 5.7 1.2s3 .4 4.7.1M17.7 14.2c1 1.3 2.4 1.4 3.8 1.7M15 13.8c.6 1.9 2.2 2.8 4.2 3.4"/>
  </>;
  return <>
    <ellipse cx="12" cy={variant==='aii'?4.5:7} rx="2.6" ry="2.5"/>
    <circle cx="12" cy={variant==='aii'?4.5:7} r=".65" fill="currentColor" stroke="none"/>
    {variant==='aii'?<>
      <path d="M12 7c-.5 3 .5 6 0 9M12 9c-1.3.4-2 1.3-3.6 1.2M12 10.5c1.3.4 2.1.9 3.8.7M12 15c-1.7 2-3.4 2.3-5.7 3.8M9.2 17.3l-.4 3M12 15c1.3 2 3.3 2.6 5.8 3.8M15.1 17.7l.5 3M12 16l-.3 5.2"/>
      <ellipse cx="7.2" cy="10.2" rx="1.4" ry="1"/><ellipse cx="17" cy="11.2" rx="1.4" ry="1"/>
    </>:variant==='a17'?<>
      <path d="M10.6 9.2C8.5 11 8 15 1.8 17M11.6 9.5C9.8 13 11 16.5 6.5 20M12.5 9.5C14 13 13.5 17 17.5 20M13.4 9.2c2.5 2.3 2.6 6 8.8 7.8"/>
      <g fill="currentColor" stroke="none"><circle cx="7.2" cy="13.7" r="1.05"/><circle cx="3.9" cy="16.2" r="1.05"/><circle cx="9.5" cy="16.3" r="1.05"/><circle cx="14.8" cy="17.1" r="1.05"/><circle cx="16.8" cy="13.6" r="1.05"/><circle cx="20" cy="16" r="1.05"/></g>
    </>:<path d="M12 9.5c-.2.7.2 1.3 0 2M12 11.5c-1.9 1.1-3.5 1.5-5.6 1.4S3.6 14 1.8 14.4M6.4 12.9c-.8 1.3-1.1 2.6-2.5 3.5M9.3 12.5c.1 1.8-1 3.3-2.3 4.5M12 11.5c1.7 1.3 3.5 1.4 5.3 1.6s3 1.4 4.9 1.8M17.3 13.1c.7 1.3 1.1 2.6 2.6 3.5M14.4 12.8c-.1 1.7 1.2 3.1 2.5 4.7M12 11.5c-.6 2.5.5 4.7-.3 7"/>}
  </>;
}

function PhotoreceptorGlyph({shape}) {
  return <>
    {shape==='cone'?<path d="M11.2 2.2Q12 .9 12.8 2.2L15 6.7Q15.7 8 14.2 8H9.8Q8.3 8 9 6.7ZM9.5 8v2c0 1 1 1.5 2.5 1.5s2.5-.5 2.5-1.5V8M10.4 5h3.2"/>:shape==='rod'?<path d="M10 9V3.5a2 2 0 0 1 4 0V9ZM10 4.5h4M10 7h4M10.5 9v2.5M13.5 9v2.5"/>:<path d="M12 1.8c-2.3 0-2.6 2.1-2.6 4.1s.3 3.6 2.6 3.6 2.6-1.6 2.6-3.6-.3-4.1-2.6-4.1ZM9.7 4.2h4.6M9.4 6.7h5.2M12 9.5v2"/>}
    <path d="M12 11.5c-1.8 0-3 1.3-3 3s1.2 3 3 3 3-1.3 3-3-1.2-3-3-3ZM12 17.5V20"/>
    {shape==='cone'?<path d="M12 20c-2 0-3.5 1-4 2h8c-.5-1-2-2-4-2Z"/>:shape==='rod'?<circle cx="12" cy="21" r="1.3"/>:<path d="M9.5 21c1.5.5 3.5.5 5 0"/>}
    <circle cx="12" cy="14.5" r=".65" fill="currentColor" stroke="none"/>
  </>;
}
