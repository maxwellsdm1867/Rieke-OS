import {createServer as createViteServer} from 'vite';
import {isolatedViteCache} from '../../isolatedViteCache.js';

export async function createServer(options = {}) {
  const cache = isolatedViteCache();
  try {
    const server = await createViteServer({...options, cacheDir:cache.directory,
      server:{...options.server, ws:false}});
    const close = server.close.bind(server);
    server.close = async () => {await close(); cache.dispose();};
    return server;
  } catch (error) {
    cache.dispose();
    throw error;
  }
}
