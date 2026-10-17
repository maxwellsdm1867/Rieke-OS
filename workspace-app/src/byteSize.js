// One byte-size presentation for the whole app: decimal SI units (1 KB = 1000 B,
// as Finder reports), one decimal for KB/MB and two for GB/TB. Fixed decimals
// keep whole values explicit ("305.0 MB"), so the same bytes read identically on
// Project overview, protocol overviews, Data stores, Project files and imports.
const UNITS=[['KB',1e3,1],['MB',1e6,1],['GB',1e9,2],['TB',1e12,2]];

export function formatBytes(bytes,{unavailable='—'}={}){
  if(typeof bytes!=='number'||!Number.isFinite(bytes)||bytes<0)return unavailable;
  if(bytes<1000)return `${Math.round(bytes)} B`;
  for(let index=0;index<UNITS.length;index++){
    const [unit,scale,digits]=UNITS[index],text=(bytes/scale).toFixed(digits);
    // Roll over when rounding reaches the next unit (999.96 MB -> 1.00 GB).
    if(Number(text)<1000||index===UNITS.length-1)return `${text} ${unit}`;
  }
}
