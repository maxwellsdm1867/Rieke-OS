export default function ExportSaveLocation(){
  const desktop=!!globalThis.window?.riekeDesktop;
  return <p className="export-save-location">{desktop?<><strong>Save to:</strong> <code>~/Downloads</code>. Export opens a save dialog showing the full path; browse to another folder or change the filename there.</>:<>Export downloads the file to your browser’s download location. Enable “Ask where to save” in your browser to choose another folder.</>}</p>;
}
