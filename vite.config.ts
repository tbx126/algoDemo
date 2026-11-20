import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // 固定 IPv4，避免 localhost 只解析到 ::1 时预览工具连不上
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ['**/backend/**'],
    },
    proxy: {
      '/real-api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
