const fs=require('node:fs'),http=require('node:http'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),dist=path.join(root,'workspace-app/dist');
const types={'.js':'text/javascript','.css':'text/css','.png':'image/png','.html':'text/html'};
function server(){let icon='rieke';return http.createServer((request,response)=>{
 const route=new URL(request.url,'http://127.0.0.1').pathname;
 if(route==='/appUpdates.js'){response.setHeader('Content-Type','text/javascript');response.end(fs.readFileSync(path.join(root,'workspace-app/src/appUpdates.js')));return;}
 if(route.startsWith('/api/')){
  response.setHeader('Content-Type','application/json');
  if(route==='/api/projects')response.end(JSON.stringify({launcher:true,projects:[],managed_root:'/temporary'}));
  else if(route==='/api/app/appearance'){
   if(request.method==='POST'){let body='';request.on('data',chunk=>{body+=chunk;});request.on('end',()=>{icon=JSON.parse(body).icon;response.end(JSON.stringify({icon}));});}
   else response.end(JSON.stringify({icon}));
  }
  else if(route==='/api/app/version')response.end(JSON.stringify({installed:'0.1.3',state:'current'}));
  else response.end('{}');return;
 }
 let file=path.join(dist,route==='/'?'index.html':route);
 if(!file.startsWith(dist)||!fs.existsSync(file)){response.writeHead(404);response.end();return;}
 response.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');response.end(fs.readFileSync(file));
 });}
(async()=>{
 const servers=[server(),server()];await Promise.all(servers.map(s=>new Promise(resolve=>s.listen(0,'127.0.0.1',resolve))));
 const origins=servers.map(s=>`http://127.0.0.1:${s.address().port}`);
 const chrome=process.env.DISCO_CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
 const browser=await chromium.launch({...(fs.existsSync(chrome)?{executablePath:chrome}:{}),headless:true,args:['--no-first-run','--no-default-browser-check']});
 try{
  const context=await browser.newContext();const page=await context.newPage();
  const status={state:'Available',channel:'unsigned-testing',available:'99.0.0'};
  async function claim(url){await page.goto(url);return page.evaluate(async status=>{const {claimUpdateDiscovery}=await import('/appUpdates.js');return claimUpdateDiscovery(status,new Set());},status);}
  assert.equal(await claim(origins[0]),true);
  assert.equal(await claim(origins[1]),false);
  assert.equal(await claim(origins[0]),false);
  const fresh=await browser.newContext();const next=await fresh.newPage();await next.goto(origins[1]);
  assert.equal(await next.evaluate(async status=>{const{claimUpdateDiscovery}=await import('/appUpdates.js');return claimUpdateDiscovery(status,new Set());},status),true);
  await page.goto(origins[0]);await page.waitForFunction(()=>document.querySelector('link[rel="icon"]')?.getAttribute('href')==='/rieke-emblem.png');
  assert.match(await page.title(),/Disco/);
  await page.getByRole('button',{name:'About Disco'}).click();
  await page.getByText('A little lab tradition',{exact:true}).click();
  await page.getByRole('button',{name:'Disco ball',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('link[rel="icon"]')?.getAttribute('href')==='/disco-icon.png');
  await page.getByRole('button',{name:'Rieke emblem',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('link[rel="icon"]')?.getAttribute('href')==='/rieke-emblem.png');
  assert.equal(await page.locator('link[rel="apple-touch-icon"]').getAttribute('href'),'/rieke-os-icon.png');
  const cookie=(await context.cookies()).find(cookie=>cookie.name==='rieke_update_discovery');assert.equal(cookie.expires,-1);
  console.log(JSON.stringify({browser:fs.existsSync(chrome)?'Google Chrome (isolated contexts)':'Playwright Chromium (isolated contexts)',ports:servers.map(s=>s.address().port),claims:[true,false,false],freshSessionClaim:true,sessionCookieExpires:cookie.expires,favicon:'/rieke-emblem.png',title:await page.title()}));
  await context.close();await fresh.close();
 }finally{await browser.close();await Promise.all(servers.map(s=>new Promise(resolve=>s.close(resolve))));}
})().catch(error=>{console.error(error);process.exitCode=1;});
