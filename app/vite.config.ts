import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `vite build --mode webdemo` (pnpm build:web) makes the static web demo: relative asset URLs so it can
// live under any path (e.g. GitHub Pages at /FinHub/), its own output folder, and the demo flag.
export default defineConfig(({ mode }) => {
  const webDemo = mode === 'webdemo'
  return {
    plugins: [react()],
    clearScreen: false,
    base: webDemo ? './' : '/',
    // Tauri expects a fixed dev port; the backend's CORS allow-list matches it.
    // Ignore src-tauri: watching Rust build output crashes Vite with EBUSY on Windows while linking.
    server: { port: 1420, strictPort: true, host: '127.0.0.1', watch: { ignored: ['**/src-tauri/**'] } },
    envPrefix: ['VITE_', 'TAURI_ENV_'],
    define: { 'import.meta.env.VITE_FINHUB_WEB_DEMO': JSON.stringify(webDemo ? '1' : '') },
    build: { target: 'es2022', outDir: webDemo ? 'dist-web' : 'dist' },
  }
})
