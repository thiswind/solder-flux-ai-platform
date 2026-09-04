import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
// 引入通用字体文件 (Naive UI 推荐)
import 'vfonts/Lato.css'
// 引入全局样式
import './style.css'

// SSO：后端 API 返回 401（未登录/令牌失效）时，跳回统一门户登录并携带回跳地址
import axios from 'axios'
import { fetchRole } from './role'
const PORTAL_LOGIN = '/yunxi/'
axios.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response && error.response.status === 401) {
      const redirect = encodeURIComponent(window.location.origin + window.location.pathname)
      window.location.href = PORTAL_LOGIN + '?redirect=' + redirect
    }
    return Promise.reject(error)
  }
)

const app = createApp(App)

// 挂载路由
app.use(router)

app.mount('#app')

// 拉取当前用户角色，用于前端按钮权限控制（Admin 专属操作显隐）
fetchRole()