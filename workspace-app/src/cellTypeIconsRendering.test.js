import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

test('recorded types select consistent icons across overview, cell list, selection and incoming chips',async()=>{
  const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
  const dom=new JSDOM('<!doctype html><main></main>');
  const root=dom.window.document.querySelector('main');
  const draw=(Component,props)=>{root.innerHTML=renderToStaticMarkup(React.createElement(Component,props));return root;};
  try{
    const {default:Summary}=await server.ssrLoadModule('/src/cell-qc/ui/CellTypeSummary.jsx');
    const {CellList}=await server.ssrLoadModule('/src/components/Common.jsx');
    const {default:Selection}=await server.ssrLoadModule('/src/protocol-overview/ui/SelectionOverview.jsx');
    const {default:Incoming}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingCellTypes.jsx');
    const examples=[['RGC\\ON-parasol','on-parasol'],['OFF parasol','off-parasol'],['ON midget','on-midget'],['OFF midget','off-midget'],['Bipolar\\ON','on-bipolar'],['OFF bipolar','off-bipolar'],['Cones','cone'],['Rod','rod'],['Horizontal cell','horizontal']];
    for(const [type,token] of examples){
      const cell=Object.freeze({cell_uuid:`id-${token}`,cell_type:type,label:'Cell 1',date:'2026-10-11',epochs:1});
      const fixtures=[
        [Summary,{types:[{type,count:1}],total:1},'.cell-type-neuron svg'],
        [CellList,{cells:[cell]},'.cell-glyph svg'],
        [Selection,{cell},'.selection-overview>svg'],
        [Incoming,{cells:[cell],count:1},'.incoming-type-chip svg'],
      ];
      for(const [Component,props,selector] of fixtures){
        const svg=draw(Component,props).querySelector(selector);
        assert.ok(svg,`${type}: ${selector}`);
        assert.equal(svg.style.color,/^(on|off)-/.test(token)?`var(--cell-${token.split('-')[0]})`:'var(--ink-muted)');
        assert.equal(svg.getAttribute('aria-hidden'),'true','recorded text supplies accessible identity');
      }
      assert.equal(draw(Summary,{types:[{type,count:1}],total:1}).querySelector('.cell-type-name').firstChild.textContent,type);
      assert.match(draw(CellList,{cells:[cell]}).textContent,new RegExp(`id-${token}`));
    }
    const unknown=draw(Selection,{cell:{cell_uuid:'unknown',label:'ON parasol',epochs:1}}).querySelector('svg');
    assert.equal(unknown.style.color,'var(--ink-muted)','a display name must not classify the cell');
  }finally{dom.window.close();await server.close();}
});
