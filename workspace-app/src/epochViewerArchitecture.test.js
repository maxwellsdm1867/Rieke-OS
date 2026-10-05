import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
test('protocol and search adapters delegate their entire viewer assembly to one shared renderer',async()=>{
 for(const adapter of ['Inspector','MatchingEpochs','MetadataExplorer']){
  const source=await readFile(new URL(`./${adapter==='MetadataExplorer'?'metadata-explorer':'epoch-browser'}/ui/${adapter}.jsx`,import.meta.url),'utf8');
  assert.match(source,adapter==='MetadataExplorer'?/<MatchingEpochs\b/:/<EpochViewer\b/,adapter);
  for(const component of ['EpochBrowserLayout','EpochBrowserToolbar','EpochTreePane','EpochDetailHeading','EpochAnalysisInclusion','MetadataPanel','TreeBuilder','PagedTree','ProtocolViewFilter'])assert.doesNotMatch(source,new RegExp(`<${component}\\b`),`${adapter} must not assemble ${component} independently`);
 }
 const shared=await readFile(new URL('./epoch-browser/ui/EpochViewer.jsx',import.meta.url),'utf8');
 for(const component of ['EpochBrowserLayout','EpochBrowserToolbar','EpochTreePane','EpochDetailHeading','EpochAnalysisInclusion','MetadataPanel','TreeBuilder','RetainedTreePresentation','ProtocolViewFilter'])assert.match(shared,new RegExp(`<${component}\\b`),`${component} belongs to the common renderer`);
 const retained=await readFile(new URL('./tree-browser/ui/RetainedTreePresentation.jsx',import.meta.url),'utf8');assert.match(retained,/<Activity\b/);assert.match(retained,/<PagedTree\b/);
});

test('search designer delegates to the shared viewer and both adapters supply local filters',async()=>{
 const explorer=await readFile(new URL('./metadata-explorer/ui/MetadataExplorer.jsx',import.meta.url),'utf8');
 assert.match(explorer,/<MatchingEpochs designMode/);
 assert.doesNotMatch(explorer,/<(?:TreeBuilder|PagedTree|EpochBrowserLayout)\b/);
 for(const adapter of ['Inspector','MatchingEpochs']){
  const source=await readFile(new URL(`./${adapter==='MetadataExplorer'?'metadata-explorer':'epoch-browser'}/ui/${adapter}.jsx`,import.meta.url),'utf8');
  assert.match(source,/onViewFilters=/);
  assert.doesNotMatch(source,/<ProtocolViewFilter\b/);
 }
});
