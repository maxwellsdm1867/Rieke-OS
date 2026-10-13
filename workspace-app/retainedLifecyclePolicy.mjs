// Review receipts for the complete production dependency closure of App.
// This is deliberately conservative: helper changes also invalidate receipts.
import {readFileSync,existsSync} from 'node:fs';
import {resolve,dirname,relative,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {parseSync} from 'rolldown/utils';
import {analyze} from './architectureImports.mjs';

const root=dirname(fileURLToPath(import.meta.url));
const ignored=new Set(['start','end','loc','range','comments','leadingComments','trailingComments','innerComments']);
function canonical(value){
 if(Array.isArray(value))return value.map(canonical);
 if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).filter(key=>!ignored.has(key)).sort().map(key=>[key,canonical(value[key])]));
 return value;
}
const digest=value=>createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
export function inspectModule(filename,source){
 const dependencies=analyze(filename,source).dependencies;
 const parsed=parseSync(filename,source);
 const hooks=new Map(),namespaces=new Set(),sites=[];
 for(const node of parsed.program.body){
  if(node.type!=='ImportDeclaration')continue;
  for(const specifier of node.specifiers){
   const imported=specifier.imported?.name;
   if(node.source.value==='react'){
    if(['useEffect','useLayoutEffect','useInsertionEffect'].includes(imported))hooks.set(specifier.local.name,imported);
    if(['ImportDefaultSpecifier','ImportNamespaceSpecifier'].includes(specifier.type))namespaces.add(specifier.local.name);
   }
   if(imported==='useSemanticReset')hooks.set(specifier.local.name,imported);
  }
 }
 function visit(node,owner='<module>',parent){
  if(!node||typeof node!=='object')return;
  if(['FunctionDeclaration','FunctionExpression','ArrowFunctionExpression'].includes(node.type))owner=node.id?.name??(parent?.type==='VariableDeclarator'?parent.id?.name:undefined)??owner;
  if(node.type==='Identifier'&&hooks.has(node.name)&&parent?.type!=='ImportSpecifier'&&!(parent?.type==='CallExpression'&&parent.callee===node))throw Error(`Unsupported lifecycle hook alias/reference in ${filename}: ${node.name}`);
  if(node.type==='MemberExpression'&&namespaces.has(node.object?.name)&&['useEffect','useLayoutEffect','useInsertionEffect'].includes(node.property?.name??node.property?.value)&&!(parent?.type==='CallExpression'&&parent.callee===node))throw Error(`Unsupported lifecycle namespace hook alias in ${filename}`);
  if(node.type==='VariableDeclarator'&&namespaces.has(node.init?.name)&&node.id?.type==='ObjectPattern'&&node.id.properties.some(property=>['useEffect','useLayoutEffect','useInsertionEffect'].includes(property.key?.name??property.key?.value)))throw Error(`Unsupported destructured lifecycle hook in ${filename}`);
  if(node.type==='CallExpression'){
   const callee=node.callee;
   const kind=callee?.type==='Identifier'?hooks.get(callee.name):callee?.type==='MemberExpression'&&namespaces.has(callee.object?.name)?(callee.property?.name??callee.property?.value):null;
   if(['useEffect','useLayoutEffect','useInsertionEffect','useSemanticReset'].includes(kind))sites.push({owner,kind,fingerprint:digest(node)});
  }
  for(const value of Object.values(node))if(Array.isArray(value))value.forEach(child=>visit(child,owner,node));else if(value&&typeof value==='object')visit(value,owner,node);
 }
 visit(parsed.program);
 return {fingerprint:digest(parsed.program),sites,dependencies};
}
export function census(base=root){
 const pending=[resolve(base,'src/App.jsx')],result={};
 while(pending.length){
  const filename=pending.pop(),name=relative(base,filename).replaceAll('\\','/');
  if(result[name])continue;
  if(!name.startsWith('src/')||name.includes('/test-support/')||name.includes('.test.'))throw Error(`Non-production dependency: ${name}`);
  const {dependencies,...receipt}=inspectModule(filename,readFileSync(filename,'utf8'));result[name]=receipt;
  for(const dependency of dependencies){
   if(!dependency.startsWith('.')){
    if(!['react','react-dom','react-dom/client','lucide-react','@tanstack/react-query'].includes(dependency))throw Error(`Unreviewed external or aliased dependency ${name}: ${dependency}`);
    continue;
   }
   const target=resolve(dirname(filename),dependency);
   if(['.css','.svg','.png','.jpg','.woff2'].includes(extname(target)))continue;
   const found=[target,...['.js','.jsx','.mjs','/index.js','/index.jsx'].map(suffix=>target+suffix)].find(path=>existsSync(path)&&['.js','.jsx','.mjs'].includes(extname(path)));
   if(!found)throw Error(`Unresolved production dependency ${name}: ${dependency}`);
   pending.push(found);
  }
 }
 return Object.fromEntries(Object.entries(result).sort(([a],[b])=>a.localeCompare(b)));
}
export function checkInventory(actual,inventory){
 const failures=[];
 for(const [name,receipt] of Object.entries(actual)){
  const reviewed=inventory.modules?.[name];
  if(!reviewed){failures.push(`${name}: missing lifecycle review`);continue;}
  if(reviewed.fingerprint!==receipt.fingerprint)failures.push(`${name}: source changed since lifecycle review`);
  if(JSON.stringify(reviewed.sites)!==JSON.stringify(receipt.sites))failures.push(`${name}: effect census changed`);
  if(!reviewed.reason||!reviewed.lifetime||!Array.isArray(reviewed.tests)||!reviewed.tests.length)failures.push(`${name}: incomplete ownership/behavior receipt`);
 }
 for(const name of Object.keys(inventory.modules??{}))if(!actual[name])failures.push(`${name}: stale dependency receipt`);
 return failures;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const actual=census();
 if(process.argv.includes('--census'))process.stdout.write(JSON.stringify(actual,null,2)+'\n');
 else{
  const inventory=JSON.parse(readFileSync(resolve(root,'../docs/architecture/retained-ui-lifetimes.json'),'utf8'));
  const failures=checkInventory(actual,inventory);
  if(failures.length){console.error(failures.join('\n'));process.exitCode=1;}
  else console.log(`Retained lifecycle review: ${Object.keys(actual).length} modules checked`);
 }
}
