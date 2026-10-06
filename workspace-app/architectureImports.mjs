// The lock pins the parser and native binding. No regex fallback on failure.
import {parseSync} from 'rolldown/utils';
import {readFileSync} from 'node:fs';
import {builtinModules,isBuiltin} from 'node:module';
import {pathToFileURL} from 'node:url';

export function analyze(filename,source,{allowDomOverride=false}={}){
 const parsed=parseSync(filename,source);
 if(parsed.errors.length)throw Error(`Parse diagnostics in ${filename}: ${parsed.errors.map(e=>e.message).join('; ')}`);
 if(parsed.program?.type!=='Program')throw Error(`Unsupported parser AST for ${filename}`);
 const found=[],exports=[];let domOverrides=0,hasReexports=false;
 const loader=node=>(node?.type==='Identifier'&&node.name==='require')||(node?.type==='MemberExpression'&&node.object?.name==='module'&&(node.property?.name==='require'||node.property?.value==='require'));
 const property=(node,name)=>node?.type==='MemberExpression'&&!node.computed&&node.property?.name===name;
 const dom=node=>node?.type==='LogicalExpression'&&node.operator==='||'&&node.right?.value==='jsdom'&&property(node.left,'RIEKE_TEST_DOM_MODULE')&&property(node.left.object,'env')&&node.left.object.object?.name==='process';
 function binding(node){
  if(node?.type==='Identifier')exports.push(node.name);
  else if(node?.type==='ObjectPattern')for(const item of node.properties)binding(item.value??item.argument);
  else if(node?.type==='ArrayPattern')node.elements.forEach(binding);
  else if(node?.type==='AssignmentPattern')binding(node.left);
  else if(node?.type==='RestElement')binding(node.argument);
 }
 function visit(node,parent){
  if(!node||typeof node!=='object')return;
  if(['ImportDeclaration','ExportNamedDeclaration','ExportAllDeclaration'].includes(node.type)&&node.source)found.push(node.source.value);
  if(node.type==='ExportDefaultDeclaration')exports.push('default');
  if(node.type==='ExportAllDeclaration'){exports.push('*');hasReexports=true;}
  if(node.type==='ExportNamedDeclaration'){
   if(node.source)hasReexports=true;
   if(node.declaration?.type==='VariableDeclaration')for(const d of node.declaration.declarations)binding(d.id);
   else if(node.declaration?.id)binding(node.declaration.id);
   for(const item of node.specifiers??[])exports.push(item.exported?.name??item.exported?.value);
  }
  if(node.type==='ImportExpression'){
   if(allowDomOverride&&dom(node.source)){domOverrides++;found.push('jsdom');}
   else found.push(node.source.value);
  }
  if(node.type==='MemberExpression'&&node.computed&&typeof node.property?.value!=='string'&&(node.object?.name==='module'||node.object?.type==='MetaProperty'&&node.object.meta?.name==='import'))throw Error(`Computed module/meta loader member in ${filename} is not statically checkable`);
  if(node.type==='MemberExpression'&&node.object?.type==='MetaProperty'&&node.object.meta?.name==='import'&&['glob','globEager'].includes(node.property?.name??node.property?.value))throw Error(`Unsupported import.meta.glob loader in ${filename}`);
  if(node.type==='CallExpression'&&loader(node.callee))found.push(node.arguments[0]?.value);
  const propertyKey=parent?.type==='Property'&&parent.key===node&&!parent.computed&&!parent.shorthand;
  const memberKey=parent?.type==='MemberExpression'&&parent.property===node&&!parent.computed;
  if(loader(node)&&!propertyKey&&!memberKey&&!(parent?.type==='CallExpression'&&parent.callee===node))throw Error(`Aliased loader in ${filename} is not statically checkable`);
  for(const child of Object.values(node)){
   if(Array.isArray(child))child.forEach(value=>visit(value,node));else if(child&&typeof child==='object')visit(child,node);
  }
 }
 visit(parsed.program);
 if(found.some(value=>typeof value!=='string'))throw Error(`Computed module loading in ${filename} is not statically checkable`);
 if(allowDomOverride&&domOverrides!==1)throw Error(`Expected exactly one approved DOM loader in ${filename}`);
 return {dependencies:found,exports,hasReexports,domOverrides};
}
export const dependencies=(filename,source)=>analyze(filename,source).dependencies;

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{
  const files=JSON.parse(readFileSync(0,'utf8'));
  process.stdout.write(JSON.stringify(files.map(({filename,source,allowDomOverride=false})=>{
   const result=analyze(filename,source,{allowDomOverride});
   // Node 22 omits prefix-only modules such as node:test from builtinModules.
   // Ask Node about each exact specifier; never allow every node: prefix.
   return {filename,...result,builtins:[...new Set([...builtinModules,...result.dependencies.filter(isBuiltin)])]};
  })));
 }catch(error){process.stderr.write(`Architecture parser failed: ${error.message}\n`);process.exitCode=1;}
}
