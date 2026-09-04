import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'DataPlatform',
    component: () => import('../views/DataPlatform.vue'),
    meta: { title: '数据平台' }
  },
  {
    path: '/reasoning',
    name: 'Reasoning',
    component: () => import('../views/ReasoningV3.vue'),
    meta: { title: '智能推理' }
  },
  {
    path: '/records',
    name: 'Records',
    component: () => import('../views/Records.vue'),
    meta: { title: '操作记录' }
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('../views/ProfilePage.vue'),
    meta: { title: '修改个人信息' }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

export default router
