import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tauri expects a fixed dev port; the backend's CORS allow-list matches it.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true, host: '127.0.0.1' },
  envPrefix: ['VITE_', 'TAURI_ENV_'],
  build: { target: 'es2022' },
})
