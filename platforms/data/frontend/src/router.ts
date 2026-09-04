import { createRouter, createWebHistory } from 'vue-router'

import DashboardPage from './views/DashboardPage.vue'
import DatasetPage from './views/DatasetPage.vue'
import PipelinePage from './views/PipelinePage.vue'
import ProcessingLogPage from './views/ProcessingLogPage.vue'
import ProfilePage from './views/ProfilePage.vue'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', name: 'dashboard', component: DashboardPage },
    { path: '/pipeline', name: 'pipeline', component: PipelinePage },
    { path: '/logs', name: 'logs', component: ProcessingLogPage },
    { path: '/datasets', name: 'datasets', component: DatasetPage },
    { path: '/profile', name: 'profile', component: ProfilePage },
  ],
})
