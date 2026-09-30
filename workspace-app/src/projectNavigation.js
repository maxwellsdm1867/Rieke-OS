export function projectKey(project){return project.path||project.uuid;}
export function orderedProjectRecords(projects,order){
 if(!Array.isArray(order))return projects;
 const rank=new Map(order.map((key,index)=>[key,index]));
 return projects.map((project,index)=>({project,index})).sort((a,b)=>(rank.get(projectKey(a.project))??order.length+a.index)-(rank.get(projectKey(b.project))??order.length+b.index)).map(item=>item.project);
}
export function projectBootstrap(document=globalThis.document){
 try{
  const data=JSON.parse(document?.getElementById('rieke-projects-bootstrap')?.textContent||'null');
  return data&&Array.isArray(data.projects)&&data.projects.every(project=>typeof project.path==='string'&&typeof project.uuid==='string'&&typeof project.name==='string')?data:null;
 }catch{return null;}
}
