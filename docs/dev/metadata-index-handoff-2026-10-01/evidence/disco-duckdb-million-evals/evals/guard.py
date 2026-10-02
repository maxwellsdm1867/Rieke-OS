"""Guard only an explicitly launched owned experiment process and its children."""
import argparse,json,subprocess,time
from pathlib import Path
import psutil
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--seconds',type=int,default=300)
p.add_argument('command',nargs=argparse.REMAINDER)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
command=a.command[1:] if a.command[:1]==['--'] else a.command
start=time.monotonic();report={'command':command,'samples':[],'aborted':False};child=None

def stop_owned():
 if child is None or child.poll() is not None:return
 try:children=psutil.Process(child.pid).children(recursive=True)
 except (psutil.Error,OSError):children=[]
 for owned in children:
  try:owned.terminate()
  except psutil.Error:pass
 child.terminate()
 try:child.wait(timeout=3)
 except subprocess.TimeoutExpired:child.kill();child.wait()
 for owned in children:
  try:owned.kill()
  except psutil.Error:pass

try:
 # Fail before launch if sandbox permissions prevent the required guard.
 psutil.Process().children(recursive=True)
 psutil.virtual_memory();psutil.disk_usage(a.out)
 with (a.out/'worker.log').open('w') as log:
  child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
  report['owned_pid']=child.pid;proc=psutil.Process(child.pid)
  while child.poll() is None:
   try:processes=[proc]+proc.children(recursive=True);rss=sum(x.memory_info().rss for x in processes if x.is_running())
   except psutil.NoSuchProcess:rss=0
   available=psutil.virtual_memory().available;free=psutil.disk_usage(a.out).free;elapsed=time.monotonic()-start
   report['samples'].append({'seconds':elapsed,'tree_rss_bytes':rss,'available_ram_bytes':available,'free_disk_bytes':free})
   reason=('time cap' if elapsed>a.seconds else 'process tree RSS cap' if rss>1536*2**20 else 'available RAM floor' if available<768*2**20 else 'free disk floor' if free<3*2**30 else None)
   if reason:report.update(aborted=True,reason=reason);stop_owned();break
   time.sleep(.5)
  report['exit_code']=child.wait()
except BaseException as error:
 report.update(aborted=True,reason='Supervisor failure: '+str(error));stop_owned()
finally:
 report['seconds']=time.monotonic()-start
 report['passed']=not report['aborted'] and report.get('exit_code')==0
 (a.out/'guard.json').write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(0 if report['passed'] else 1)
