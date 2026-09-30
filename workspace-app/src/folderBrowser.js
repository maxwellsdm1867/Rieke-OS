// Choosing a path never creates, restores, moves or modifies a folder.
export function absoluteFolderPath(value){
  if(typeof value!=='string'||!value.startsWith('/')||value.includes('\0'))throw new Error('Choose an absolute folder path on this computer.');
  return value.replace(/\/+$/,'')||'/';
}
export function folderParentPath(value){
  const path=absoluteFolderPath(value);
  if(path==='/')return null;
  return path.slice(0,path.lastIndexOf('/'))||'/';
}
export function folderBasename(value){
  return value?absoluteFolderPath(value).split('/').pop():'';
}
export function newFolderPath(parent,name){
  const directory=absoluteFolderPath(parent);
  if(typeof name!=='string'||!name.trim()||['.','..'].includes(name.trim())||/[\\/\x00-\x1f]/.test(name)||name.trim().length>255)throw new Error('Use a folder name without slashes, dots alone or control characters.');
  return `${directory==='/'?'':directory}/${name.trim()}`;
}
export function shouldCreateNewFolder(listing){
  return !listing.empty||listing.requested_exists===false;
}
export async function readFolderListing({directory='',offset=0,request}){
  if(directory)absoluteFolderPath(directory);
  if(!Number.isSafeInteger(offset)||offset<0)throw new Error('Folder page is invalid.');
  const query=new URLSearchParams({offset:String(offset),limit:'200'});
  if(directory)query.set('directory',directory);
  const data=await request(`/folders?${query}`);
  if(!data||typeof data!=='object'||!Array.isArray(data.folders)||!Array.isArray(data.locations)||typeof data.has_more!=='boolean'||!Number.isSafeInteger(data.offset)||data.offset<0||!Number.isSafeInteger(data.total)||data.total<0)throw new Error('The folder browser returned an incomplete listing.');
  if(Object.hasOwn(data,'empty')&&typeof data.empty!=='boolean')throw new Error('The folder browser returned invalid empty-folder information.');
  if(Object.hasOwn(data,'requested_exists')&&typeof data.requested_exists!=='boolean')throw new Error('The folder browser returned invalid requested-folder information.');
  if(Object.hasOwn(data,'truncated')&&typeof data.truncated!=='boolean')throw new Error('The folder browser returned invalid listing-limit information.');
  absoluteFolderPath(data.directory);
  if(data.parent!==null)absoluteFolderPath(data.parent);
  for(const folder of [...data.folders,...data.locations]){
    if(!folder||typeof folder.name!=='string'||!folder.name)throw new Error('The folder browser returned an invalid folder.');
    absoluteFolderPath(folder.path);
  }
  if(data.has_more&&(!Number.isSafeInteger(data.next_offset)||data.next_offset<=data.offset))throw new Error('The next folder page is unavailable.');
  return data;
}
async function chooseFolderDialog(options){
  const {openFolderBrowserDialog}=await import('./components/FolderBrowserDialog.jsx');
  return openFolderBrowserDialog(options);
}
export async function browseFolder({directory='',purpose='existing',title,suggestedName,parentDirectory,
  nativeBridge=globalThis.window?.riekeDesktop||null,chooseDialog=chooseFolderDialog,request}={}){
  if(!['existing','new','create'].includes(purpose))throw new Error('Choose an existing folder, an empty project folder or a new destination.');
  let initialDirectory='';
  // An unfinished text field is only a navigation hint, not a selection.
  if(directory){try{initialDirectory=absoluteFolderPath(directory);}catch{}}
  const initialName=purpose!=='existing'?(folderBasename(initialDirectory)||suggestedName||'New project'):undefined;
  if(purpose==='new')initialDirectory=parentDirectory?absoluteFolderPath(parentDirectory):(initialDirectory?folderParentPath(initialDirectory)||'/':'');
  if(typeof nativeBridge?.chooseProjectFolder==='function'){
    let selected;
    try{selected=await nativeBridge.chooseProjectFolder();}
    catch(error){throw new Error(`The folder chooser could not open: ${error.message||'Try again.'}`);}
    if(selected===null||selected===undefined)return null;
    const nativePath=absoluteFolderPath(selected);
    if(purpose==='existing')return nativePath;
    initialDirectory=nativePath;
  }
  const selection=await chooseDialog({purpose,title:title||(purpose!=='existing'?'Choose a project folder':'Choose a folder'),initialDirectory,initialName,request});
  if(selection===null||selection===undefined)return null;
  if(purpose==='new'||purpose==='create'&&typeof selection==='object'){
    if(!selection||typeof selection!=='object')throw new Error('Choose a parent folder and name the new folder.');
    return newFolderPath(selection.directory,selection.name);
  }
  return absoluteFolderPath(selection);
}
