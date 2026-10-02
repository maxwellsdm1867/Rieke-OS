import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import {spawnSync} from 'node:child_process';

test('each server cache stays private through late writes and is removed at process exit', () => {
  const helper = new URL('./test-support/isolatedVite.js', import.meta.url).href;
  const root = new URL('..', import.meta.url).pathname;
  const script = `import assert from 'node:assert/strict';
    import {existsSync, writeFileSync} from 'node:fs';
    import {join} from 'node:path';
    import {createServer} from ${JSON.stringify(helper)};
    const options={root:${JSON.stringify(root)},configFile:false,
      cacheDir:'/tmp/rieke-shared-cache-must-not-be-used',logLevel:'silent',
      server:{middlewareMode:true},appType:'custom'};
    const a=await createServer(options), b=await createServer(options);
    assert.notEqual(a.config.cacheDir,b.config.cacheDir);
    assert.notEqual(a.config.cacheDir,options.cacheDir);
    assert.equal(a.config.server.ws,false);
    await a.close(); await b.close();
    assert.ok(existsSync(a.config.cacheDir));
    setImmediate(()=>writeFileSync(join(a.config.cacheDir,'late-write.json'),'{}'));
    console.log(JSON.stringify([a.config.cacheDir,b.config.cacheDir]));`;
  const child=spawnSync(process.execPath,['--input-type=module','-e',script],
    {encoding:'utf8',timeout:10000});
  assert.equal(child.status,0,child.stderr);
  const paths=JSON.parse(child.stdout.trim());
  assert.notEqual(paths[0],paths[1]);
  for(const path of paths)assert.equal(existsSync(path),false);
});
