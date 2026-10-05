export const APPEARANCE_CACHE = 'disco.appearance.v1';
export const THEMES = [
  {id:'system', name:'System', description:'Follows device appearance', icon:'disco', scheme:'light'},
  {id:'light', name:'Light', description:'Light · disco ball', icon:'disco', scheme:'light'},
  {id:'dark', name:'Dark', description:'Dark slate · disco ball', icon:'disco', scheme:'dark'},
  {id:'fred', name:'Fred', description:'Light purple · Rieke emblem', icon:'rieke', scheme:'light'},
];
export function normalizeAppearance(value){
  const theme = THEMES.find(item=>item.id===(value?.theme==='bright'?'light':value?.theme)) || THEMES.find(item=>item.id===(value?.icon==='rieke'?'fred':'light'));
  return {theme:theme.id, icon:theme.icon};
}
export function readCachedAppearance(storage=globalThis.localStorage){
  try{return normalizeAppearance(JSON.parse(storage?.getItem(APPEARANCE_CACHE)||'null'));}
  catch{return normalizeAppearance(null);}
}
export function cacheAppearance(value, storage=globalThis.localStorage){
  try{storage?.setItem(APPEARANCE_CACHE,JSON.stringify(normalizeAppearance(value)));}catch{/* The server preference remains authoritative when browser storage is unavailable. */}
}
export function systemColorScheme(){return globalThis.window?.matchMedia?.('(prefers-color-scheme: dark)');}
export function resolveTheme(value, dark=systemColorScheme()?.matches){
  const preference=normalizeAppearance(value).theme;
  return preference==='system'?(dark?'dark':'light'):preference;
}
export function watchSystemTheme(value, onChange, media=systemColorScheme()){
  if(value.theme!=='system'||!media)return ()=>{};
  const changed=()=>onChange();
  media.addEventListener('change',changed);
  return ()=>media.removeEventListener('change',changed);
}
export function applyTheme(value, documentObject=globalThis.document){
  const theme=THEMES.find(item=>item.id===resolveTheme(value));
  if(!documentObject?.documentElement)return;
  const changed=documentObject.documentElement.dataset.theme!==theme.id;
  documentObject.documentElement.dataset.theme=theme.id;
  documentObject.documentElement.dataset.appearance=normalizeAppearance(value).theme;
  documentObject.documentElement.style.colorScheme=theme.scheme;
  const rail=documentObject.defaultView?.getComputedStyle(documentObject.documentElement).getPropertyValue('--rail').trim();
  if(rail)documentObject.querySelector('meta[name="theme-color"]')?.setAttribute('content',rail);
  if(changed)documentObject.defaultView?.dispatchEvent(new Event('disco:appearance'));
}
