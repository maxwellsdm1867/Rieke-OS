/** Compact neuron silhouette, matching the interface's outline icons. */
export default function NeuronIcon({size=19,strokeWidth=1.7,...props}){
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    <path d="M7 8.5 4 6V2M4 6H1M9.5 7 10 3l3-2M10 3 8 1M7 11 3 12l-2 3M3 12l-2-2M9 13l-2 5-3 2M7 18l1 4M12 12l3 3h4l3 3M19 15l3-3M22 18v3M22 18h1"/>
    <path d="M7 8.5c.5-2 3.5-2.2 5-.5 1.5 1.8 1 4-1 5-2 1-4.5-.5-4.5-2.5 0-.8.2-1.4.5-2Z"/>
    <circle cx="9.5" cy="10" r=".65" fill="currentColor" stroke="none"/>
  </svg>;
}
