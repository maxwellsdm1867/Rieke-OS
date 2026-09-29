import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';
class RenderBoundary extends React.Component {
  state = {error:null};
  static getDerivedStateFromError(error) {return {error};}
  render() {if(this.state.error) return <div className="error" role="alert"><div><h2>The workspace could not render</h2><p>{this.state.error.message}</p><button onClick={()=>window.location.reload()}>Reload workspace</button></div></div>;return this.props.children;}
}
createRoot(document.getElementById('root')).render(<React.StrictMode><RenderBoundary><App/></RenderBoundary></React.StrictMode>);
