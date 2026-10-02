import React,{useState,useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import PagedTree from './src/components/PagedTree.jsx';
import MetadataPanel from './src/components/MetadataPanel.jsx';
import {api} from './src/api.js';
import './src/styles.css';

function Experiment(){
 const [config,setConfig]=useState(null),[selected,setSelected]=useState(null),[epoch,setEpoch]=useState(null),[error,setError]=useState('');
 useEffect(()=>{fetch('/bench-config').then(r=>r.json()).then(setConfig).catch(e=>setError(e.message));},[]);
 useEffect(()=>{if(!selected)return;setEpoch(null);api(`/epochs/${selected}`).then(setEpoch).catch(e=>setError(e.message));},[selected]);
 if(!config)return <p role="status">Loading fixture configuration…</p>;
 return <main style={{height:'100vh',padding:20,display:'flex',gap:20}}>
  <section style={{width:700,height:700,display:'flex',flexDirection:'column'}}><h1>Disco everyday action experiment</h1><p>{config.epochs.toLocaleString()} synthetic epochs · source {config.source_head}</p>
   <PagedTree presentation="tree" protocolId={config.protocol_uuid} splits="cell,block" revision={0} design onSelectEpoch={setSelected}/>
  </section>
  <div style={{width:420,height:700}}><MetadataPanel epoch={epoch} catalog={{data:config.catalog||{fields:[]}}} onClose={()=>{}}/><output id="detail-ready" data-epoch={epoch?.epoch_uuid||''}/></div>
  {error&&<p role="alert">{error}</p>}
 </main>;
}
createRoot(document.getElementById('root')).render(<Experiment/>);
