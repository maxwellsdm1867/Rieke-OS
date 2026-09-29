import { useState } from 'react';
import {
  ArrowLeft, ArrowRight, ArrowUp, Check, ChevronRight, Code2, Database,
  File, FileClock, FileJson, Folder, FolderOpen, HardDrive, Link2, LockKeyhole,
  RefreshCw, ShieldCheck, Upload, AlertTriangle,
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
function sectionIcon(section) {
  const key = `${section.key} ${section.label}`.toLowerCase();
  if (/database|db files/.test(key)) return Database;
  if (/log|job/.test(key)) return FileClock;
  if (/upload|raw/.test(key)) return Upload;
  if (/protocol|quer/.test(key)) return FileJson;
  return FolderOpen;
}

export default function ProjectFiles({onStores}) {
  const [path, setPath] = useState('');
  const [offset, setOffset] = useState(0);
  const storage = useResource('/storage');
  const files = useResource(`/files?${new URLSearchParams({path, offset, limit:100})}`);
  function openDirectory(nextPath) {setPath(nextPath || ''); setOffset(0);}
  function refresh() {storage.reload(); files.reload();}
  const data = storage.data;
  const listing = files.data;
  const segments = path.split('/').filter(Boolean);
  const activeSection = data?.sections?.find(section => path === section.path || path.startsWith(`${section.path}/`));
  const database = data?.database || {};
  const state = String(database.status || 'Unknown');
  const connected = /^(connected|running|ready|available|healthy)$/i.test(state);
  return <div className="page project-files">
    <div className="page-heading">
      <div><div className="eyebrow">PROJECT STORAGE</div><h1>Files & database</h1>
        <p>Project data lives in its own directory. Recording references, saved queries and operation history stay together.</p>
      </div>
      <div className="button-row">{onStores && <button onClick={onStores}><Database size={16}/> H5 data stores</button>}<button onClick={refresh} disabled={storage.loading || files.loading}>
        <RefreshCw size={16} className={storage.loading || files.loading ? 'spin' : ''}/> Refresh
      </button></div>
    </div>
    <Status {...storage} retry={storage.reload}>{data && <>
      <section className="pf-location" aria-label="Storage locations">
        <div className="pf-root-icon"><HardDrive size={23}/></div>
        <div className="pf-location-main"><span className="pf-field-label">Managed project directory</span>
          <strong className="pf-path">{data.root}</strong>
          <details className="pf-code-location"><summary><Code2 size={13}/> App code location · separate from project data</summary>
            <p className="pf-path">{data.code_root}</p>
          </details>
        </div>
        <Badge kind="info">Read-only browser</Badge>
      </section>

      <section className="pf-database" aria-label="Database service">
        <div className="pf-database-title"><Database size={19}/><div><h2>Project database</h2>
          <p>{database.adapter || 'Database adapter not reported'} · SQL service</p></div>
          <Badge kind={connected ? 'success' : 'neutral'}>{connected && <Check size={12}/>} {state}</Badge>
        </div>
        <dl className="pf-database-facts">
          <div><dt>Recording schema</dt><dd>{database.database || 'Not configured'}</dd></div>
          <div><dt>Bookkeeping schema</dt><dd>{database.workspace_database || 'Not configured'}</dd></div>
          <div><dt>Database runtime</dt><dd>{database.container || 'Not reported'}</dd></div>
        </dl>
        <p className="pf-database-note"><ShieldCheck size={14}/><span><code>catalog.json</code> describes the connection and project references. The scientific records live in the SQL database.</span></p>
        <details className="pf-database-storage"><summary>Physical database storage</summary>
          <p className="pf-path">{database.storage_path || 'Not reported'}</p>
          <p>Database-managed files are restricted here. The Database files section contains the readable runtime inventory and documentation.</p>
        </details>
      </section>

      <nav className="pf-sections" aria-label="Project data sections">
        {(data.sections || []).map(section => {
          const Icon = sectionIcon(section);
          const active = activeSection?.key === section.key;
          return <button key={section.key} className={active ? 'active' : ''}
            onClick={()=>openDirectory(section.path)} title={section.description} aria-current={active ? 'location' : undefined}>
            <Icon size={16}/><span>{section.label}</span>
          </button>;
        })}
      </nav>
    </>}</Status>

    <section className="section pf-browser" aria-label="Managed project files">
      <div className="pf-browser-toolbar">
        <button className="icon-button" disabled={!path || files.loading} aria-label="Up one directory"
          onClick={()=>openDirectory(listing?.parent ?? segments.slice(0,-1).join('/'))}><ArrowUp size={17}/></button>
        <nav className="pf-breadcrumb" aria-label="Directory breadcrumb">
          <button onClick={()=>openDirectory('')} aria-current={!path?'location':undefined}><FolderOpen size={15}/> Project data</button>
          {segments.map((segment,index)=><span key={segments.slice(0,index+1).join('/')}><ChevronRight size={13}/>
            <button onClick={()=>openDirectory(segments.slice(0,index+1).join('/'))}
              aria-current={index===segments.length-1?'location':undefined}>{segment}</button>
          </span>)}
        </nav>
        <span className="pf-entry-count">{listing ? `${number(listing.total)} items` : ''}</span>
      </div>
      {activeSection && <p className="pf-section-description">{activeSection.description}</p>}
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
      <div className="pf-file-footer"><span><LockKeyhole size={13}/> Browse metadata only · original files remain unchanged</span>
        {listing && <div className="pf-pagination"><button disabled={offset===0 || files.loading} aria-label="Previous files page" onClick={()=>setOffset(Math.max(0,offset-100))}><ArrowLeft size={15}/></button>
          <span>{listing.total?offset+1:0}–{Math.min(offset+listing.entries.length,listing.total)} of {number(listing.total)}</span>
          <button disabled={!listing.has_more || files.loading} aria-label="Next files page" onClick={()=>setOffset(offset+100)}><ArrowRight size={15}/></button>
        </div>}
      </div>
    </section>

    {data && <section className="section pf-sources" aria-label="Referenced recordings">
      <div className="section-heading"><div><h2>Referenced recordings</h2><p>Raw recordings can remain outside the project directory. These are the paths the backend uses.</p></div><Badge>{number(data.sources?.length)} sources</Badge></div>
      {(data.sources || []).length ? <div className="pf-source-list">{data.sources.map(source=><div className="pf-source-row" key={source.source_sha256 || source.path}>
        <div className="pf-source-icon"><Link2 size={18}/></div>
        <div className="pf-source-details"><strong>{source.filename}</strong><p className="pf-path">{source.path}</p>
          <details><summary>Source identity</summary><p className="pf-path">SHA-256 · {source.source_sha256}</p></details>
        </div>
        <Badge kind="neutral">{source.location==='managed'?'Managed source':'External reference'}</Badge>
        <Badge kind={source.exists===true?'success':source.exists===false?'warning':'neutral'}>{source.exists===true?<Check size={12}/>:<AlertTriangle size={12}/>}{source.exists===true?'Available':source.exists===false?'Missing':'Not checked'}</Badge>
      </div>)}</div> : <Empty title="No recordings registered">Imported recording references will be listed here.</Empty>}
    </section>}
  </div>;
}
