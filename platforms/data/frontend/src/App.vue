<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <n-loading-bar-provider>
          <div class="app-container">
            <n-layout position="absolute">
              <n-layout-header bordered class="nav-header">
                <div class="logo">
                  <img src="./assets/logo.png" class="logo-icon" alt="Logo" />
                  <span class="logo-text">锡膏数据管理平台</span>
                </div>
                <n-menu mode="horizontal" :options="menuOptions" v-model:value="activeKey" class="nav-menu" />
                <n-button tertiary round size="medium" class="manual-btn" @click="downloadManual">
                  <template #icon>
                    <n-icon><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor"><path d="M21 5c-1.11-.35-2.33-.5-3.5-.5-1.95 0-4.05.4-5.5 1.5-1.45-1.1-3.55-1.5-5.5-1.5S2.45 4.9 1 6v14.65c0 .25.25.5.5.5.1 0 .15-.05.25-.05C3.1 20.45 5.05 20 6.5 20c1.95 0 4.05.4 5.5 1.5 1.35-.85 3.8-1.5 5.5-1.5 1.65 0 3.35.3 4.75 1.05.1.05.15.05.25.05.25 0 .5-.25.5-.5V6c-.6-.45-1.25-.75-2-1zm0 13.5c-1.1-.35-2.3-.5-3.5-.5-1.7 0-4.15.65-5.5 1.5V8c1.35-.85 3.8-1.5 5.5-1.5 1.2 0 2.4.15 3.5.5v11.5z"/></svg></n-icon>
                  </template>
                  使用说明书
                </n-button>
                <n-dropdown :options="userDropdownOptions" @select="handleUserAction" trigger="click">
                  <div class="user-avatar-trigger">
                    <n-avatar round :size="36" :style="{ backgroundColor: avatarColor }">
                      {{ userInitial }}
                    </n-avatar>
                    <span class="user-display-name">{{ displayName }}</span>
                    <n-icon class="dropdown-arrow"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor"><path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/></svg></n-icon>
                  </div>
                </n-dropdown>
              </n-layout-header>
              
              <n-layout has-sider position="absolute" :style="layoutStyle">
                <n-layout-content :content-style="contentStyle">
                  <router-view v-slot="{ Component }">
                    <transition name="fade" mode="out-in">
                      <component :is="Component" />
                    </transition>
                  </router-view>
                </n-layout-content>
              </n-layout>
              <nav class="mobile-tabbar">
                <RouterLink to="/" class="tab-item" :class="{ active: activeKey === 'dashboard' }">
                  <svg class="tab-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/></svg>
                  <span>系统总览</span>
                </RouterLink>
                <RouterLink to="/pipeline" class="tab-item" :class="{ active: activeKey === 'pipeline' }">
                  <svg class="tab-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"/></svg>
                  <span>上传文件</span>
                </RouterLink>
                <RouterLink to="/logs" class="tab-item" :class="{ active: activeKey === 'logs' }">
                  <svg class="tab-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14H7v-2h5v2zm5-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>
                  <span>处理日志</span>
                </RouterLink>
                <RouterLink to="/datasets" class="tab-item" :class="{ active: activeKey === 'datasets' }">
                  <svg class="tab-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
                  <span>数据来源</span>
                </RouterLink>
              </nav>
            </n-layout>
          </div>
        </n-loading-bar-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { h, ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  NLoadingBarProvider,
  NLayout,
  NLayoutHeader,
  NLayoutContent,
  NMenu,
  NIcon,
  NAvatar,
  NDropdown,
  NButton,
  createDiscreteApi
} from 'naive-ui'
import { useRouter } from 'vue-router'
import { roleState, fetchRole } from './role'

// 退出确认弹窗使用离散 API，避免根组件在自己模板里提供 provider 却在自己 setup 调用 useDialog 导致的注入报错
const { dialog } = createDiscreteApi(['dialog'])

const route = useRoute()
const router = useRouter()
const activeKey = ref<string | null>(null)

const isMobile = ref(false)
const handleResize = () => {
  isMobile.value = window.innerWidth <= 768
}

watch(route, (newRoute) => {
  if (newRoute.path === '/') activeKey.value = 'dashboard'
  else if (newRoute.path.startsWith('/pipeline')) activeKey.value = 'pipeline'
  else if (newRoute.path.startsWith('/logs')) activeKey.value = 'logs'
  else if (newRoute.path.startsWith('/datasets')) activeKey.value = 'datasets'
}, { immediate: true })

onMounted(() => {
  handleResize()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

const contentStyle = computed(() => ({
  padding: isMobile.value ? '12px 12px 76px' : '24px',
  backgroundColor: '#f5f7fa',
  overflow: 'auto'
}))

const layoutStyle = computed(() => ({
  top: isMobile.value ? '56px' : '72px',
  bottom: 0
}))

const themeOverrides = {
  common: {
    primaryColor: '#165DFF',
    primaryColorHover: '#4080FF',
    primaryColorPressed: '#0E42D2',
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
  },
  Layout: {
    headerColor: '#FFFFFF',
    headerBorderColor: '#E5E6EB'
  },
  Menu: {
    itemTextColor: '#4E5969',
    itemTextColorHover: '#165DFF',
    itemTextColorActive: '#FFFFFF',
    itemIconColor: '#4E5969',
    itemIconColorHover: '#165DFF',
    itemIconColorActive: '#FFFFFF',
    itemColorActive: '#165DFF',
    itemColorHover: 'rgba(22, 93, 255, 0.1)',
    borderRadius: '8px',
    fontSize: '16px',
    itemHeight: '48px'
  }
}

function renderIcon(d: string) {
  return () => h(NIcon, null, { default: () => h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24' }, [h('path', { fill: 'currentColor', d })]) })
}

function renderUserIcon(d: string) {
  return () => h(NIcon, null, { default: () => h('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24' }, [h('path', { fill: 'currentColor', d })]) })
}

const menuOptions = computed<any[]>(() => [
  {
    label: () => h(RouterLink, { to: '/' }, { default: () => '系统总览' }),
    key: 'dashboard',
    icon: renderIcon('M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z')
  },
  {
    label: () => h(RouterLink, { to: '/pipeline' }, { default: () => '上传文件' }),
    key: 'pipeline',
    // 数据管理平台: 文件上传是所有登录用户的基础操作(compute 平台的上传才是 Admin 专属),
    // 所以这里不限制角色, 所有用户均可见。Admin/Users 区别在 PipelinePage 内的"重跑流水线"等按钮上。
    icon: renderIcon('M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z')
  },
  {
    label: () => h(RouterLink, { to: '/logs' }, { default: () => '处理日志' }),
    key: 'logs',
    icon: renderIcon('M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14H7v-2h5v2zm5-4H7v-2h10v2zm0-4H7V7h10v2z')
  },
  {
    label: () => h(RouterLink, { to: '/datasets' }, { default: () => '数据来源' }),
    key: 'datasets',
    icon: renderIcon('M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z')
  }
])

// ---- 用户头像下拉菜单 ----
const displayName = computed(() => roleState.displayName || roleState.username || '用户')
const userInitial = computed(() => {
  const name = displayName.value
  return name ? name.charAt(0).toUpperCase() : 'U'
})

const avatarColors = ['#165DFF', '#18A058', '#F0A020', '#D03050', '#722ED1', '#0066FF']
const avatarColor = computed(() => {
  const idx = (roleState.username?.charCodeAt(0) || 0) % avatarColors.length
  return avatarColors[idx]
})

const userDropdownOptions = computed<any[]>(() => [
  {
    label: roleState.username || '未登录',
    key: 'info',
    disabled: true
  },
  { type: 'divider', key: 'd1' },
  {
    label: '个人信息修改',
    key: 'profile',
    icon: renderUserIcon('M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z')
  },
  {
    label: '平台入口',
    key: 'portal',
    icon: renderUserIcon('M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z')
  },
  {
    label: '退出平台',
    key: 'logout',
    icon: renderUserIcon('M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z')
  }
])

function handleUserAction(key: string) {
  if (key === 'profile') {
    router.push('/profile')
  } else if (key === 'portal') {
    window.location.href = '/yunxi/#/home'
  } else if (key === 'logout') {
    dialog.warning({
      title: '退出登录',
      content: '确定要退出平台吗？',
      positiveText: '确定退出',
      negativeText: '取消',
      onPositiveClick: () => {
        document.cookie = 'yx_token=; path=/; max-age=0'
        localStorage.removeItem('yx_role')
        localStorage.removeItem('yx_username')
        localStorage.removeItem('yx_display_name')
        window.location.href = '/yunxi/'
      }
    })
  }
}

// 页面加载时刷新用户信息
fetchRole()

function downloadManual() {
  const a = document.createElement('a')
  a.href = '/yunxi/data/api/v1/manual'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
</script>

<style>
.app-container {
  height: 100vh;
  width: 100vw;
  position: relative;
}

.nav-header {
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 40px;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.logo {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 240px;
}

.logo-icon {
  height: 40px;
  width: auto;
}

.logo-text {
  font-size: 20px;
  font-weight: 700;
  color: #1D2129;
  letter-spacing: 0.5px;
}

.nav-menu {
  flex: 1;
  display: flex;
  justify-content: flex-end;
  margin-right: 20px;
}

.manual-btn {
  margin-right: 16px;
  white-space: nowrap;
}

.user-avatar-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 8px;
  transition: background-color 0.2s;
  white-space: nowrap;
}

.user-avatar-trigger:hover {
  background-color: rgba(0, 0, 0, 0.04);
}

.user-display-name {
  font-size: 14px;
  font-weight: 500;
  color: #1D2129;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dropdown-arrow {
  font-size: 16px;
  color: #86909c;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

body {
  margin: 0;
  background-color: #f5f7fa;
}

.mobile-tabbar {
  display: none;
}

@media (max-width: 768px) {
  .nav-header {
    height: 56px;
    padding: 0 16px;
  }

  .logo {
    gap: 8px;
    min-width: auto;
  }

  .logo-icon {
    height: 28px;
  }

  .logo-text {
    font-size: 15px;
    letter-spacing: 0;
  }

  .nav-header .nav-menu,
  .nav-header .manual-btn,
  .nav-header .user-display-name,
  .nav-header .dropdown-arrow {
    display: none;
  }

  .user-avatar-trigger {
    padding: 4px;
  }

  .mobile-tabbar {
    display: flex;
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 200;
    background: #fff;
    border-top: 1px solid #e5e6eb;
    padding-bottom: env(safe-area-inset-bottom);
  }

  .mobile-tabbar .tab-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    min-height: 56px;
    font-size: 11px;
    color: #86909c;
    text-decoration: none;
    -webkit-tap-highlight-color: transparent;
  }

  .mobile-tabbar .tab-item.active {
    color: #165dff;
  }

  .mobile-tabbar .tab-icon {
    width: 22px;
    height: 22px;
    display: block;
  }
}
</style>
