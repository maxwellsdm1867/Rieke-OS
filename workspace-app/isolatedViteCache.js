import {mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

// Every Vite server owns its cache, even when dependencies come from a copy.
// Vite can finish cache writes after close(); retain ownership until process exit.
const owned = new Set();
process.once('exit', () => {
  for (const directory of owned) rmSync(directory, {recursive:true, force:true});
});
export function isolatedViteCache() {
  const directory = mkdtempSync(join(tmpdir(), 'rieke-vite-'));
  owned.add(directory);
  return {directory};
}
