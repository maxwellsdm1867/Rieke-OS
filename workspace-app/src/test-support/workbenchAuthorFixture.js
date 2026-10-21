// These component fixtures omit App's provider. Give the outer session owner a
// resolved author; lower frozen/queue probes retain their own test contracts.
export const workbenchAuthorFixture={name:'workbench-owner-author',enforce:'pre',resolveId(source,importer){
 if(importer?.endsWith('/IncomingWorkbench.jsx')&&source.endsWith('/annotations/annotationProfile.js'))return '\0workbench-owner-author';
},load(id){if(id==='\0workbench-owner-author')return "export const useAnnotationProfile=()=>({profileUuid:'fixture-author',loading:false,error:null});";}};
