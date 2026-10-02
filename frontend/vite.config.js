import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 18180,
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://localhost:18732',
    },
  },
})
