'use strict';
// Resolve the visible native owner; retained and recovery documents can coexist.
async function retainedPage(application,{heading,title,timeout=90000}={}){
 const end=Date.now()+timeout;
 while(Date.now()<end){
  const url=await application.evaluate(({BrowserWindow})=>{
   const window=BrowserWindow.getAllWindows().find(item=>!item.isDestroyed());
   if(!window)return null;
   const content=window.contentView.children.map(view=>view.webContents).filter(Boolean).at(-1)||window.webContents;
   return content.isDestroyed()?null:content.getURL();
  });
  const page=application.windows().find(item=>item.url()===url);
  if(page){
   const titleReady=!title||(await page.title())===title+' · Disco';
   const headingReady=!heading||await page.getByRole('heading',{name:heading,exact:true}).isVisible().catch(()=>false);
   if(titleReady&&headingReady&&/^http:\/\/127\.0\.0\.1:\d+\//.test(url))return page;
   if(headingReady&&heading&&url?.startsWith('file:')&&url.endsWith('/recovery.html'))return page;
  }
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw new Error('Visible owned document did not reach expected title/heading');
}
async function showSidebar(page){
 const show=page.getByRole('button',{name:'Show sidebar',exact:true});
 if(await show.isVisible())await show.click();
}
module.exports={retainedPage,showSidebar};
