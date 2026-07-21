import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev 期把 /api 代理到 FastAPI Agent 服务(接真后端时用;当前前端走 mock,不影响)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api/chat': { target: 'http://localhost:8000', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') },
      '/api/tickets': { target: 'http://localhost:8080', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') },
    },
  },
})
