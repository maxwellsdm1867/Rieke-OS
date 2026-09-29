// Calendar dates use the client's local timezone, not UTC date conversion.
export function localExportDate(date=new Date()){
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
export function defaultExportName(label='Search',date=localExportDate()){
  const readable=String(label||'Search').replace(/([a-z])([A-Z])/g,'$1 $2').replace(/Cur Inject/g,'current injection');
  const base=readable.trim().replace(/[_\s·—-]+\d{4}-\d{2}-\d{2}$/,'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^A-Za-z0-9]+/g,'_').replace(/^_+|_+$/g,'').slice(0,109).replace(/_+$/g,'')||'Selection';
  return `${base}_${date}`;
}
