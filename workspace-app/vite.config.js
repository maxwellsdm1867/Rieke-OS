import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import {isolatedViteCache} from './isolatedViteCache.js';
const cache = isolatedViteCache();
// Keep prior hashed chunks available to tabs still open during local rebuilds.
// Keep the browser's Host aligned with Origin for native same-origin app writes.
export default defineConfig({ cacheDir:cache.directory, plugins: [react()], build: {emptyOutDir:false}, server: {proxy: {'/api': {target: 'http://127.0.0.1:8766', changeOrigin: false}}} });
