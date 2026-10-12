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
    const examples=[
      ['RGC/ON-parasol','cell-on'],['RGC/OFF-parasol','cell-off'],['RGC/ON-midget','cell-on'],['RGC/OFF-midget','cell-off'],['RGC/small bistratified','cell-bistratified'],
      ['amacrine/AII','cell-amacrine'],['amacrine/A17','cell-amacrine'],['amacrine/starburst','cell-amacrine'],
      ['bipolar/OFF-diffuse','cell-off'],['bipolar/OFF-midget','cell-off'],['bipolar/ON-diffuse','cell-on'],['bipolar/ON-midget','cell-on'],['bipolar/rod','cell-on'],
      ['horizontal','cell-outer'],['photoreceptor/S cone','cell-cone-s'],['photoreceptor/M cone','cell-cone-m'],['photoreceptor/L cone','cell-cone-l'],['photoreceptor/rod','cell-outer'],['unknown','ink-muted'],
      ['ON bipolar','cell-on'],['OFF bipolar','cell-off'],['Cones','ink-muted'],['Unspecified-type bipolar','ink-muted'],['Generic amacrine','ink-muted'],
      ['RGC/unlisted subtype','ink-muted'],['bipolar/unlisted subtype','ink-muted'],['amacrine/unlisted subtype','ink-muted'],['photoreceptor/unlisted subtype','ink-muted'],
    ];
    for(const [index,[type,token]] of examples.entries()){
      const cell=Object.freeze({cell_uuid:`id-${index}`,cell_type:type,label:'Cell 1',date:'2026-10-12',epochs:1});
      const fixtures=[
        [Summary,{types:[{type,count:1}],total:1},'.cell-type-neuron svg'],
        [CellList,{cells:[cell]},'.cell-glyph svg'],
        [Selection,{cell},'.selection-overview>svg'],
        [Incoming,{cells:[cell],count:1},'.incoming-type-chip svg'],
      ];
      for(const [Component,props,selector] of fixtures){
        const svg=draw(Component,props).querySelector(selector);
        assert.ok(svg,`${type}: ${selector}`);
        assert.equal(svg.style.color,`var(--${token})`);
        assert.equal(svg.getAttribute('aria-hidden'),'true','recorded text supplies accessible identity');
      }
      assert.equal(draw(Summary,{types:[{type,count:1}],total:1}).querySelector('.cell-type-name').firstChild.textContent,type);
      assert.match(draw(CellList,{cells:[cell]}).textContent,new RegExp(`id-${index}`));
    }
    const glyph=type=>draw(Selection,{cell:{cell_uuid:'identity',cell_type:type,epochs:1}}).querySelector('svg').innerHTML;
    assert.notEqual(glyph('RGC/ON-midget'),glyph('bipolar/ON-midget'));
    assert.notEqual(glyph('photoreceptor/rod'),glyph('bipolar/rod'));
    assert.equal(glyph('photoreceptor/S cone'),glyph('photoreceptor/M cone'));
    assert.equal(glyph('photoreceptor/M cone'),glyph('photoreceptor/L cone'));
    assert.equal(new Set(['AII','A17','starburst','unknown'].map(type=>glyph(`amacrine/${type}`))).size,4);
    const unknown=draw(Selection,{cell:{cell_uuid:'unknown',label:'ON parasol',epochs:1}}).querySelector('svg');
    assert.equal(unknown.style.color,'var(--ink-muted)','a display name must not classify the cell');
  }finally{dom.window.close();await server.close();}
});
