import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
// 自动导入插件 (让你少写 import)
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import fs from 'node:fs'
import crypto from 'node:crypto'

// dev-only: 本地起前端时不依赖门户 SSO 也能拿到数据。
// 子服务后端从 Cookie yx_token 验签, 而手机/IP 访问不会带 localhost 的门户 cookie,
// 导致每个接口 401 → 前端全局拦截器跳门户 → 死循环(页面反复闪烁)。
// 这里用与子服务相同的密钥手签一个 dev JWT, 让 vite proxy 转发时注入 Cookie,
// 后端验签通过即返回真实数据。仅 dev 生效, build/prod 完全不受影响。
const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..') // platforms/compute/frontend -> 仓库根

function loadPortalSecret() {
  const p = resolve(REPO_ROOT, '.env')
  if (fs.existsSync(p)) {
    for (const line of fs.readFileSync(p, 'utf-8').split('\n')) {
      const s = line.trim()
      if (!s || s.startsWith('#') || !s.includes('=')) continue
      const idx = s.indexOf('=')
      const k = s.slice(0, idx).trim()
      const v = s.slice(idx + 1).trim().replace(/^["']|["']$/g, '')
      if (k === 'PORTAL_SECRET_KEY') return v
    }
  }
  return 'yunxi-portal-secret-2026-change-me'
}

function signDevJwt(secret) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url')
  const header = b64({ alg: 'HS256', typ: 'JWT' })
  const now = Math.floor(Date.now() / 1000)
  const body = b64({ sub: '1', username: 'dev', role: 'Admin', iat: now, exp: now + 86400 * 365 })
  const sig = crypto.createHmac('sha256', secret).update(`${header}.${body}`).digest('base64url')
  return `${header}.${body}.${sig}`
}

const DEV_JWT = signDevJwt(loadPortalSecret())

function injectDevCookie(proxy) {
  proxy.on('proxyReq', (proxyReq) => {
    if (process.env.NODE_ENV === 'development') {
      proxyReq.setHeader('Cookie', 'yx_token=' + DEV_JWT)
    }
  })
}

// dev-only: 给 /api/v1/me 返回匿名用户(兜底, 避免个别路径漏注入 cookie 时仍跳门户)
const anonymousMeStubCompute = {
  name: 'yunxi-compute-anonymous-me-stub',
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      const path = (req.url || '').split('?')[0]
      if (path === '/yunxi/compute/api/v1/me' || path === '/api/v1/me') {
        _res.statusCode = 200
        _res.setHeader('Content-Type', 'application/json; charset=utf-8')
        _res.end(JSON.stringify({ role: 'Users', username: '', display_name: '' }))
        return
      }
      next()
    })
  },
}

// 把 /yunxi/compute(少末尾斜杠) 与 /yunxi、/yunxi/ 一律 302 重定向到 /yunxi/compute/,
// 让浏览器地址栏路径与 vite base 对齐, 避免前端路由匹配错位导致页面反复刷新。
const trailingSlashComputeRedirect = {
  name: 'yunxi-compute-trailing-slash-redirect',
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      const url = req.url || ''
      const queryIdx = url.indexOf('?')
      const path = queryIdx >= 0 ? url.slice(0, queryIdx) : url
      const query = queryIdx >= 0 ? url.slice(queryIdx) : ''
      if (path === '/yunxi/compute' || path === '/yunxi/' || path === '/yunxi') {
        res.statusCode = 302
        res.setHeader('Location', '/yunxi/compute/' + query)
        res.end()
        return
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
    trailingSlashComputeRedirect,
    anonymousMeStubCompute
  ],
  // 关键配置：开发服务器代理
  // 让前端 (5173) 能骗过浏览器，把请求发给后端 (8001)
  server: {
    host: true,
    hmr: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        configure: injectDevCookie,
        // rewrite: (path) => path.replace(/^\/api/, '') // 根据后端路由决定是否开启
      },
      '/yunxi/compute/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/yunxi\/compute/, ''),
        configure: injectDevCookie
      }
    }
  }
})
