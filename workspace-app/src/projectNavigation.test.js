import test from 'node:test';
import assert from 'node:assert/strict';
import {orderedProjectRecords,projectKey,projectBootstrap,isCurrentProject} from './projectNavigation.js';
import {reorderIds} from './ordering.js';

test('clicking another current project preserves the folder order, including native copies sharing UUIDs',()=>{
 const projects=[{path:'/a',uuid:'same',current:true},{path:'/b',uuid:'same',current:false},{path:'/c',uuid:'c'}];
 const order=reorderIds(projects.map(projectKey),'/b','/a','before');
 const switched=projects.map(project=>({...project,current:project.path==='/b'}));
 assert.deepEqual(orderedProjectRecords(switched,order).map(projectKey),['/b','/a','/c']);
 assert.deepEqual(orderedProjectRecords(projects,order).map(projectKey),['/b','/a','/c']);
 assert.deepEqual(projects.map(projectKey),['/a','/b','/c']);
 assert.deepEqual(orderedProjectRecords([...switched,{path:'/d',uuid:'d'}],order).map(projectKey),['/b','/a','/c','/d']);
});
test('first render reads the server inventory, with safe fallbacks for missing or malformed bootstrap',()=>{
 const data={current_project_uuid:'a',projects:[{uuid:'a',name:'Alpha',path:'/a'}]};
 const document={getElementById:()=>({textContent:JSON.stringify(data)})};
 assert.deepEqual(projectBootstrap(document),data);
 for(const text of ['{broken','null','{"projects":[{}]}'])assert.equal(projectBootstrap({getElementById:()=>({textContent:text})}),null);
 assert.equal(projectBootstrap({getElementById:()=>null}),null);
});
test('current project uses the active canonical path and identity, never a shared UUID alone',()=>{
 const projects=[{path:'/a',uuid:'same',current:false},{path:'/b',uuid:'same',current:true}];
 const registry={current_project_uuid:'same',projects};
 assert.deepEqual(projects.map(project=>isCurrentProject(project,registry)),[false,true]);
 assert.equal(isCurrentProject({...projects[1],uuid:'different'},registry),false);
 assert.equal(isCurrentProject(projects[1],{...registry,current_project_uuid:null}),false);
 assert.equal(isCurrentProject(projects[0],{...registry,projects:projects.map(project=>({...project,current:false}))}),false);
});
