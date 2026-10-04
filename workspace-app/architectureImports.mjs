// The frontend lock pins this parser and its native binding. Parse errors or a
// missing binding fail the guard; there is deliberately no regex fallback.
import {parseSync} from 'rolldown/utils';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';

export function dependencies(filename,source){
  const parsed=parseSync(filename,source);
  if(parsed.errors.length)throw new Error(`Parse diagnostics in ${filename}: ${parsed.errors.map(error=>error.message).join("; ")}`);
  if(parsed.program?.type!=="Program")throw new Error(`Unsupported parser AST for ${filename}`);
  const found=[];
  function visit(node,parent){
    if(!node||typeof node!=='object')return;
    if(['ImportDeclaration','ExportNamedDeclaration','ExportAllDeclaration'].includes(node.type)&&node.source)found.push(node.source.value);
    if(node.type==='ImportExpression')found.push(node.source.value);
    const loader=callee=>(callee?.type==='Identifier'&&callee.name==='require')||(callee?.type==='MemberExpression'&&callee.object?.name==='module'&&
      (callee.property?.name==='require'||callee.property?.value==='require'));
    if(node.type==='CallExpression'&&loader(node.callee))found.push(node.arguments[0]?.value);
    if(loader(node)&&!(parent?.type==='MemberExpression'&&parent.property===node)&&!(parent?.type==='CallExpression'&&parent.callee===node))throw new Error(`Aliased loader in ${filename} is not statically checkable`);
    for(const child of Object.values(node)){
      if(Array.isArray(child))child.forEach(item=>visit(item,node));else if(child&&typeof child==='object')visit(child,node);
    }
  }
  visit(parsed.program);
  if(found.some(value=>typeof value!=="string"))throw new Error(`Computed module loading in ${filename} is not statically checkable`);
  return found;
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{
    const files=JSON.parse(readFileSync(0,'utf8'));
    process.stdout.write(JSON.stringify(files.map(({filename,source})=>({filename,dependencies:dependencies(filename,source)}))));
  }catch(error){process.stderr.write(`Architecture parser failed: ${error.message}\n`);process.exitCode=1;}
}
