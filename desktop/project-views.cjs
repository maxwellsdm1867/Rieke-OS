'use strict';
// Retained documents own presentation only. Main supplies authenticated bindings,
// draft acknowledgment and lifecycle admission; no process authority lives here.
const bindingKey = binding => JSON.stringify([binding.project_uuid,binding.project_path,binding.session_id,binding.pid,binding.created_at,binding.origin]);
class ProjectViews {
  constructor({window,createView,prepare,onRegister=()=>{},onDispose=()=>{},onActivate=()=>{},admit=()=>true,limit=3}) {
    Object.assign(this,{window,createView,prepare,onRegister,onDispose,onActivate,admit,limit});
    this.owners=new Map();this.active=null;this.sequence=0;this.generation=0;this.chain=Promise.resolve();
  }
  activate(binding,url) {
    const generation=this.generation;
    const operation=this.chain.catch(()=>{}).then(()=>this.open(binding,url,generation));
    this.chain=operation;return operation;
  }
  activateRetained(owner,authorize) {
    const generation=this.generation,key=bindingKey(owner.binding);
    const check=()=>{
      if(generation!==this.generation||!this.admit())throw Error('Project activation was cancelled.');
      if(bindingKey(owner.binding)!==key)throw Error('The retained project binding changed.');
      if(owner.closing)throw Error('This project is closing.');
      if(owner.draftUnavailable)throw Error('This project renderer stopped. Quit and reopen Disco to recover its last saved view.');
      const current=this.owners.get(key);
      if(current!==owner){
        if(!current&&owner.retired==='evicted')return false;
        throw Error('The retained project owner changed.');
      }
      if(owner.isDestroyed())throw Error('This project renderer stopped. Quit and reopen Disco to recover its last saved view.');
      return true;
    };
    const operation=this.chain.catch(()=>{}).then(async()=>{
      // The caller's admission callback runs in the same queue as attachment.
      // Even a clean eviction must not bypass its caller/lifecycle fence.
      check();
      await authorize();
      if(!check())return {activated:false};
      return this.show(owner);
    });
    this.chain=operation;return operation;
  }
  async open(binding,url,generation) {
    if(generation!==this.generation)throw Error('Project activation was cancelled.');
    if(!this.admit())throw Error('Project activation is unavailable.');
    const key=bindingKey(binding);let owner=this.owners.get(key);
    if(owner?.closing)throw Error('This project is closing.');
    if(owner?.draftUnavailable)throw Error('This project renderer stopped. Quit and reopen Disco to recover its last saved view.');
    if(owner?.isDestroyed()){this.dispose(owner);owner=null;}
    if(!owner){
      const view=this.createView();
      owner={view,webContents:view.webContents,parentWindow:this.window,binding:{...binding},active:false,closing:false,draftUnavailable:false,isDestroyed:()=>view.webContents.isDestroyed()};
      this.owners.set(key,owner);this.onRegister(owner);
      try{await owner.webContents.loadURL(url);}catch(error){this.dispose(owner);throw error;}
      if(generation!==this.generation||!this.admit()||this.owners.get(key)!==owner)throw Error('Project activation was cancelled.');
    }
    return this.show(owner);
  }
  async show(owner){
    if(this.active!==owner){
      const previous=this.active;
      if(previous){previous.active=false;this.window.contentView.removeChildView(previous.view);if(!previous.isDestroyed())previous.webContents.send('desktop:project-visibility',{visible:false});}
      this.active=owner;owner.active=true;owner.used=++this.sequence;
      this.window.contentView.addChildView(owner.view);this.resize();
      owner.webContents.send('desktop:project-visibility',{visible:true});owner.webContents.focus();
      await this.onActivate(owner);
    }
    if(!this.trimming)this.trimming=this.trim().finally(()=>{this.trimming=null;});
    return {activated:true};
  }
  resize(){if(this.active&&!this.active.isDestroyed()){const [width,height]=this.window.getContentSize();this.active.view.setBounds({x:0,y:0,width,height});}}
  find({projectUuid,path}){return [...this.owners.values()].filter(owner=>owner.binding.project_uuid===projectUuid&&owner.binding.project_path===path);}
  async prepareClose(identity){
    const owners=this.find(identity);owners.forEach(owner=>{owner.closing=true;});
    let result;try{result=await this.prepare(owners);}catch(error){owners.forEach(owner=>{owner.closing=false;this.resume(owner);});throw error;}
    if(!result.ready){owners.forEach(owner=>{owner.closing=false;this.resume(owner);});throw Error(result.reason||'Project view could not be saved.');}
    return result;
  }
  resume(owner){if(!owner.isDestroyed())owner.webContents.send('desktop:project-resume',{});}
  cancelClose(identity){this.find(identity).forEach(owner=>{owner.closing=false;this.resume(owner);});}
  dispose(owner,{evicted=false}={}){
    owner.retired=evicted?'evicted':'closed';
    if(this.active===owner){this.active=null;owner.active=false;if(!this.window.isDestroyed())this.window.contentView.removeChildView(owner.view);}
    this.owners.delete(bindingKey(owner.binding));this.onDispose(owner);
    if(!owner.isDestroyed())owner.webContents.close();
  }
  cancelActivations(){this.generation++;this.suspend();}
  suspend(owner=this.active){
    if(!owner)return;
    if(this.active===owner){this.active=null;owner.active=false;if(!this.window.isDestroyed())this.window.contentView.removeChildView(owner.view);}
    owner.active=false;
    if(!owner.isDestroyed()&&!owner.draftUnavailable)owner.webContents.send('desktop:project-visibility',{visible:false});
  }
  clear(){for(const owner of [...this.owners.values()])this.dispose(owner);}
  async trim(){
    for(const owner of [...this.owners.values()].filter(item=>item!==this.active&&!item.closing).sort((a,b)=>(a.used||0)-(b.used||0))){
      if(this.owners.size<=this.limit)return;
      // A failed or busy draft is a soft-cap exception, never permission to lose it.
      try{const result=await this.prepare([owner]);if(result.ready&&owner!==this.active&&!owner.closing)this.dispose(owner,{evicted:true});else this.resume(owner);}catch{this.resume(owner);}
    }
  }
}
module.exports={ProjectViews,bindingKey};
