/** Schematic retinal side view; ON arbors lie closer to the ganglion soma. */
export default function NeuronIcon({size=19,strokeWidth=1.7,compact=false,parasol=false,somaOffset=0,polarity,...props}){
  const offset=polarity==='off'?0:4;
  const rx=compact?3.4:parasol?4.44:3,ry=compact?3.3:parasol?3.6:2.8;
  const somaY=17.3+somaOffset;
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    <path d={`M12 ${somaY-ry}C11.4 12.8 12.7 ${9+offset} 12 ${7+offset}`}/>
    {compact?<g transform={`translate(0 ${offset})`}>
      <path d="M12 7c-1.1-1-2-.7-3.2-1.5M8.8 5.5l-.6-1.7M12 7c.9-1.1 2.1-1.2 3.1-2M15.1 5l.6-1.6M10.5 6.2l.2-1.6M13.6 5.9l-.3-1.8"/>
    </g>:<g transform={`translate(0 ${offset})`}>
      <path d="M12 7C10 5.7 8.5 6.3 6.4 5.2S3.5 5.3 1.5 4.7M6.4 5.2C5.1 4.2 5.8 3.3 4.8 2.5M9.1 6C9.8 4.8 8.9 4 8 3.5M12 7c1.4-1.8 3.2-1.1 5.1-2s3.5-.4 5.4-1.2M17.1 5c.4-1-.5-1.7-.3-2.8M20.2 4.3l1.1-1.8M14.5 5.9c-.7-1 .2-2 .7-2.7"/>
      {parasol && <path d="M3.5 4.8l-.7-1.6M5.1 3.4 3.7 3M18.8 4.5l-.3-1.7M21.1 2.9l1.2-.3"/>}
    </g>}
    {compact || parasol?<>
      <ellipse cx="12" cy={somaY} rx={rx} ry={ry}/>
      <path d={`M12 ${somaY+ry}C11.8 21.5 12.7 22.1 14.2 22.1H22`}/>
    </>:<>
      <path transform={`translate(0 ${somaOffset})`} d="M12 14.5c-1.8 0-3 1.2-3 2.8s1.3 2.8 3 2.8 3-1.2 3-2.8-1.2-2.8-3-2.8Z"/>
      <path d={`M12 ${somaY+ry}c-.2 ${1.5-somaOffset} .7 ${2-somaOffset} 2.2 ${2-somaOffset}H22`}/>
    </>}
    <circle cx="12" cy={somaY} r=".65" fill="currentColor" stroke="none"/>
  </svg>;
}
