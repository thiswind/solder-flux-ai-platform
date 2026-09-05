import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
// 自动导入插件 (让你少写 import)
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'

// 自动把不带末尾斜杠的 /yunxi/compute 重定向到 /yunxi/compute/,
// 避免 base 带斜杠带来的英文提示页卡住浏览器。
const trailingSlashComputeRedirect = {
  name: 'yunxi-compute-trailing-slash-redirect',
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      const url = req.url || ''
      if (url === '/yunxi/compute') {
        req.url = '/yunxi/compute/'
      }
      next()
    })
  },
}

export default defineConfig({
  base: '/yunxi/compute/',
  plugins: [
    vue(),
    AutoImport({
      imports: [
        'vue',
        {
          'naive-ui': [
            'useDialog',
            'useMessage',
            'useNotification',
            'useLoadingBar'
          ]
        }
      ]
    }),
    Components({
      resolvers: [NaiveUiResolver()]
    }),
    trailingSlashComputeRedirect
  ],
  // 关键配置：开发服务器代理
  // 让前端 (5173) 能骗过浏览器，把请求发给后端 (8000)
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/api/, '') // 根据后端路由决定是否开启
      },
      '/yunxi/compute/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/yunxi\/compute/, '')
      }
    }
  }
})