import test from 'node:test';
import assert from 'node:assert/strict';
import React,{useEffect,useState} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {useSemanticReset} from './useSemanticReset.js';

test('semantic presentation reset matrix distinguishes StrictMode and Activity replay from identity change',async()=>{
 let tree,edit,state;const resets=[],connections=[];
 function Owner({identity,label}){
  const [text,setText]=useState('');state=text;edit=setText;
  useSemanticReset(identity,()=>{resets.push([identity,label]);setText(`default:${identity}:${label}`);});
  useEffect(()=>{connections.push(`open:${identity}`);return()=>connections.push(`close:${identity}`);},[identity]);
  return React.createElement('input',{value:text});
 }
 const render=(identity='a',mode='visible',label='one')=>act(()=>{const node=React.createElement(React.StrictMode,null,React.createElement(React.Activity,{mode},React.createElement(Owner,{identity,label})));tree?tree.update(node):tree=TestRenderer.create(node);});
 try{await render();assert.deepEqual(resets,[['a','one']]);assert.ok(connections.filter(value=>value==='open:a').length>=2,'ordinary authority/subscription effects still replay');
  await act(()=>edit('unfinished'));await render('a','hidden');await render('a','visible','new callback');assert.equal(state,'unfinished');assert.equal(resets.length,1);
  await render('b','hidden','latest');await render('b','visible','latest');assert.equal(state,'default:b:latest');assert.deepEqual(resets,[['a','one'],['b','latest']]);
  await act(()=>edit('other unfinished'));await render('a','visible','returned');assert.equal(state,'default:a:returned');assert.equal(resets.length,3,'A/B/A is a real change, not a global once-per-key cache');
 }finally{await act(()=>tree?.unmount());}
});

test('uncommitted suspended identities cannot consume or reset presentation',async()=>{
 let tree,edit,text;const resets=[],held=new Promise(()=>{});
 function Owner({identity,suspend}){const [value,setValue]=useState('');edit=setValue;text=value;useSemanticReset(identity,()=>{resets.push(identity);setValue(identity);});if(suspend)throw held;return React.createElement('span',null,value);}
 const render=(identity,suspend=false)=>act(()=>{const node=React.createElement(React.Suspense,{fallback:'pending'},React.createElement(Owner,{identity,suspend}));tree?tree.update(node):tree=TestRenderer.create(node);});
 try{await render('a');await act(()=>edit('draft'));await render('b',true);assert.deepEqual(resets,['a']);await render('a');assert.equal(text,'draft');assert.deepEqual(resets,['a']);}finally{await act(()=>tree?.unmount());}
});
