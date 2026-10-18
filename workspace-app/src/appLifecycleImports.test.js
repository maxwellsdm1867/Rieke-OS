import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

// App.jsx calls desktopLifecycle helpers inline; a name that is used but not
// imported only fails at runtime (browser project switch threw ReferenceError).
test('App.jsx imports every desktopLifecycle export it calls',()=>{
 const app=readFileSync(new URL('./App.jsx',import.meta.url),'utf8');
 const lifecycle=readFileSync(new URL('./desktopLifecycle.js',import.meta.url),'utf8');
 const exported=[...lifecycle.matchAll(/export\s+(?:async\s+)?(?:function|const)\s+(\w+)/g)].map(match=>match[1]);
 const imported=new Set([...app.matchAll(/import\s*\{([^}]*)\}\s*from\s*'\.\/desktopLifecycle\.js'/g)].flatMap(match=>match[1].split(',').map(name=>name.trim().split(/\s+as\s+/).pop())));
 const missing=exported.filter(name=>!imported.has(name)&&new RegExp(`(?<![\\w.])${name}\\s*\\(`).test(app));
 assert.deepEqual(missing,[]);
});
