import {fieldCategory} from './components/predicateEditor.js';
// Display aliases only: saved predicates retain the exact indexed field IDs.
const common=[
 ['protocol','Protocol ID'],
 ['annotations/epoch/tags','Epoch tags'],['annotations/cell/tags','Cell tags'],
 ['annotations/effective/tags','Effective tags'],['annotations/authors','Tag authors'],
 ['metadata/experiment/attributes/purpose','Experiment Purpose'],
 ['metadata/experiment/purpose','Experiment Purpose'],
 ['metadata/experiment/notes','Experiment Notes'],
 ['metadata/cell/comment','Cell Comment'],['metadata/cell/comments','Cell Comments'],
 ['metadata/cell/attributes/comment','Cell Comment'],
 ['metadata/cell/notes','Cell Notes'],['metadata/cell/label','Cell Label'],
 ['properties/bathTemperature','Bath Temperature'],
 ['metadata/epoch/comment','Epoch Comment'],['metadata/epoch/comments','Epoch Comments'],
 ['metadata/epoch/attributes/comment','Epoch Comment'],['metadata/epoch/notes','Epoch Notes'],
 ['metadata/epoch/keywords','Epoch Keywords'],['metadata/epoch/attributes/keywords','Epoch Keywords'],
 ['metadata/cell/keywords','Cell Keywords'],['metadata/cell/attributes/keywords','Cell Keywords'],
 ['metadata/experiment/keywords','Experiment Keywords'],['metadata/experiment/attributes/keywords','Experiment Keywords'],
 ['date','Recording Date'],['metadata/experiment/start_time','Experiment Date'],
 ['metadata/cell/start_time','Cell Start'],['metadata/epoch/start_time','Epoch Start'],
];
export const predicateFieldLabel=field=>common.find(([id])=>id===field?.id)?.[1]||field?.label||field?.id;
export const predicateFieldGroup=field=>common.some(([id])=>id===field.id)?'Common fields':fieldCategory(field);
export const predicateFieldRank=field=>{const index=common.findIndex(([id])=>id===field.id);return index<0?1000:index;};
export function predicateFieldSearch(field){return `${predicateFieldLabel(field)} ${field.label} ${field.id} ${field.path} ${fieldCategory(field)} ${field.id==='protocol'?'protocol id acquisition protocol':''} ${field.id.endsWith('/notes')?'notes comments':''} ${(field.examples||[]).join(' ')}`.toLowerCase();}
