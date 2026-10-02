import {useTreeGroupTags} from '../components/TreeGroupTags.jsx';
import {useMutationUndo} from '../useMutationUndo.js';
import GroupAnnotationRecovery from '../components/GroupAnnotationRecovery.jsx';
export default function TreeGroupLifecycleHarness({onChange}){
 useMutationUndo('owned-group-project',onChange);
 const groups=useTreeGroupTags({splits:'protocol',onAnnotationsChanged:onChange});
 return <><button onClick={event=>groups.open({path:['b'.repeat(64)],value:'ExpandingSpots',count:1857},{field:'protocol'}, {revision:'a'.repeat(64)},event)}>Open group</button>{groups.dialog}<GroupAnnotationRecovery/></>;
}
