import {createServer as createViteServer} from 'vite';
import {isolatedViteCache} from '../../isolatedViteCache.js';

export async function createServer(options = {}) {
  const cache = isolatedViteCache();
  // Server closure does not prove Vite's detached filesystem work has drained.
  // The process owns this unique cache through natural exit, including failures.
  return createViteServer({...options, cacheDir:cache.directory,
    server:{...options.server, ws:false}});
}
