export const EXPORT_FORMATS=Object.assign(Object.create(null),{
  'wheeler-sqlite':{label:'Wheeler SQLite database',downloadLabel:'SQLite database',description:'A queryable SQLite database containing the frozen query, epoch metadata, inclusion decisions and H5 references. Query it with Wheeler or another SQLite client; raw recordings remain in the original H5 files.'},
  'epictree-mat':{label:'EpicTree MATLAB bundle',downloadLabel:'MATLAB bundle',description:'The MATLAB bundle contains recordings.mat, an EpicTree launcher, selection mask and the frozen query recipe. Waveforms are read lazily from the original H5 files.'},
  'reference-json':{label:'Reference JSON',downloadLabel:'JSON',description:'The reference package saves the query, filters, inclusion decisions and exact epoch identities. Raw recordings stay in the original H5 files.'},
});
export function initialExportFormat(recipe){
  if(!recipe)return 'wheeler-sqlite';
  // Older export-reuse records without a format represent reference JSON.
  // Preserve an unfamiliar explicit value so the UI requires a deliberate
  // supported choice rather than silently changing its destination.
  return recipe.format || 'reference-json';
}
export function exportFormatLabel(format){return EXPORT_FORMATS[format || 'reference-json']?.label || `Unknown format (${format})`;}
export function exportDownloadLabel(format){return EXPORT_FORMATS[format || 'reference-json']?.downloadLabel || 'Saved artifact';}
export function validExportReceipt(receipt,expectedFormat){
  return !!EXPORT_FORMATS[expectedFormat]&&receipt?.format===expectedFormat&&
    ['dataset_uuid','event_uuid','download_url'].every(key=>typeof receipt[key]==='string'&&receipt[key].trim().length>0)&&
    Number.isSafeInteger(receipt.epoch_count)&&receipt.epoch_count>0;
}
