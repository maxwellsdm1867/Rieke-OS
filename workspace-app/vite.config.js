import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// Keep prior hashed chunks available to tabs still open during local rebuilds.
export default defineConfig({ plugins: [react()], build: {emptyOutDir:false}, server: {proxy: {'/api': 'http://127.0.0.1:8766'}} });
