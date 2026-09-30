'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path');
const {createHash} = require('node:crypto');
const {createFixture, launch, gracefulQuit} = require('./helpers.cjs');
const {verifyResources} = require('../updater-validation.cjs');
const output = path.resolve(__dirname, '../../docs/dev/desktop-ui-e2e');
(async () => {
  const fixture = await createFixture(); let application, page;
  const manifestBytes = await fs.readFile(path.join(fixture.bundle, 'Contents/Resources/runtime/runtime-manifest.json'));
  const manifest = JSON.parse(manifestBytes);
  try {
    ({application,page} = await launch(fixture));
    await page.getByRole('heading', {name:'Your projects', exact:true}).waitFor({timeout:90000});
    const previous = JSON.parse(await fs.readFile(path.join(output, 'before-toolbar-fit-fix.json')));
    await page.getByRole('button', {name:new RegExp('^Open Electron lifecycle fixture ' + previous.run_id + ',')}).click();
    await page.getByRole('button', {name:'Project overview',exact:true}).waitFor({timeout:90000});
    const profile = page.getByRole('dialog', {name:'Tag author',exact:true});
    if(await profile.waitFor({state:'visible',timeout:3000}).then(()=>true).catch(()=>false)) {
      await profile.getByRole('button', {name:'Electron E2E',exact:true}).first().click(); await profile.waitFor({state:'hidden'});
    }
    const source = await fs.readFile(path.resolve(__dirname,'../../workspace-app/src/styles.css'),'utf8');
    const marker = '/* Keep the app mark visible as the scientific toolbar gets narrower. */';
    assert.ok(source.includes(marker)); const css = source.slice(source.indexOf(marker));
    // The packaged CSP explicitly allows inline styles. This preview leaves
    // that policy, the app bundle and all backend resources unchanged.
    assert.ok(await page.evaluate(css => {const style=document.createElement('style');style.textContent=css;document.head.append(style);return style.sheet?.cssRules.length>0;},css));
    const measurements = [];
    for(const width of [1440,960]) {
      await application.evaluate(({BrowserWindow},width)=>BrowserWindow.getAllWindows()[0].setContentSize(width,900),width);
      await page.waitForFunction(width=>innerWidth===width,width);
      const geometry = await page.evaluate(()=>{
        const icon=document.querySelector('.header-app-icon'),header=document.querySelector('.app-header');
        const rect=node=>{const r=node.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};};
        return {width:innerWidth,naturalWidth:icon.naturalWidth,icon:rect(icon),header:rect(header),controls:[...header.children]
          .filter(node=>node!==icon&&!node.classList.contains('spacer')&&node.getClientRects().length).map(node=>({className:node.className,...rect(node)}))};
      });
      await page.screenshot({path:path.join(output,`toolbar-preview-${width}.png`)});
      assert.ok(geometry.naturalWidth>0); assert.ok(geometry.icon.right<=geometry.header.right&&geometry.icon.right<=width);
      for(const c of geometry.controls) assert.ok(!(c.left<geometry.icon.right&&c.right>geometry.icon.left&&c.top<geometry.icon.bottom&&c.bottom>geometry.icon.top));
      measurements.push(geometry);
    }
    await gracefulQuit(application,page); application=null;page=null;
    await verifyResources(path.join(fixture.bundle,'Contents/Resources/runtime'),manifest.resources);
    const receipt={format:'rieke-toolbar-css-preview',version:1,passed:true,final_packaged_qualification:false,
      method:'Exact prior disposable packaged fixture; DOM-only inline CSS allowed by existing CSP; no bundle or backend mutation',
      source_manifest_sha256:createHash('sha256').update(manifestBytes).digest('hex'),preview_css_sha256:createHash('sha256').update(css).digest('hex'),measurements};
    await fs.writeFile(path.join(output,'toolbar-preview.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));
  } finally {if(application&&page) await gracefulQuit(application,page);}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
