import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  base: '/yunxi/data/',
  plugins: [vue()],
  server: {
    // 5174 专供数据管理平台，避免与智能计算平台前端(5173)端口冲突
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
