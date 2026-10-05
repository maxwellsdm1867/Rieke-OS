import {useSyncExternalStore} from 'react';
import {mutationUndo} from '../mutationUndo.js';
// Isolate undo availability notifications from the scientific workspace. A tag
// gesture must not rerender all mounted epoch/tree views just to update a button.
export default function UndoControls({onUndo}){
 useSyncExternalStore(mutationUndo.subscribe,mutationUndo.version);
 const state=mutationUndo.view();
 return <><button disabled={!state.count||state.busy||!!state.pending} onClick={onUndo} title="Undo last tag or analysis inclusion edit (Cmd+Z / Ctrl+Z)">Undo edit</button>{state.message&&<span role="status" className="undo-status">{state.message}</span>}</>;
}
