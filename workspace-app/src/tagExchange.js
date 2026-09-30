export const MAX_TAG_IMPORT_BYTES=8*1024*1024;
export async function readTagDocument(file){
 if(!file||file.size>MAX_TAG_IMPORT_BYTES)throw new Error('Choose a tag JSON file smaller than 8 MB.');
 if(/\.ugm$/i.test(file.name||''))throw new Error('UGM files are not supported. Choose a tag JSON file.');
 let value;try{value=JSON.parse(await file.text());}catch{throw new Error('This file is not valid tag JSON. Choose a tag JSON exported from a compatible source workspace.');}
 if(!value||Array.isArray(value)||typeof value!=='object')throw new Error('A tag file must contain a JSON object with UUID-based tag entries.');
 return value;
}
export function tagExportUrl({format='rieke',scope='project',epoch}){
 if(!['rieke','samarjit'].includes(format))throw new Error('Unsupported tag export format');
 const query=new URLSearchParams({format});
 if(scope!=='project'){
  if(!['cell','epoch'].includes(scope)||!epoch?.[`${scope}_uuid`])throw new Error('Select a cell or epoch before exporting its tags.');
  query.set('target_kind',scope);query.set('target_uuid',epoch[`${scope}_uuid`]);
 }
 return `/api/annotations/export?${query}`;
}
export function tagPreviewSummary(preview){
 const rows=Array.isArray(preview?.entries)?preview.entries:[];
 return {added:preview?.addition_count||0,unchanged:preview?.unchanged_count||0,targets:rows.length,rows};
}
