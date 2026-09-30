'use strict';
const bridge = window.riekeDesktop;
function display(status) {
  const testing = status.channel === 'unsigned-testing';
  document.getElementById('title').textContent = status.title || 'Rieke OS recovery';
  document.getElementById('message').textContent = status.message || 'Startup has not completed.';
  document.getElementById('detail').textContent = status.detail || '';
  document.getElementById('channel').textContent = 'Unsigned testing';
  document.getElementById('channel').hidden = !testing;
  document.getElementById('gatekeeper').textContent = 'If macOS blocks this unsigned testing app on its first open, choose Open Anyway in System Settings → Privacy & Security.';
  document.getElementById('gatekeeper').hidden = !testing || status.state !== 'Bootstrap' || (status.detail || '').includes('Open Anyway');
  document.getElementById('install').hidden = status.state !== 'Bootstrap';
  document.getElementById('retry').hidden = status.state !== 'Recovery';
  document.getElementById('restore').hidden = status.state !== 'Recovery';
}
bridge.status().then(display); bridge.onStatus(display);
for (const [id, action] of [['install', () => bridge.installAndOpen()], ['retry', () => bridge.retryStartup()], ['restore', () => bridge.restorePreviousVersion()], ['quit', () => bridge.quit()]]) {
  document.getElementById(id).onclick = async event => {
    event.target.disabled = true;
    try { const result = await action(); if (result?.ready === false) document.getElementById('detail').textContent = result.reason || 'The app is waiting for current work to finish.'; } catch (error) { document.getElementById('detail').textContent = error.message; }
    finally { event.target.disabled = false; }
  };
}
