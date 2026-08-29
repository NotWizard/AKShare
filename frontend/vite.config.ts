import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// Dev: proxy /api → FastAPI backend (:8000). Prod: reverse-proxy handles it.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // VITE_API_TARGET 覆盖：worktree/并行开发时指向另一个后端端口（如 :8001）
      '/api': { target: process.env.VITE_API_TARGET || 'http://localhost:8000', changeOrigin: true },
    },
  },
  preview: {
    strictPort: true,
  },
  build: {
    rollupOptions: {
      output: {
        // Split echarts into its own vendor chunk (function form preserves
        // tree-shaking — only the modules we actually import end up bundled,
        // unlike the object form which pulls the full package entry).
        manualChunks(id) {
          if (
            id.includes('node_modules/echarts') ||
            id.includes('node_modules/vue-echarts')
          ) {
            return 'vendor-echarts'
          }
        },
      },
    },
  },
})
