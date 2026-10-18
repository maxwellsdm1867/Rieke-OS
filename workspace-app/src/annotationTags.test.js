import test from 'node:test';
import assert from 'node:assert/strict';
import {compactAnnotationTags,annotationChange,annotationIndicator,annotationPredicate,bulkAnnotationChange,canRemoveAnnotation,navigateAfterTagSave} from "./annotations/annotationTags.js";
const first={epoch_uuid:'epoch-a',cell_uuid:'cell-a',cell_label:'Cell1',date:'2026-09-23'};
const second={epoch_uuid:'epoch-b',cell_uuid:'cell-b',cell_label:'Cell1',date:'2026-09-24'};
const annotations={revisions:{cell:{me:3},epoch:{me:2}}};
test('cell annotation identity uses UUID rather than reused date or cell labels',()=>{
 const a=annotationChange({epoch:first,targetKind:'cell',profileUuid:'me',annotations,tag:'good'}),b=annotationChange({epoch:second,targetKind:'cell',profileUuid:'me',annotations,tag:'good'});
 assert.deepEqual(a.target_uuids,['cell-a']);assert.deepEqual(b.target_uuids,['cell-b']);assert.deepEqual(a.expected_revisions,{'cell-a':3});
 const direct=annotationChange({epoch:first,targetKind:'epoch',profileUuid:'me',annotations,tag:'good',remove:true});
 assert.deepEqual(direct.target_uuids,['epoch-a']);assert.deepEqual(direct.tags_remove,['good']);assert.deepEqual(direct.tags_add,[]);
});
test('inherited, direct, dataset and same-text author annotations remain distinct',()=>{
 const record={annotations:{cell_tags:[{tag:'good',profile_uuid:'me',author_name:'Fred'},{tag:'good',profile_uuid:'other',author_name:'Max'}],epoch_tags:[{tag:'good',profile_uuid:'me',author_name:'Fred'}]},curation:{tags:['good']}};
 const indicator=annotationIndicator(record);assert.deepEqual([indicator.count,indicator.cell,indicator.epoch,indicator.dataset],[4,2,1,1]);assert.match(indicator.title,/Cell: good · Max/);assert.match(indicator.title,/Dataset: good/);
 assert.equal(canRemoveAnnotation(record.annotations.cell_tags[1],'me'),false);assert.equal(canRemoveAnnotation(record.annotations.epoch_tags[0],'me'),true);
});
test('bulk targets are exact UUIDs with verified author-specific revisions and no cell promotion',()=>{
 const body=bulkAnnotationChange({targetUuids:['epoch-b','epoch-a','epoch-b'],profileUuid:'me',tag:'stable',read:{targets:{'epoch-a':{target_kind:'epoch',target_uuid:'epoch-a',revisions:{me:4}},'epoch-b':{target_kind:'epoch',target_uuid:'epoch-b',revisions:{}}}}});
 assert.deepEqual(body.target_uuids,['epoch-b','epoch-a']);assert.deepEqual(body.expected_revisions,{'epoch-b':0,'epoch-a':4});assert.equal(body.target_kind,'epoch');
 assert.throws(()=>bulkAnnotationChange({targetUuids:['missing'],profileUuid:'me',tag:'x',read:{targets:{}}}),/verified/);
});
test('tag filters use exact array membership in the intended shared annotation scope',()=>{
 assert.deepEqual(annotationPredicate('cell','NBQX'),{all:[{field:'annotations/cell/tags',operator:'contains',value:'NBQX'}]});
 assert.equal(annotationPredicate('effective','good').all[0].field,'annotations/effective/tags');
 assert.throws(()=>annotationPredicate('protocol','good'),/Unknown/);
});


test('Tab waits for a tag save and never advances on failure or a changed epoch',async()=>{
 const calls=[];
 const base={draft:' good ',isCurrent:()=>true,navigate:direction=>calls.push(direction),direction:1};
 assert.equal(await navigateAfterTagSave({...base,save:async tag=>{calls.push(tag);return true;}}),true);
 assert.deepEqual(calls,['good',1]);calls.length=0;
 assert.equal(await navigateAfterTagSave({...base,save:async()=>false}),false);
 assert.equal(await navigateAfterTagSave({...base,save:async()=>true,isCurrent:()=>false}),false);
 assert.deepEqual(calls,[]);
 assert.equal(await navigateAfterTagSave({...base,draft:' ',direction:-1,save:()=>{throw Error('Blank tag must not save');}}),true);
 assert.deepEqual(calls,[-1]);
});


test('compact row indicators show cell tags once and direct tags only on epochs',()=>{
  const row={annotations:{cell_tags:[{tag:'cell',author_name:'A'}],epoch_tags:[{tag:'epoch',author_name:'B'}]},curation:{tags:['dataset']}};
  assert.equal(annotationIndicator(row,'cell').count,1);
  assert.equal(annotationIndicator(row,'epoch').count,2);
  assert.doesNotMatch(annotationIndicator(row,'epoch').title,/Cell:/);
  assert.equal(annotationIndicator({annotations:{cell_tags:row.annotations.cell_tags}},'epoch').count,0);
});


test('tag pills keep one color per text and merge authors without hiding distinct tags',()=>{
  const a={tag:'Quality',author_name:'Alice'},b={tag:'Reviewed',author_name:'Bob'};
  const first=compactAnnotationTags({annotations:{epoch_tags:[a,{...a,author_name:'Bob'},b]}});
  const reordered=compactAnnotationTags({annotations:{cell_tags:[b,a]}},'cell');
  assert.equal(first.length,2);
  assert.equal(first[0].color,reordered[1].color);
  assert.match(first[0].title,/Alice, Bob/);
});

test('chip tooltip shows author and added time; approximate and pending states are explicit',async()=>{
 const {annotationChipTitle,formatTagTime}=await import('./annotations/annotationTags.js');
 const format=date=>date.toISOString();
 const chip={tag:'good',author_name:'Ada',added_at:'2026-10-01T12:30:00Z',time_source:'recorded'};
 assert.equal(annotationChipTitle(chip,'epoch',format),'good · epoch tag · Ada · added 2026-10-01T12:30:00.000Z');
 assert.equal(annotationChipTitle({...chip,time_source:'approximate'},'cell',format),'good · inherited from cell · Ada · added about 2026-10-01T12:30:00.000Z (approximate)');
 assert.equal(annotationChipTitle({tag:'new',author_name:'Ada',pending:true},'epoch',format),'new · epoch tag · Ada · saving…');
 assert.equal(annotationChipTitle({tag:'old',author_name:''},'epoch',format),'old · epoch tag · author not recorded');
 assert.equal(formatTagTime('not a time',format),'');
 assert.ok(formatTagTime('2026-10-01T12:30:00Z').length>0);
});

test('unsaved tag recovery restores one text and names every other cancelled text',async()=>{
  const {unsavedTagRecovery,unsavedTagMessage}=await import('./annotations/annotationTags.js');
  const cancelled=[{tag:'b'},{tag:'x',remove:true},{tag:'c '}];
  assert.deepEqual(unsavedTagRecovery({failedTag:'a',cancelled,composer:''}),{restore:'a',unsaved:['b','c']});
  assert.deepEqual(unsavedTagRecovery({failedTag:'a',cancelled,composer:'typing'}),{restore:null,unsaved:['a','b','c']});
  assert.deepEqual(unsavedTagRecovery({failedTag:null,cancelled,composer:''}),{restore:'b',unsaved:['c']},'a failed removal restores the first cancelled add');
  assert.deepEqual(unsavedTagRecovery({failedTag:'a',cancelled,composer:'',restorable:false}),{restore:null,unsaved:['a','b','c']});
  assert.equal(unsavedTagMessage('Conflict.',['b','c']),'Conflict. Not saved: “b”, “c”.');
  assert.equal(unsavedTagMessage('Conflict.',[]),'Conflict.');
});
