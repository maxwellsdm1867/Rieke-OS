import {ArrowRight,Database,FolderOpen,Search,Upload} from 'lucide-react';
import './ProjectWelcome.css';

export default function ProjectWelcome({name,directory,loading,error,onRetry,onOverview,onSearch,onStores,onImport,onFolder}){
  return <section className="page project-welcome" aria-labelledby="project-welcome-title">
    <div className="page-heading"><div><div className="eyebrow">YOUR PROJECT</div><h1 id="project-welcome-title">{name}</h1><p>Browse recordings, inspect sources, or add data.</p></div></div>
    <div className="project-welcome-actions">
      <button className="project-welcome-card" disabled={loading} onClick={onOverview}><Database size={24}/><span><strong>Browse recordings</strong><small>Open the project overview and cells</small></span><ArrowRight size={18}/></button>
      <button className="project-welcome-card" disabled={loading} onClick={onSearch}><Search size={24}/><span><strong>Search recordings</strong><small>Find epochs by their recorded metadata</small></span><ArrowRight size={18}/></button>
      <button className="project-welcome-card" disabled={loading} onClick={onStores}><FolderOpen size={24}/><span><strong>Data stores</strong><small>Inspect sources and recording locations</small></span><ArrowRight size={18}/></button>
      <button className="project-welcome-card" disabled={loading} onClick={onImport}><Upload size={24}/><span><strong>Add recordings</strong><small>Import Symphony H5 files</small></span><ArrowRight size={18}/></button>
    </div>
    {loading&&<p className="project-welcome-progress" role="status">Opening project data… You can still choose another project.</p>}
    {error&&<div className="error project-welcome-error" role="alert"><strong>Project data could not open</strong><p>{error}</p><button onClick={onRetry} disabled={loading}>Retry</button></div>}
    <div className="project-welcome-location"><FolderOpen size={16}/><span title={directory}>{directory}</span><button className="quiet" onClick={onFolder}>Project folder</button></div>
  </section>;
}
