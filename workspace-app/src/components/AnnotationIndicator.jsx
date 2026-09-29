import {MessageCircle} from 'lucide-react';
import {annotationIndicator} from '../annotationTags.js';
import './AnnotationTags.css';
export default function AnnotationIndicator({epoch}){
 const summary=annotationIndicator(epoch);
 return summary.count>0?<span className="annotation-row-summary" title={summary.title} aria-label={`${summary.cell} inherited cell tags, ${summary.epoch} direct epoch tags, ${summary.dataset} dataset tags`}><MessageCircle size={11}/>{summary.count}</span>:null;
}
