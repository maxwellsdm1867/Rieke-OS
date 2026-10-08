// Download only from an explicit export action, never from receipt restoration.
// Download cancellation does not undo the saved scientific export.
export function downloadExport(receipt, documentObject=globalThis.document) {
  if(!receipt?.download_url||!documentObject?.createElement)return false;
  let link;
  try {
    link=documentObject.createElement('a');
    link.href=receipt.download_url;
    link.download='';
    link.hidden=true;
    documentObject.body.appendChild(link);
    link.click();
    return true;
  } catch {
    // The receipt's visible download link remains available for a manual retry.
    return false;
  } finally {link?.remove();}
}
