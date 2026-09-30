import { useState } from 'react';
import {
  ArrowLeft, ArrowRight, ArrowUp, Check, ChevronRight, Code2, Database,
  File, FileJson, Folder, FolderOpen, Link2, LockKeyhole,
  RefreshCw, ShieldCheck, Upload, AlertTriangle, Copy, BookOpen, Download, Settings2, Activity,
} from 'lucide-react';
import { useResource, number } from '../api.js';
import { Badge, Empty, Status } from './Common.jsx';
import './ProjectFiles.css';

function fileSize(bytes) {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024, unit = 0;
  while (value >= 1024 && unit < units.length - 1) {value /= 1024; unit++;}
  return `${value.toLocaleString(undefined, {maximumFractionDigits: 1})} ${units[unit]}`;
}
function modified(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}
function entryIcon(entry) {
  if (entry.type === 'restricted' || (entry.type === 'directory' && entry.browseable === false)) return LockKeyhole;
  if (entry.type === 'directory') return Folder;
  if (entry.type === 'symlink') return Link2;
  if (entry.name.endsWith('.json')) return FileJson;
  return File;
}
const fileGroups = [
  {label:'Recording files',description:'Original recordings stored here',icon:Activity,paths:['raw-uploads']},
  {label:'Imports',description:'Imported recording metadata',icon:Upload,paths:['imports']},
  {label:'Exports',description:'Saved results ready to use',icon:Download,paths:['exports']},
  {label:'Saved work',description:'Protocols and saved queries',icon:BookOpen,paths:['protocols','query-snapshots']},
  {label:'App storage',description:'Database, backups and logs',icon:Settings2,paths:['database','backups','logs','cache']},
];
const sectionNames={'raw-uploads':'Recording files',imports:'Imports',exports:'Exports',protocols:'Protocols','query-snapshots':'Saved queries',database:'Database',backups:'Backups',logs:'Activity logs',cache:'Temporary indexes'};

export default function ProjectFiles({onStores,onFolder}) {
  const [path, setPath] = useState('');
  const [offset, setOffset] = useState(0);
  const [copied,setCopied]=useState(false),[copyError,setCopyError]=useState('');
  const storage = useResource('/storage');
  const files = useResource(`/files?${new URLSearchParams({path, offset, limit:100})}`);
  function openDirectory(nextPath) {setPath(nextPath || ''); setOffset(0);}
  function refresh() {storage.reload(); files.reload();}
  const data = storage.data;
  const listing = files.data;
  const segments = path.split('/').filter(Boolean);
  const activeSection = data?.sections?.find(section => path === section.path || path.startsWith(`${section.path}/`));
  const group=fileGroups.find(item=>item.paths.includes(activeSection?.key));
  async function copyLocation(){try{await navigator.clipboard.writeText(data.root);setCopied(true);setCopyError('');}catch{setCopyError('Select the folder path and copy it manually.');}}
  const database = data?.database || {};
  const state = String(database.status || 'Unknown');
  const connected = /^(connected|running|ready|available|healthy)$/i.test(state);
  return <div className="page project-files">
    <div className="page-heading">
      <div><div className="eyebrow">PROJECT STORAGE</div><h1>Project files</h1>
        <p>Browse your recordings, saved work and exports. Everything here belongs to this project.</p>
      </div>
      <div className="button-row">{onStores && <button onClick={onStores}><Activity size={16}/> Manage recordings</button>}<button onClick={refresh} disabled={storage.loading || files.loading}>
        <RefreshCw size={16} className={storage.loading || files.loading ? 'spin' : ''}/> Refresh
      </button></div>
    </div>
    <Status {...storage} retry={storage.reload}>{data && <>
      <section className="pf-location" aria-label="Storage locations">
        <button type="button" className="pf-root-icon" onClick={onFolder} disabled={!onFolder}
          aria-label="Project folder actions" title="Project folder actions · open, close or share a project"
          aria-haspopup="dialog"><FolderOpen size={23}/></button>
        <div className="pf-location-main"><span className="pf-field-label">PROJECT FOLDER</span>
          <strong className="pf-path">{data.root}</strong>
          <details className="pf-code-location"><summary><Code2 size={13}/> App code location · separate from project data</summary>
            <p className="pf-path">{data.code_root}</p>
          </details>
        </div>
        <button className="pf-copy-path" onClick={copyLocation}>{copied?<Check size={14}/>:<Copy size={14}/>} {copied?'Copied':'Copy path'}</button>
      </section>

      {copyError&&<p className="pf-copy-error" role="status">{copyError}</p>}
      <nav className="pf-category-grid" aria-label="Project file categories">
        {fileGroups.map(item=>{const Icon=item.icon;const target=item.paths.find(key=>data.sections?.some(section=>section.key===key));return <button key={item.label} disabled={!target} className={group===item?'active':''} aria-current={group===item?'location':undefined} onClick={()=>openDirectory(target)}><span className="pf-category-icon"><Icon size={20}/></span><strong>{item.label}</strong><small>{item.description}</small></button>;})}
      </nav>
      {group&&group.paths.length>1&&<nav className="pf-sections" aria-label={`${group.label} folders`}>{group.paths.filter(key=>data.sections?.some(section=>section.key===key)).map(key=><button key={key} className={activeSection?.key===key?'active':''} aria-current={activeSection?.key===key?'location':undefined} onClick={()=>openDirectory(key)}><Folder size={14}/>{sectionNames[key]}</button>)}</nav>}
    </>}</Status>

    <section className="section pf-browser" aria-label="Managed project files">
      <div className="pf-browser-toolbar">
        <button className="icon-button" disabled={!path || files.loading} aria-label="Up one directory"
          onClick={()=>openDirectory(listing?.parent ?? segments.slice(0,-1).join('/'))}><ArrowUp size={17}/></button>
        <nav className="pf-breadcrumb" aria-label="Directory breadcrumb">
          <button onClick={()=>openDirectory('')} aria-current={!path?'location':undefined}><FolderOpen size={15}/> All files</button>
          {segments.map((segment,index)=><span key={segments.slice(0,index+1).join('/')}><ChevronRight size={13}/>
            <button onClick={()=>openDirectory(segments.slice(0,index+1).join('/'))}
              aria-current={index===segments.length-1?'location':undefined}>{index===0?sectionNames[segment]||segment:segment}</button>
          </span>)}
        </nav>
        <span className="pf-entry-count">{listing ? `${number(listing.total)} items` : ''}</span>
      </div>
      {activeSection && <p className="pf-section-description">{group?.description||activeSection.description}{group?.label==='App storage'?' · These files are managed by the app.':''}</p>}
      <Status {...files} retry={files.reload}>
        {listing && (listing.entries.length ? <div className="pf-table-scroll">
          <table className="pf-file-table"><thead><tr><th scope="col">Name</th><th scope="col">Type</th><th scope="col">Size</th><th scope="col">Modified</th></tr></thead>
            <tbody>{listing.entries.map(entry=>{
              const Icon = entryIcon(entry);
              const browseable = entry.type === 'directory' && entry.browseable !== false;
              const restricted = entry.type === 'restricted' || (entry.type === 'directory' && entry.browseable === false);
              return <tr key={entry.path} className={restricted ? 'pf-restricted' : ''}>
                <td>{browseable ? <button className="pf-directory" onClick={()=>openDirectory(entry.path)}><Icon size={17}/><span>{entry.name}</span><ChevronRight size={14}/></button>
                  : <span className="pf-file-name"><Icon size={17}/><span>{entry.name}</span>{restricted&&<Badge>Managed by database</Badge>}</span>}</td>
                <td>{restricted?'Restricted':entry.type==='directory'?'Folder':entry.type==='symlink'?'Symbolic link':'File'}</td>
                <td className="pf-number">{entry.type==='file'?fileSize(entry.size_bytes):'—'}</td>
                <td><time dateTime={entry.modified_at || undefined}>{modified(entry.modified_at)}</time></td>
              </tr>;
            })}</tbody>
          </table>
        </div> : <Empty title="This folder is empty">New project outputs will appear here when they are created.</Empty>)}
      </Status>
      <div className="pf-file-footer"><span><LockKeyhole size={13}/> View only · your files stay unchanged</span>
        {listing && <div className="pf-pagination"><button disabled={offset===0 || files.loading} aria-label="Previous files page" onClick={()=>setOffset(Math.max(0,offset-100))}><ArrowLeft size={15}/></button>
          <span>{listing.total?offset+1:0}–{Math.min(offset+listing.entries.length,listing.total)} of {number(listing.total)}</span>
          <button disabled={!listing.has_more || files.loading} aria-label="Next files page" onClick={()=>setOffset(offset+100)}><ArrowRight size={15}/></button>
        </div>}
      </div>
    </section>

    {data && <section className="section pf-sources" aria-label="Referenced recordings">
      <div className="section-heading"><div><h2>Recording locations</h2><p>See which recordings are in your project folder and which are linked from elsewhere.</p></div><Badge>{number(data.sources?.length)} sources</Badge></div>
      {(data.sources || []).length ? <div className="pf-source-list">{data.sources.map(source=><div className="pf-source-row" key={source.source_sha256 || source.path}>
        <div className="pf-source-icon"><Link2 size={18}/></div>
        <div className="pf-source-details"><strong>{source.filename}</strong><p className="pf-path">{source.path}</p>
          <details><summary>Source identity</summary><p className="pf-path">SHA-256 · {source.source_sha256}</p></details>
        </div>
        <Badge kind="neutral">{source.location==='managed'?'In project folder':'Linked recording'}</Badge>
        <Badge kind={source.exists===true?'success':source.exists===false?'warning':'neutral'}>{source.exists===true?<Check size={12}/>:<AlertTriangle size={12}/>}{source.exists===true?'Available':source.exists===false?'Missing':'Not checked'}</Badge>
      </div>)}</div> : <Empty title="No recordings registered">Imported recording references will be listed here.</Empty>}
    </section>}
    {data&&<details className="pf-database" aria-label="App storage details"><summary><Database size={18}/><span><strong>App storage details</strong><small>Your project database is managed by Rieke OS.</small></span><ChevronRight className="pf-detail-chevron" size={17}/></summary><div className="pf-database-content"><div className="pf-database-title"><h2>Project database</h2><Badge kind={connected?'success':'neutral'}>{connected&&<Check size={12}/>} {state}</Badge></div><dl className="pf-database-facts"><div><dt>Recordings schema</dt><dd>{database.database||'Not configured'}</dd></div><div><dt>Saved work schema</dt><dd>{database.workspace_database||'Not configured'}</dd></div><div><dt>Database runtime</dt><dd>{database.runtime==='bundled-mysql'?'Bundled private MySQL':database.container||'Not reported'}</dd></div></dl><p className="pf-path">{database.storage_path||'Storage location not reported'}</p><p className="pf-database-note"><ShieldCheck size={14}/><span>Close the project before moving its folder. Database-managed files are protected from changes in this browser.</span></p></div></details>}
  </div>;
}
