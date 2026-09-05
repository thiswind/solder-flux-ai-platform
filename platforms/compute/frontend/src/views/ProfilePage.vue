<template>
  <div class="profile-page">
    <div class="profile-header">
      <h2>修改个人信息</h2>
      <p class="profile-subtitle">修改您的显示名称、邮箱或登录密码</p>
    </div>

    <n-card class="profile-card">
      <n-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-placement="top"
        label-width="auto"
        size="large"
      >
        <n-grid :cols="1" :x-gap="24" responsive="screen" item-responsive>
          <n-gi span="1 m:2">
            <n-form-item label="用户名" path="username">
              <n-input :value="roleState.username" disabled />
            </n-form-item>
          </n-gi>

          <n-gi span="1 m:2">
            <n-form-item label="显示名称" path="display_name">
              <n-input
                v-model:value="formData.display_name"
                placeholder="请输入显示名称"
                clearable
              />
            </n-form-item>
          </n-gi>

          <n-gi span="1 m:2">
            <n-form-item label="邮箱" path="email">
              <n-input
                v-model:value="formData.email"
                placeholder="请输入邮箱地址"
                clearable
              />
            </n-form-item>
          </n-gi>

          <n-gi span="1 m:2">
            <n-divider style="margin: 8px 0 16px" />
            <n-form-item label="当前密码" path="current_password">
              <n-input
                v-model:value="formData.current_password"
                type="password"
                placeholder="修改密码时必填，留空则不修改密码"
                show-password-on="click"
              />
            </n-form-item>
          </n-gi>

          <n-gi span="1 m:2">
            <n-form-item label="新密码" path="new_password">
              <n-input
                v-model:value="formData.new_password"
                type="password"
                placeholder="至少 6 位（留空则不修改）"
                show-password-on="click"
              />
            </n-form-item>
          </n-gi>

          <n-gi span="1 m:2">
            <n-form-item label="确认新密码" path="confirm_password">
              <n-input
                v-model:value="formData.confirm_password"
                type="password"
                placeholder="再次输入新密码"
                show-password-on="click"
                @keyup.enter="handleSave"
              />
            </n-form-item>
          </n-gi>
        </n-grid>

        <div class="profile-actions">
          <n-button type="primary" :loading="saving" @click="handleSave">
            保存修改
          </n-button>
          <n-button @click="router.push('/')">返回</n-button>
        </div>
      </n-form>
    </n-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard,
  NForm,
  NFormItem,
  NInput,
  NButton,
  NGrid,
  NGi,
  NDivider
} from 'naive-ui'
import { roleState } from '../role'
import axios from 'axios'

const router = useRouter()
const message = useMessage()
const formRef = ref(null)
const saving = ref(false)

const formData = reactive({
  display_name: '',
  email: '',
  current_password: '',
  new_password: '',
  confirm_password: ''
})

const formRules = {
  email: [
    { pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/, message: '请输入有效的邮箱地址', trigger: 'blur' }
  ],
  new_password: [
    { min: 6, message: '密码至少 6 位', trigger: 'blur' }
  ],
  confirm_password: [
    {
      validator: (rule, value) => {
        if (formData.new_password && value !== formData.new_password) {
          return new Error('两次输入的密码不一致')
        }
        return true
      },
      trigger: 'blur'
    }
  ]
}

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  if (formData.new_password && !formData.current_password) {
    message.warning('修改密码时必须填写当前密码')
    return
  }

  saving.value = true
  try {
    const payload = {
      display_name: formData.display_name || null,
      email: formData.email || null
    }
    if (formData.current_password && formData.new_password) {
      payload.password = formData.new_password
      payload.current_password = formData.current_password
    }

    await axios.put(import.meta.env.BASE_URL + 'api/v1/user/profile', payload)
    message.success('个人信息已更新')

    if (formData.display_name) {
      roleState.displayName = formData.display_name
      localStorage.setItem('yx_display_name', formData.display_name)
    }

    formData.current_password = ''
    formData.new_password = ''
    formData.confirm_password = ''
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '保存失败，请稍后重试'
    message.error(msg)
  } finally {
    saving.value = false
  }
}

async function loadProfile() {
  try {
    const resp = await axios.get(import.meta.env.BASE_URL + 'api/v1/user/profile')
    if (resp.data) {
      formData.display_name = resp.data.display_name || ''
      formData.email = resp.data.email || ''
    }
  } catch {
    // 静默失败，使用默认值
  }
}

loadProfile()
</script>

<style scoped>
.profile-page {
  max-width: 720px;
  margin: 0 auto;
}

.profile-header {
  margin-bottom: 24px;
}

.profile-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: #1D2129;
  margin: 0 0 6px;
}

.profile-subtitle {
  font-size: 14px;
  color: #86909c;
  margin: 0;
}

.profile-card {
  border-radius: 12px;
}

.profile-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #E5E6EB;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .profile-actions {
    flex-direction: column-reverse;
  }

  .profile-actions .n-button {
    width: 100%;
  }
}
</style>
