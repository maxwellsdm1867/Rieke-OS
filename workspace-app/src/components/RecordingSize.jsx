import {useResource} from '../api.js';
import {recordingStorage,sizeLabel} from '../protocolOverviewModel.js';
export default function RecordingSize({sourceIds,revision=0}){
  const inventory=useResource('/data-stores',`${revision}:${sourceIds?.join(',')||''}`),size=recordingStorage(inventory.data?.data_stores,sourceIds);
  return <><strong>{!Array.isArray(sourceIds)?'—':inventory.loading?'…':inventory.error?'—':sizeLabel(size.bytes)}</strong><small>{!Array.isArray(sourceIds)?'Source links unavailable':inventory.error?'Size unavailable':size.unknown?`${size.unknown} source sizes unavailable`:`${size.sources} linked H5 ${size.sources===1?'file':'files'}`}</small></>;
}
