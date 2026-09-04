import { reactive } from 'vue'
import axios from 'axios'

export interface RoleState {
  role: string
  username: string
  displayName: string
}

// 当前登录用户角色（来自门户 JWT，经后端 /api/v1/me 获取）。
// 初始从 localStorage 读取，避免首屏按钮闪烁；fetchRole 负责刷新。
export const roleState = reactive<RoleState>({
  role: localStorage.getItem('yx_role') || '',
  username: localStorage.getItem('yx_username') || '',
  displayName: localStorage.getItem('yx_display_name') || ''
})

export async function fetchRole(): Promise<void> {
  try {
    const resp = await axios.get<{ role: string; username: string; display_name?: string; email?: string }>('/api/v1/me')
    roleState.role = resp.data.role || 'Users'
    roleState.username = resp.data.username || ''
    // 优先使用服务端返回的 display_name，回退到 username
    roleState.displayName = (resp.data as any).display_name || resp.data.username || ''
    localStorage.setItem('yx_role', roleState.role)
    localStorage.setItem('yx_username', roleState.username)
    localStorage.setItem('yx_display_name', roleState.displayName)
  } catch (e) {
    // 未登录 / 令牌失效：保持为空，组件按非 Admin 处理（隐藏管理按钮）
    roleState.role = ''
  }
}
