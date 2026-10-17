/** Generic cell-count glyph drawn on the same 24-unit grid and stroke as the
 * surrounding lucide line icons. Cell-type schematics stay in CellTypeIcon. */
export default function CellsIcon({size=24,strokeWidth=2,...props}){
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    <circle cx="12" cy="12.5" r="3.5"/>
    <path d="M9.6 10 6 6.5M6 6.5H3M6 6.5V3M14.4 10 18 6.5M18 6.5h3M18 6.5V3M12 16v5M12 21l-3 1.5M12 21l3 1.5"/>
  </svg>;
}
