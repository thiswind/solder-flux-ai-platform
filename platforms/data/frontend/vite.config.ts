import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

// 自动把不带末尾斜杠的 /yunxi/data 重定向到 /yunxi/data/,
// 以避免 base 配置差异造成的提示页卡住。
function trailingSlashRedirect(): Plugin {
  return {
    name: 'yunxi-data-trailing-slash-redirect',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url || ''
        if (url === '/yunxi/data') {
          req.url = '/yunxi/data/'
        }
        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  base: '/yunxi/data/',
  plugins: [vue(), trailingSlashRedirect()],
  server: {
    // 5174 专供数据管理平台，避免与智能计算平台前端(5173)端口冲突
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/yunxi/data/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/yunxi\/data/, '')
      },
    },
  },
})
