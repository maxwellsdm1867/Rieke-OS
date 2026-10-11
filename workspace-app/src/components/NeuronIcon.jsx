/** Schematic retinal side view; ON arbors lie closer to the ganglion soma. */
export default function NeuronIcon({size=19,strokeWidth=1.7,compact=false,polarity,...props}){
  const offset=polarity==='off'?0:4;
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    <path d={`M12 14.5C11.4 12.8 12.7 ${9+offset} 12 ${7+offset}`}/>
    <g transform={`translate(${compact?4:0} ${offset}) scale(${compact?2/3:1} 1)`}>
      <path d="M12 7C10 5.7 8.5 6.3 6.4 5.2S3.5 5.3 1.5 4.7M6.4 5.2C5.1 4.2 5.8 3.3 4.8 2.5M9.1 6C9.8 4.8 8.9 4 8 3.5M12 7c1.4-1.8 3.2-1.1 5.1-2s3.5-.4 5.4-1.2M17.1 5c.4-1-.5-1.7-.3-2.8M20.2 4.3l1.1-1.8M14.5 5.9c-.7-1 .2-2 .7-2.7"/>
    </g>
    <path d="M12 14.5c-1.8 0-3 1.2-3 2.8s1.3 2.8 3 2.8 3-1.2 3-2.8-1.2-2.8-3-2.8ZM12 20.1c-.2 1.5.7 2 2.2 2H22"/>
    <circle cx="12" cy="17.3" r=".65" fill="currentColor" stroke="none"/>
  </svg>;
}
