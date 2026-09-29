import { Database, Download, Link2 } from 'lucide-react';
import { number, time } from '../api.js';
import './EpochConnections.css';

export default function EpochConnections({epoch, protocolName, contextLabel='Query'}) {
  const exports = epoch.exports || [];
  return <section className="epoch-connections" aria-label="Epoch database and export connections">
    <div className="ec-catalog"><Database size={15}/><span>Main database <strong>{epoch.catalog_ref?.database || 'Project catalog'}</strong></span><span className="ec-protocol">{contextLabel}: {protocolName}</span></div>
    {exports.length ? <details><summary><Link2 size={14}/> In {number(exports.length)} saved {exports.length===1?'export':'exports'}</summary>
      <div className="ec-export-list">{exports.map(item=><div key={item.dataset_uuid}>
        <div><strong>{item.name || 'Saved export'}</strong><small>{time(item.created_at)} · {item.dataset_uuid.slice(0,8)}</small>
          {item.metadata_matches===false&&<small>Saved with a different metadata revision</small>}</div>
        {item.download_url&&<a href={item.download_url} download title="Download the immutable export containing this epoch"><Download size={14}/> Export</a>}
      </div>)}</div>
    </details>:<div className="ec-empty"><Link2 size={14}/> No saved export in this project</div>}
  </section>;
}
