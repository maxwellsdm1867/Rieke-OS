import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

test('servers with identical roots and requested caches own distinct disposable caches', async () => {
  const options = {root:fileURLToPath(new URL('..', import.meta.url)), configFile:false,
    cacheDir:'/tmp/rieke-shared-cache-must-not-be-used', logLevel:'silent',
    server:{middlewareMode:true}, appType:'custom'};
  const a = await createServer(options);
  const b = await createServer(options);
  try {
    assert.notEqual(a.config.cacheDir, b.config.cacheDir);
    assert.notEqual(a.config.cacheDir, options.cacheDir);
    assert.equal(a.config.server.ws, false);
    assert.ok(existsSync(a.config.cacheDir));
    await a.close();
    assert.equal(existsSync(a.config.cacheDir), false);
    assert.ok(existsSync(b.config.cacheDir));
  } finally {
    await a.close();
    await b.close();
  }
  assert.equal(existsSync(b.config.cacheDir), false);
});
