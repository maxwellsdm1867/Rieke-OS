/** Independent research probe. No launch, API start or production mutation on import.
 * Caller supplies immutable asset/fixture identity, selectors and an independent
 * authority witness. Never infer authority merely from enabled controls.
 */
export function canonicalJSON(value) {
  if (Array.isArray(value)) return value.map(canonicalJSON);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, canonicalJSON(value[k])]));
  return value;
}
export function canonicalRequest(request, namespace) {
  const url = new URL(request.url());
  url.searchParams.sort(); // Stable sort preserves order of repeated values.
  let body = request.postData();
  if (body !== null) { try { body = canonicalJSON(JSON.parse(body)); } catch {} }
  return {namespace, method: request.method(), url: url.href, body};
}
export function attachLedger(page, namespace) {
  const entries = [], byRequest = new WeakMap();
  const onRequest = request => {
    if (!new URL(request.url()).pathname.startsWith('/api/')) return;
    const row = {...canonicalRequest(request, namespace), startAt: Date.now(), pending: true};
    entries.push(row); byRequest.set(request, row);
  };
  const onResponse = async response => {
    const row = byRequest.get(response.request()); if (!row) return;
    row.headersAt = Date.now(); row.status = response.status();
    row.serviceMs = response.headers()['x-owned-bench-service-ms'];
    try {
      const bytes = await response.body(); row.bodyAt = Date.now(); row.bytes = bytes.length;
      // Exact authority/POST evidence stays private. Analysis/hashing follows timing.
      try { row.json = JSON.parse(bytes.toString()); } catch {}
    } catch (error) { row.readError = String(error); }
  };
  const onFinished = request => {const row = byRequest.get(request); if (row) {row.finishedAt = Date.now(); row.pending = false;}};
  const onFailed = request => {const row = byRequest.get(request); if (row) {row.failedAt = Date.now(); row.failure = request.failure(); row.pending = false;}};
  page.on('request', onRequest); page.on('response', onResponse); page.on('requestfinished', onFinished); page.on('requestfailed', onFailed);
  return {entries, detach() {page.off('request', onRequest); page.off('response', onResponse); page.off('requestfinished', onFinished); page.off('requestfailed', onFailed);}};
}
export function temporalRequestSets(entries, intentAt, gateAt, tailAt, relevant) {
  const scoped = entries.filter(relevant);
  return {
    startedBeforeGate: scoped.filter(r => r.startAt >= intentAt && r.startAt <= gateAt),
    completedBeforeGate: scoped.filter(r => r.startAt >= intentAt && (r.bodyAt ?? Infinity) <= gateAt),
    pendingAtGate: scoped.filter(r => r.startAt <= gateAt && (r.bodyAt ?? r.failedAt ?? Infinity) > gateAt),
    completedInTail: scoped.filter(r => (r.bodyAt ?? Infinity) > gateAt && r.bodyAt <= tailAt),
    pendingAfterTail: scoped.filter(r => r.startAt <= tailAt && (r.bodyAt ?? r.failedAt ?? Infinity) > tailAt),
    interpretation: 'Temporal sets, not a causal critical-path or exclusive CPU attribution proof.'
  };
}
/** config requires a scoped surface and readiness selector. validateAuthority
 * must check independently pinned scope and rendered evidence, including valid
 * retained-cache witnesses; do not force a refetch to satisfy this callback.
 */
export async function observeTransition({page, locator, ledger, config, validateAuthority, relevantRequest}) {
  if (!config.surfaceSelector || !config.readySelector || typeof validateAuthority !== 'function' || typeof relevantRequest !== 'function') throw Error('Explicit surface/readiness/authority/request-scope contract required');
  const token = `${Date.now()}-${Math.random()}`;
  await page.evaluate(({token, config}) => {
    const q = selector => selector ? document.querySelector(selector) : null;
    const visible = n => !!n && n.getBoundingClientRect().width > 0 && n.getBoundingClientRect().height > 0 && getComputedStyle(n).visibility !== 'hidden';
    const snapshot = () => {
      const pane = q(config.layoutPaneSelector), selected = q(config.selectedSelector);
      const rect = pane?.getBoundingClientRect();
      return {scrollTop: pane?.scrollTop, scrollLeft: pane?.scrollLeft, scrollHeight: pane?.scrollHeight, clientHeight: pane?.clientHeight,
        pane: rect ? [rect.x, rect.y, rect.width, rect.height].map(x => Math.round(x * 10) / 10) : null,
        selected: selected?.getAttribute('aria-label'), selectedVisible: visible(selected),
        selectedValue: selected?.value,
        expanded: (config.expandedSelectors || []).map(selector => [...document.querySelectorAll(selector)].map(n => ({label:n.getAttribute('aria-label') || n.textContent?.trim(),open:n.open}))),
        stream: q('[aria-label="Response stream"]')?.value};
    };
    window.__comparisonProbe = {token, config, frames:0, absent:0, loading:0, inert:0, usable:0, authority:null, relevantPending:true, snapshot};
    function tick() {
      const p = window.__comparisonProbe; if (p.token !== token || p.stop) return;
      const now = performance.timeOrigin + performance.now(); p.frames++;
      if (!p.intentAt) {requestAnimationFrame(tick); return;}
      const surface = q(config.surfaceSelector), ready = q(config.readySelector);
      const absent = !visible(surface), loading = visible(q(config.loadingSelector));
      const inert = !!surface && (surface.closest('[inert]') !== null || visible(q(config.inertSelector)));
      // A body-portaled dialog can obscure an otherwise active scoped surface.
      const foreignModal = [...document.querySelectorAll(config.blockingModalSelector || 'dialog[open]')].some(n => visible(n) && n !== surface && !n.contains(surface));
      const usable = !absent && !loading && !inert && !foreignModal && visible(ready) && (!config.readyText || ready.textContent.includes(config.readyText));
      if (absent) p.absent++; if (loading) p.loading++; if (inert || foreignModal) p.inert++; if (usable) p.usable++;
      p.usefulStreak = usable ? (p.usefulStreak || 0) + 1 : 0;
      if (p.usefulStreak >= 2 && !p.contentAt) {p.contentAt=now;p.contentSnapshot=snapshot();}
      if (usable && p.authority?.valid && !p.authorityAt) p.authorityAt=now;
      const state=snapshot(), signature=JSON.stringify(state);
      if (usable && p.authority?.valid && !p.relevantPending) {
        if (signature !== p.signature) {p.signature=signature;p.stableSince=now;p.stableFrames=0;}
        p.stableFrames=(p.stableFrames||0)+1;
        if (now-p.stableSince>=100 && p.stableFrames>=4 && !p.settledAt) {p.settledAt=now;p.settledSnapshot=state;}
      } else {p.stableSince=now;p.stableFrames=0;p.signature=null;}
      if (p.settledAt && now-p.settledAt>=500 && !p.persistenceAt) {p.persistenceAt=now;p.persistenceSnapshot=state;p.persistenceAuthorityValid=!!p.authority?.valid;p.persistenceUsable=usable;p.persistencePending=p.relevantPending;p.statePersisted=JSON.stringify(p.settledSnapshot)===signature;}
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }, {token,config});
  await locator.evaluate(el => {window.__comparisonProbe.intentAt=performance.timeOrigin+performance.now();el.click();});
  const limit = Date.now() + (config.timeoutMs || 15000);
  let witness, observation;
  while (Date.now() < limit) {
    witness = await validateAuthority({page, entries:ledger.entries, config});
    const relevantPending=ledger.entries.some(row => relevantRequest(row) && row.pending);
    observation = await page.evaluate(({token,witness,relevantPending}) => {
      const p=window.__comparisonProbe; if (p.token!==token) throw Error('Probe superseded');
      p.authority=witness;p.relevantPending=relevantPending;
      const {snapshot,...value}=p;return value;
    },{token,witness,relevantPending});
    if (observation.persistenceAt) break;
    await new Promise(resolve=>setTimeout(resolve,20));
  }
  await page.evaluate(token => {if(window.__comparisonProbe?.token===token)window.__comparisonProbe.stop=true;},token);
  if (!observation?.persistenceAt) return {qualified:false,reason:'Authority or stable layout/persistence gate timed out',observation,witness};
  // Persistence sampling already exceeds the 300 ms tail; classify exactly,
  // rather than extend an implicit attribution window.
  const gate=observation.authorityAt, tail=gate+300;
  return {qualified:!!observation.persistenceAuthorityValid && observation.persistenceUsable && !observation.persistencePending && observation.statePersisted,observation,witness,requests:temporalRequestSets(ledger.entries,observation.intentAt,gate,tail,relevantRequest),
    limits:'DOM/RAF and validated authority observation; no compositor or exclusive causal work claim. Settled snapshots must be asserted against scenario expectations.'};
}
