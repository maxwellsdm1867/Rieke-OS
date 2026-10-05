import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('candidate detail and tree toggles use proposal flags; native toggles ignore them; unknown stays unavailable',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'silent',optimizeDeps:{noDiscovery:true,entries:[]}});
 let rendered;
 try{
  const {default:Detail}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochAnalysisInclusion.jsx');
  const {default:Row}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochInclusionToggle.jsx');
  const epoch={epoch_uuid:'epoch-A',curation:{included:true,review_state:'unreviewed',revision:0},review_decision:{selected:false,reviewed:true,excluded:true}};
  const original=structuredClone(epoch),calls=[];
  const update=async(component,props)=>act(async()=>{const element=React.createElement(component,{epoch,label:'epoch A',onToggle:(...args)=>calls.push(args),...props});if(rendered)rendered.update(element);else rendered=TestRenderer.create(element);});
  await update(Detail,{incoming:true});let input=rendered.root.findByType('input');assert.equal(input.props.checked,false);
  await act(()=>input.props.onChange({target:{checked:true}}));assert.equal(calls.at(-1)[0],epoch);assert.equal(calls.at(-1)[1],true);
  await update(Row,{incoming:true});let button=rendered.root.findByType('button');assert.equal(button.props['aria-pressed'],false);assert.match(button.props['aria-label'],/incoming additions/);
  await act(()=>button.props.onClick());assert.equal(calls.at(-1)[1],true);
  await update(Row,{incoming:false});button=rendered.root.findByType('button');assert.equal(button.props['aria-pressed'],true);assert.match(button.props['aria-label'],/protocol exports/);
  await update(Detail,{incoming:false});assert.equal(rendered.root.findByType('input').props.checked,true);
  await update(Row,{incoming:true,epoch:{...epoch,review_decision:undefined}});button=rendered.root.findByType('button');assert.equal(button.props.disabled,true);assert.equal(button.props['aria-pressed'],undefined);assert.match(button.props.title,/unavailable/);
  await update(Detail,{incoming:true,epoch:{...epoch,review_decision:undefined}});assert.equal(rendered.root.findAllByType('input').length,0);assert.match(rendered.toJSON().children.join(''),/unavailable/);
  assert.deepEqual(epoch,original);
 }finally{await act(async()=>rendered?.unmount());await server.close();}
});
