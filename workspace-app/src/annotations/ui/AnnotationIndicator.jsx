import {compactAnnotationTags} from '../annotationTags.js';
import './AnnotationTags.css';
export default function AnnotationIndicator({epoch,level='epoch'}){
 const tags=compactAnnotationTags(epoch,level);
 if(!tags.length)return null;
 const title=tags.map(tag=>tag.title).join('\n');
 return <span className="annotation-row-pills" title={title} aria-label={`${level} tags: ${tags.map(tag=>tag.tag).join(', ')}`}>
   {tags.slice(0,2).map(tag=><span key={tag.tag} className={`row-tag-pill tag-color-${tag.color}`} title={tag.title}>{tag.tag}</span>)}
   {tags.length>2&&<span className="row-tag-overflow" title={title}>+{tags.length-2}</span>}
 </span>;
}
