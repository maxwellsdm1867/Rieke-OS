/** Full-App decoupling suite: the real product bootstrap (src/main.jsx) with
 * App's own change wiring, measured by the same raf-aligned click observer,
 * request ledger and two-frame readiness gate as the fixed core.
 *
 * Every product read and write is real; only the launcher project inventory is
 * an owned double (benchmarks/workflow/server.py). No action reads a waveform:
 * the focused epochs carry no streams. Setup steps outside the action clock may
 * still issue the App's own reads, including its preview of epoch 1.
 */

// Inventory order is execution order inside one browser sample.
export const appInventory=[
  ['curation.toggle','focused-1'],['curation.toggle','focused-2'],['curation.toggle','focused-3'],
  ['epoch.step','after-curation'],
  ['tag.add','focused-epoch'],['epoch.step','after-tag'],
  ['view.tab_return','inspect-unchanged'],
  ['focus.return','edit-tree-open-path'],
  ['workbench.merge_all','overview-hold'],['workbench.undo','toast'],
];
export const appLimits=['Real App bootstrap and change wiring in an owned browser; launcher project inventory is an owned double.','DOM/RAF observations, not compositor presentation; production React via the existing Vite API proxy.','Merge-all includes its one-second hold gesture in the elapsed time (hold_ms is recorded separately).','Trailing requests are those started within the fixed quiet window after readiness; periodic background polls are listed by path, not removed.'];
export const TRAILING_MS=1500;
// Periodic App pollers that run regardless of the measured action.
export const BACKGROUND_PATHS=['/api/annotations/scan','/api/jobs','/api/app/updates/check','/api/metadata/status'];

export function appFixtureSource(){
  // The exact product bootstrap: theme, desktop lifecycle, StrictMode, App.
  return "import '/src/main.jsx';\n";
}

/** Browser-side synthetic focus/visibility return; installed outside React. */
export function installFocusReturn(){
  if(document.getElementById('__workflow_focus_return'))return;
  const button=document.createElement('button');
  button.id='__workflow_focus_return';button.textContent='Benchmark focus return';
  button.style.cssText='position:fixed;right:0;bottom:0;width:4px;height:4px;opacity:0.01;z-index:2147483647;padding:0;border:0';
  button.addEventListener('click',()=>{
    const set=value=>Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>value});
    set('hidden');document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('blur'));
    set('visible');document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('focus'));
  });
  document.body.appendChild(button);
}

const uid=i=>`00000000-0000-0000-0000-${i.toString(16).padStart(12,'0')}`;

export async function runAppSample({page,measure,meta,config,sample}){
  const button=(name,exact=true)=>page.getByRole('button',{name,exact});
  const wait=Number(config.setup_timeout_ms||900000);
  const label=n=>`${meta.date_label} · ${meta.cell_label} epoch ${n}`;
  // Setup: open the protocol's Inspect tab and focus epoch 2 (no streams).
  await page.getByText('Owned benchmark project',{exact:false}).first().waitFor({timeout:wait});
  await page.getByText('Fixture protocol',{exact:false}).first().click();
  await page.getByRole('tab',{name:'Inspect',exact:true}).click();
  await button('Edit Tree').waitFor({timeout:wait});
  await page.locator('.cell-tree-date').first().waitFor({timeout:wait});
  await page.locator('.cell-tree-date').first().evaluate(el=>{el.open=true;});
  await page.locator('.cell-tree-cell').first().evaluate(el=>{el.open=true;});
  await button(`Inspect ${label(2)}`).click();
  await page.getByText(`Epoch 2 of ${meta.main_count.toLocaleString('en-US')} matching epochs`,{exact:false}).waitFor({timeout:wait});
  await page.waitForFunction(()=>window.__workflow.requests.every(r=>r.end!==undefined||r.error),null,{timeout:wait});
  const toggleName=`Include ${label(2)} in protocol exports`;
  let pressed=await button(toggleName).getAttribute('aria-pressed');
  for(const variant of ['focused-1','focused-2','focused-3']){
    const expected=pressed!=='true';
    await measure('curation.toggle',variant,button(toggleName),{selector:'button',pressed:{label:toggleName,value:expected},requestDone:{method:'POST',path:'/curation'}});
    pressed=String(expected);
  }
  const step=n=>({selector:'.epoch-navigation span',text:`Epoch ${n} of ${meta.main_count.toLocaleString('en-US')} matching epochs`,focusedLabel:`Inspect ${label(n)}`});
  await measure('epoch.step','after-curation',button('Next epoch',false),step(3));
  const tag=`bench-tag-${sample}-${Date.now()}`;
  await page.getByRole('combobox',{name:'Tag this epoch',exact:false}).or(page.getByLabel('Tag this epoch',{exact:true})).first().fill(tag);
  await measure('tag.add','focused-epoch',button('Add epoch tag'),{selector:`button[aria-label="Remove my epoch tag ${tag}"]`,requestDone:{method:'POST',path:'/api/annotations'}});
  await measure('epoch.step','after-tag',button('Next epoch',false),step(4));
  await page.getByRole('tab',{name:'Overview',exact:true}).click();
  await page.getByRole('tab',{name:'Overview',exact:true,selected:true}).waitFor({timeout:wait}).catch(()=>{});
  await page.waitForTimeout(250);
  await measure('view.tab_return','inspect-unchanged',page.getByRole('tab',{name:'Inspect',exact:true}),{selector:'.epoch-navigation span',text:`Epoch 4 of ${meta.main_count.toLocaleString('en-US')} matching epochs`,focusedLabel:`Inspect ${label(4)}`,enabledButton:'Edit Tree'});
  // Edit Tree with an explicit open path: date → Cell 1 → its epochs.
  await button('Edit Tree').click();
  await page.locator('.tp-column').nth(1).locator('.tp-branch').nth(1).waitFor({timeout:wait});
  await page.locator('.tp-column').nth(1).locator('.tp-branch').nth(1).click();
  const cell1=Array.from({length:Math.min(60,100)},(_,i)=>uid(100+i));
  await page.waitForFunction(first=>!!document.querySelector(`.tp-terminal [data-epoch-uuid="${first}"]`),cell1[0],{timeout:wait});
  await page.waitForFunction(()=>window.__workflow.requests.every(r=>r.end!==undefined||r.error),null,{timeout:wait});
  await page.evaluate(installFocusReturn);
  await measure('focus.return','edit-tree-open-path',page.locator('#__workflow_focus_return'),{selector:'.tp-column .tp-branch',settledPath:{selector:'.tp-terminal [data-epoch-uuid]',uuids:cell1}});
  await button('Back to epochs').click();
  await page.getByRole('tab',{name:'Overview',exact:true}).click();
  const hold=button('Hold to merge all');
  await hold.waitFor({timeout:wait});
  await page.waitForFunction(()=>{const b=document.querySelector('button[aria-label="Hold to merge all"]');return b&&!b.disabled;},null,{timeout:wait});
  await measure('workbench.merge_all','overview-hold',hold,{gesture:'hold',holdMs:1000,selector:'.merge-undo-toast',text:`Merged ${meta.incoming_count} epochs`,requestDone:{method:'POST',path:'/merge-all'}});
  await measure('workbench.undo','toast',page.locator('.merge-undo-toast').getByRole('button',{name:'Undo',exact:false}),{selector:'.merge-undo-toast',text:'Merge undone',requestDone:{method:'POST',path:'/workbench/undo'}});
  await page.locator('.merge-undo-toast').getByRole('button',{name:'Dismiss merge notice'}).click().catch(()=>{});
}
