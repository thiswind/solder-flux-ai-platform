import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { router } from './router'
import { fetchRole } from './role'

createApp(App).use(router).mount('#app')

// 拉取当前用户角色，用于前端按钮/菜单权限控制（Admin 专属操作显隐）
fetchRole()
