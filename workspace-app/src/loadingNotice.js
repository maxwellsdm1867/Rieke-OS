// Delay entry, bridge short metadata-to-trace handoffs, never shift the layout.
export function scheduleLoadingNotice(pending,show,{setTimer=setTimeout,clearTimer=clearTimeout}={}){
  const timer=setTimer(()=>show(!!pending),pending?220:120);
  return ()=>clearTimer(timer);
}
