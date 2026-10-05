'use strict';
// Read-only process evidence. No signal, kill, stop-service or cleanup primitive.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {createHash} = require('node:crypto');
function run(file,args,options={}) {
  const {timeout=10000,maxBuffer=1024*1024,input='',...safeOptions}=options;
  return new Promise((resolve,reject)=>{
    const child=spawn(file,args,{...safeOptions,stdio:['pipe','pipe','pipe']});
    let stdout='',stderr='',bytes=0,failed=false;
    const fail=error=>{if(!failed){failed=true;clearTimeout(timer);reject(error);}};
    const timer=setTimeout(()=>fail(Error('Owned helper deadline; process not signalled, retain evidence')),timeout);
    const receive=(chunk,isError)=>{
      if(failed)return; // Continue draining streams, without storing more output.
      bytes+=chunk.length;
      if(bytes>maxBuffer)return fail(Error('Owned helper output bound; process not signalled'));
      if(isError)stderr+=chunk.toString();else stdout+=chunk.toString();
    };
    child.stdout.on('data',chunk=>receive(chunk,false));child.stderr.on('data',chunk=>receive(chunk,true));
    child.on('error',fail);
    child.on('close',code=>{
      clearTimeout(timer);if(failed)return;
      if(code!==0)return fail(Error(`Owned helper exited ${code}: ${stderr.slice(-2000)}`));
      resolve({stdout,stderr});
    });
    child.stdin.on('error',fail);child.stdin.end(input);
  });
}

const ANCHOR = String.raw`
import json, os, sys, psutil
pid, parent, executable = sys.argv[1:]
p = psutil.Process(int(pid))
assert p.ppid() == int(parent) and p.uids().real == os.getuid()
assert os.path.realpath(p.exe()) == os.path.realpath(executable)
print(json.dumps({'pid':p.pid,'created':p.create_time()}))
`;
const PROBE = String.raw`
import json, os, sys, psutil
bundle, home, preferences, root_pid, root_created = sys.argv[1:]
root_pid, root_created = int(root_pid), float(root_created)
bundle = os.path.realpath(bundle)
if root_pid:
    try:
        root = psutil.Process(root_pid)
        assert root.create_time() == root_created, 'Root PID identity changed'
        assert root.uids().real == os.getuid() and os.path.realpath(root.exe()).startswith(bundle + os.sep)
    except psutil.NoSuchProcess:
        pass
rows = []
for process in psutil.process_iter(['pid', 'ppid', 'create_time', 'exe']):
    try:
        item = process.info
        exe = os.path.realpath(item['exe'] or '')
        if item['pid'] != os.getpid() and exe.startswith(bundle + os.sep):
            rows.append((process, item, exe))
    except psutil.NoSuchProcess:
        pass
owned = {item['pid'] for _, item, _ in rows}
# Discover children without exporting unrelated process metadata.
changed = True
while changed:
    changed = False
    for process in psutil.process_iter(['pid', 'ppid', 'create_time', 'exe']):
        try:
            item = process.info
            if item['pid'] != os.getpid() and item['ppid'] in owned and item['pid'] not in owned:
                exe = os.path.realpath(item['exe'] or '')
                assert exe.startswith(bundle + os.sep), 'Unexpected descendant executable; environment not read'
                rows.append((process, item, exe))
                owned.add(item['pid']); changed = True
        except psutil.NoSuchProcess:
            pass
result = []
for process, item, exe in rows:
    try:
        assert process.create_time() == item['create_time'], 'PID reused before environment observation'
        assert process.uids().real == os.getuid() and os.path.realpath(process.exe()) == exe
        env = process.environ()
        # Return only explicit isolation paths, never credentials or command lines.
        isolation = {key: env.get(key) for key in ('HOME', 'RIEKE_PREFERENCES_DIR')}
        ports, sockets, listeners = [], [], []
        for connection in process.net_connections(kind='all'):
            if connection.status == psutil.CONN_LISTEN and connection.laddr:
                if isinstance(connection.laddr, str): sockets.append(connection.laddr)
                else:
                    ports.append(connection.laddr.port)
                    listeners.append({'host':connection.laddr.ip,'port':connection.laddr.port})
            elif isinstance(connection.laddr, str) and connection.laddr:
                sockets.append(connection.laddr)
        result.append(dict(pid=item['pid'], ppid=item['ppid'], created=item['create_time'],
            executable=exe, isolation=isolation, ports=sorted(set(ports)), listeners=listeners, sockets=sorted(set(sockets))))
    except psutil.NoSuchProcess:
        pass
print(json.dumps(result))
`;
const DEBUG_LISTENERS = String.raw`
import json, os, sys, psutil
pid, created, executable, encoded = sys.argv[1:]
p = psutil.Process(int(pid))
assert p.create_time() == float(created) and p.uids().real == os.getuid()
assert os.path.realpath(p.exe()) == os.path.realpath(executable)
expected = json.loads(encoded)
assert len(expected) == 2 and len({row['port'] for row in expected}) == 2
assert all(row['host'] in ('127.0.0.1','::1') and 0 < row['port'] < 65536 for row in expected)
ports = {row['port'] for row in expected}
listeners = [c for c in p.net_connections(kind='tcp') if c.status == psutil.CONN_LISTEN and c.laddr.port in ports]
assert all(c.laddr.ip in ('127.0.0.1','::1') for c in listeners), 'Debug listener is not loopback'
actual = {(c.laddr.ip,c.laddr.port) for c in listeners}
assert all((row['host'],row['port']) in actual for row in expected), 'Exact endpoint address must belong to owned root'
assert p.create_time() == float(created) and p.uids().real == os.getuid()
assert os.path.realpath(p.exe()) == os.path.realpath(executable)
print(json.dumps({'pid':p.pid,'created':p.create_time(),'listeners':expected,'loopback_only':True}))
`;
const EXIT_PROBE = String.raw`
import json, sys, psutil
records = json.load(sys.stdin)
alive = []
for row in records:
    try:
        p = psutil.Process(row['pid'])
        if p.create_time() == row['created']:
            alive.append({'pid': row['pid'], 'created': row['created']})
    except psutil.NoSuchProcess:
        pass
print(json.dumps(alive))
`;

function within(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative));
}

class OwnedProcesses {
  constructor({python, bundle, home, preferences, env}) {
    Object.assign(this, {python, bundle, home, preferences, env});
    this.records = new Map(); this.ports = new Set(); this.listeners=new Map(); this.sockets = new Set();
    this.verifiedExternalSockets = new Set();
    this.rootPid = 0; this.rootCreated=0; this.errors = []; this.timer = null; this.pending = null;
  }
  async capture() {
    if(this.pending)return this.pending;
    this.pending=this.captureOnce();
    try{return await this.pending;}finally{this.pending=null;}
  }
  async captureOnce() {
    const {stdout} = await run(this.python, ['-I', '-B', '-c', PROBE, this.bundle, this.home,
      this.preferences, String(this.rootPid),String(this.rootCreated)], {env:this.env, timeout:10000, maxBuffer:4*1024*1024});
    const rows = JSON.parse(stdout);
    for (const row of rows) {
      assert.ok(row.created > 0 && Number.isInteger(row.pid));
      assert.ok(within(this.bundle, row.executable), 'Owned descendant executable escaped bundle');
      assert.equal(row.isolation.HOME, this.home, 'Actual owned child HOME escaped fixture');
      const effective=row.isolation.RIEKE_PREFERENCES_DIR??path.join(row.isolation.HOME,'.rieke-os');
      assert.equal(effective,this.preferences,'Actual effective child preferences escaped fixture');
      this.records.set(`${row.pid}:${row.created}`, row);
      for (const port of row.ports) this.ports.add(port);
      for(const listener of row.listeners)this.listeners.set(JSON.stringify(listener),listener);
      for (const socket of row.sockets) if (path.isAbsolute(socket)) {
        this.sockets.add(socket);
      }
    }
    return rows;
  }
  async verifyNativeSocket(project, projectUuid) {
    // macOS native MySQL uses a short /tmp path. Prove the exact binding;
    // never allow arbitrary /tmp sockets or read database credentials.
    const read=async name=>{
      const filename=path.join(project,'database',name),stat=await fs.lstat(filename);
      assert.ok(stat.isFile()&&!stat.isSymbolicLink()&&stat.uid===process.getuid());
      return JSON.parse(await fs.readFile(filename,'utf8'));
    };
    const descriptor=await read('service.json'),runtime=await read('native-runtime.json');
    assert.equal(descriptor.project_uuid,projectUuid);assert.equal(runtime.project_uuid,projectUuid);
    assert.equal(runtime.instance_uuid,descriptor.instance_uuid);assert.equal(runtime.project_path,project);
    const token=createHash('sha256').update(project+descriptor.instance_uuid).digest('hex').slice(0,24);
    const directory=`/tmp/rieke-mysql-${process.getuid()}-${token}`;
    assert.equal(runtime.socket,path.join(directory,'mysql.sock'));
    const stat=await fs.lstat(directory);
    assert.ok(stat.isDirectory()&&!stat.isSymbolicLink()&&stat.uid===process.getuid()&&(stat.mode&0o777)===0o700);
    assert.ok([...this.records.values()].some(row=>row.pid===runtime.pid&&row.created===runtime.process_created&&row.executable===runtime.executable));
    for(const filename of [runtime.socket,path.join(await fs.realpath(directory),'mysql.sock')]) {
      this.verifiedExternalSockets.add(filename);this.sockets.add(filename);
    }
  }
  async start(pid) {
    const {stdout}=await run(this.python,['-I','-B','-c',ANCHOR,String(pid),String(process.pid),path.join(this.bundle,'Contents/MacOS/Disco')],{env:this.env});
    const anchor=JSON.parse(stdout);this.rootPid=anchor.pid;this.rootCreated=anchor.created;
    this.timer = setInterval(() => {
      if(this.pending)return; // Skip overlapping samples; never queue behind probes.
      void this.capture().catch(error => {clearInterval(this.timer);this.errors.push(error.message);});
    }, 1000);
    this.timer.unref();
  }
  async verifyDebugListeners(listeners) {
    assert.equal(listeners.length,2);assert.equal(new Set(listeners.map(row=>row.port)).size,2);
    const {stdout}=await run(this.python,['-I','-B','-c',DEBUG_LISTENERS,String(this.rootPid),String(this.rootCreated),
      path.join(this.bundle,'Contents/MacOS/Disco'),JSON.stringify(listeners)],{env:this.env});
    const proof=JSON.parse(stdout);assert.equal(proof.pid,this.rootPid);assert.equal(proof.created,this.rootCreated);
    assert.equal(proof.loopback_only,true);assert.deepEqual(proof.listeners,listeners);
    for(const listener of listeners){this.ports.add(listener.port);this.listeners.set(JSON.stringify(listener),listener);}
    return proof;
  }
  async stopObservation() {clearInterval(this.timer);if(this.pending)await this.pending;}
  async assertExited() {
    await this.stopObservation();
    assert.deepEqual(this.errors, [], 'Process observation incomplete');
    // Pass only PID/creation identities as a file-free stdin payload.
    const input = JSON.stringify([...this.records.values()].map(({pid,created}) => ({pid,created})));
    const {stdout}=await run(this.python,['-I','-B','-c',EXIT_PROBE],{env:this.env,input});
    const alive=JSON.parse(stdout);
    assert.deepEqual(alive, [], 'Recorded owned processes survived normal Quit');
    this.rootPid = 0;this.rootCreated=0;
    assert.deepEqual(await this.capture(), [], 'Unrecorded bundle processes survived normal Quit');
    for (const {host,port} of this.listeners.values()) {
      assert.ok(['127.0.0.1','::1'].includes(host),'Non-loopback owned listener; cleanup unproven');
      // Connection checks are read-only and never bind a port or send a request.
      const net = require('node:net');
      const listening = await new Promise((resolve,reject) => {
        const socket = net.createConnection({host,port});
        socket.once('connect',()=>{socket.destroy();resolve(true);});
        socket.once('error',error=>{socket.destroy();if(error.code==='ECONNREFUSED')resolve(false);else reject(error);});
        socket.setTimeout(1000,()=>{socket.destroy();reject(new Error('Owned port exit check timed out'));});
      });
      assert.equal(listening,false,'Previously owned port remains listening; no cleanup claim');
    }
    for (const socket of this.sockets) {
      assert.ok(within(path.dirname(this.home),socket)||this.verifiedExternalSockets.has(socket),'Unverified external socket; cleanup unproven');
      await assert.rejects(fs.lstat(socket), {code:'ENOENT'});
    }
    return {recorded_processes:this.records.size, ports:[...this.ports], listeners:[...this.listeners.values()], sockets_removed:this.sockets.size,
      pid_creation_time_verified:true, actual_child_preferences_verified:true};
  }
  snapshot() {return [...this.records.values()];}
}
module.exports = {OwnedProcesses, within, run};
