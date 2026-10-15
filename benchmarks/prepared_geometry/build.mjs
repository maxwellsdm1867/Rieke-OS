import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
export async function buildOwnedProduction(source,meta,output){
 const workspace=path.join(source,'workspace-app'),require=createRequire(path.join(workspace,'package.json'));
 const {build}=await import(pathToFileURL(require.resolve('vite')));
 const {default:react}=await import(pathToFileURL(path.join(workspace,'node_modules/@vitejs/plugin-react/dist/index.js')));
 const {fixtureSource}=await import(pathToFileURL(path.resolve(import.meta.dirname,'../workflow/fixture-app.mjs')));
 const root=path.join(output,'production-entry'),outDir=path.join(output,'production-dist');await fs.mkdir(root,{recursive:true});
 await fs.symlink(path.join(workspace,'src'),path.join(root,'src'),'dir');
 await fs.symlink(await fs.realpath(path.join(workspace,'node_modules')),path.join(root,'node_modules'),'dir');
 await fs.writeFile(path.join(root,'index.html'),'<!doctype html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>');
 const ending="createRoot(document.getElementById('root')).render(<App/>);";
 let shell=fixtureSource(meta);if(shell.split(ending).length!==2)throw Error('Fixture composition bootstrap changed');
 shell=shell.replace(ending,"window.__diagnosticProductionContext={mode:import.meta.env.MODE,production:import.meta.env.PROD,react:React.version,entry:'src/main.jsx',ownedComposition:true};export default App;");
 const appPath=path.join(root,'OwnedApp.jsx');await fs.writeFile(appPath,shell);
 let replaced=0;
 await build({root,configFile:false,mode:'production',base:'/__workflow-assets/',logLevel:'error',plugins:[react(),{name:'owned-production-composition',enforce:'pre',resolveId(id,importer){if(id==='./App.jsx'&&importer?.endsWith('/src/main.jsx')){replaced++;return appPath;}}}],define:{'process.env.NODE_ENV':JSON.stringify('production')},build:{outDir,emptyOutDir:false,manifest:true,minify:true,sourcemap:false}});
 if(replaced!==1)throw Error('Expected exactly one actual main.jsx App substitution');
 const files={};async function hash(dir){for(const item of await fs.readdir(dir,{withFileTypes:true})){const p=path.join(dir,item.name);if(item.isDirectory())await hash(p);else files[path.relative(outDir,p)]=crypto.createHash('sha256').update(await fs.readFile(p)).digest('hex');}}await hash(outDir);
 const receipt={runtime:'production-react-vite-build',productionBootstrap:'workspace-app/src/main.jsx',bootstrapSha256:crypto.createHash('sha256').update(await fs.readFile(path.join(workspace,'src/main.jsx'))).digest('hex'),topLevelApp:'same owned real-component workflow fixture; fullApp navigation/session restoration unmeasured',viteProxy:false,assetBase:'/__workflow-assets/',files};
 await fs.writeFile(path.join(output,'production-build-receipt.json'),JSON.stringify(receipt,null,2));return receipt;
}
