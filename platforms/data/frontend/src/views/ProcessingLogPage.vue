<script setup lang="ts">
import { h, onMounted, onUnmounted, ref, computed } from 'vue'
import { roleState } from '../role'
import {
  NButton,
  NCard,
  NDataTable,
  NDescriptions,
  NDescriptionsItem,
  NEmpty,
  NModal,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'

import type { RunSummary } from '../services/api'
import { deleteRun, fetchRuns, exportRuns, clearAllRuns } from '../services/api'

const loading = ref(false)
const exporting = ref(false)
const runs = ref<RunSummary[]>([])
const showDetail = ref(false)
const selectedRun = ref<RunSummary | null>(null)
const message = useMessage()
const dialog = useDialog()

// 权限：当前登录用户是否为管理员（来自门户 JWT）
const isAdmin = computed(() => roleState.role === 'Admin')

function getRunArtifactPath(run: RunSummary) {
  return String(run.summary?.artifacts?.latest_delivery_excel || '')
}

function getRunCounts(run: RunSummary) {
  return run.summary?.counts || {}
}

function getStatusTagType(status: string) {
  if (status === 'success') return 'success' as const
  if (status === 'running') return 'warning' as const
  if (status === 'failed') return 'error' as const
  return 'default' as const
}

function getStatusLabel(status: string) {
  if (status === 'success') return '成功'
  if (status === 'running') return '处理中'
  if (status === 'failed') return '失败'
  return '未知'
}

async function loadRuns() {
  loading.value = true
  try {
    runs.value = await fetchRuns()
  } catch (error: any) {
    console.error(error)
    message.error(error?.message ?? '处理日志加载失败')
  } finally {
    loading.value = false
  }
}

function handleView(run: RunSummary) {
  selectedRun.value = run
  showDetail.value = true
}

function handleDelete(run: RunSummary) {
  dialog.warning({
    title: '删除处理日志',
    content: '删除后将清除该次处理结果、结果文件及相关数据库记录，是否继续？',
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteRun(run.id)
        message.success('处理日志已删除')
        if (selectedRun.value?.id === run.id) {
          showDetail.value = false
          selectedRun.value = null
        }
        await loadRuns()
      } catch (error: any) {
        console.error(error)
        message.error(error?.response?.data?.detail || error?.message || '删除失败')
      }
    },
  })
}

async function handleExport() {
  exporting.value = true
  try {
    const blob = await exportRuns()
    const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '').replace(' ', '_')
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `processing_log_${ts}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  } catch (error: any) {
    console.error(error)
    message.error(error?.response?.data?.detail || error?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

function handleClearAll() {
  dialog.warning({
    title: '清空全部处理日志',
    content: '将删除所有处理日志记录（不可恢复），不影响上传文件与数据集。是否继续？',
    positiveText: '确认清空',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await clearAllRuns()
        message.success('已清空全部处理日志')
        await loadRuns()
      } catch (error: any) {
        console.error(error)
        message.error(error?.response?.data?.detail || error?.message || '清空失败')
      }
    },
  })
}

const columns = [
  {
    title: '序号',
    key: 'index',
    width: 80,
    render(_: RunSummary, index: number) {
      return index + 1
    },
  },
  {
    title: '处理时间节点',
    key: 'started_at',
    width: 260,
    render(row: RunSummary) {
      return h('div', { class: 'time-cell' }, [
        h('div', null, `开始：${row.started_at || '-'}`),
        h('div', null, `结束：${row.completed_at || '-'}`),
      ])
    },
  },
  {
    title: '处理后的结果文件地址',
    key: 'artifact_path',
    render(row: RunSummary) {
      return h(
        'span',
        {
          class: 'path-text',
          title: getRunArtifactPath(row) || '暂无结果文件',
        },
        getRunArtifactPath(row) || '暂无结果文件',
      )
    },
  },
  {
    title: '处理结果状态',
    key: 'status',
    width: 130,
    render(row: RunSummary) {
      return h(
        NTag,
        { type: getStatusTagType(row.status), bordered: false },
        { default: () => getStatusLabel(row.status) },
      )
    },
  },
  {
    title: '查看 / 删除',
    key: 'actions',
    width: 180,
    render(row: RunSummary) {
      const actions = [
        h(
          NButton,
          {
            size: 'small',
            quaternary: true,
            type: 'primary',
            onClick: () => handleView(row),
          },
          { default: () => '查看' },
        ),
      ]
      if (isAdmin.value) {
        actions.push(
          h(
            NButton,
            {
              size: 'small',
              quaternary: true,
              type: 'error',
              onClick: () => handleDelete(row),
            },
            { default: () => '删除' },
          ),
        )
      }
      return h('div', { class: 'action-group' }, actions)
    },
  },
]

const isMobile = ref(typeof window !== 'undefined' && window.innerWidth <= 768)
const handleResize = () => {
  isMobile.value = window.innerWidth <= 768
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  loadRuns()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

const fmtTime = (s: string | null | undefined) => {
  if (!s) return '-'
  return s.replace(/\.\d+/, '').replace('T', ' ')
}

const mobileColumns = computed(() => [
  {
    title: '序号',
    key: 'index',
    width: 50,
    render(_: RunSummary, index: number) {
      return index + 1
    },
  },
  {
    title: '处理时间',
    key: 'started_at',
    render(row: RunSummary) {
      return h('div', { class: 'time-cell' }, [
        h('div', null, `开始：${fmtTime(row.started_at)}`),
        h('div', null, `结束：${fmtTime(row.completed_at)}`),
      ])
    },
  },
  {
    title: '结果',
    key: 'status',
    width: 80,
    render(row: RunSummary) {
      return h(
        NTag,
        { type: getStatusTagType(row.status), bordered: false, size: 'small' },
        { default: () => getStatusLabel(row.status) },
      )
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 120,
    render(row: RunSummary) {
      const actions = [
        h(
          NButton,
          {
            size: 'small',
            quaternary: true,
            type: 'primary',
            onClick: () => handleView(row),
          },
          { default: () => '查看' },
        ),
      ]
      if (isAdmin.value) {
        actions.push(
          h(
            NButton,
            {
              size: 'small',
              quaternary: true,
              type: 'error',
              onClick: () => handleDelete(row),
            },
            { default: () => '删除' },
          ),
        )
      }
      return h('div', { class: 'action-group' }, actions)
    },
  },
])
</script>

<template>
  <div class="log-container">
    <div class="header-section">
      <div class="title-block">
        <h1>处理日志</h1>
        <p>展示每次自动化处理的时间节点、结果状态与结果文件位置，可查看详情或删除历史记录。</p>
      </div>
      <div class="action-bar">
        <n-button type="primary" ghost :loading="loading" @click="loadRuns">刷新日志</n-button>
        <n-button type="default" :loading="exporting" @click="handleExport">导出日志</n-button>
        <n-button v-if="isAdmin" type="error" ghost @click="handleClearAll">清空日志</n-button>
      </div>
    </div>

    <n-card :bordered="false" class="log-card">
      <n-data-table
        :columns="isMobile ? mobileColumns : columns"
        :data="runs"
        :loading="loading"
        :scroll-x="isMobile ? undefined : 700"
        :pagination="isMobile ? false : { pageSize: 8 }"
        :bordered="false"
        size="small"
      />
      <div v-if="!loading && !runs.length" class="empty-wrap">
        <n-empty description="暂无处理日志" />
      </div>
    </n-card>

    <n-modal v-model:show="showDetail" preset="card" style="width: 90%; max-width: 760px" title="处理结果详情" :mask-closable="true">
      <n-descriptions label-placement="left" :column="1" bordered>
        <n-descriptions-item label="任务 ID">#{{ selectedRun?.id }}</n-descriptions-item>
        <n-descriptions-item label="处理状态">
          <n-tag :type="getStatusTagType(selectedRun?.status || '')" :bordered="false">
            {{ getStatusLabel(selectedRun?.status || '') }}
          </n-tag>
        </n-descriptions-item>
        <n-descriptions-item label="开始时间">{{ selectedRun?.started_at || '-' }}</n-descriptions-item>
        <n-descriptions-item label="结束时间">{{ selectedRun?.completed_at || '-' }}</n-descriptions-item>
        <n-descriptions-item label="结果文件地址">
          <span class="detail-path">{{ selectedRun ? getRunArtifactPath(selectedRun) || '暂无结果文件' : '-' }}</span>
        </n-descriptions-item>
        <n-descriptions-item label="处理消息">{{ selectedRun?.message || '暂无' }}</n-descriptions-item>
        <n-descriptions-item label="是否关联图片">{{ selectedRun?.include_images ? '是' : '否' }}</n-descriptions-item>
        <n-descriptions-item label="原始文件数量">{{ selectedRun ? getRunCounts(selectedRun).source_files || 0 : 0 }}</n-descriptions-item>
        <n-descriptions-item label="原始数据数量">
          {{ selectedRun ? (getRunCounts(selectedRun).overall_records || 0) + (getRunCounts(selectedRun).specific_raw_records || 0) + (getRunCounts(selectedRun).image_inventory_records || 0) : 0 }}
        </n-descriptions-item>
        <n-descriptions-item label="汇总数据数量">{{ selectedRun ? getRunCounts(selectedRun).delivery_dataset || 0 : 0 }}</n-descriptions-item>
        <n-descriptions-item label="待关联数据量">{{ selectedRun ? getRunCounts(selectedRun).review_queue || 0 : 0 }}</n-descriptions-item>
      </n-descriptions>
    </n-modal>
  </div>
</template>

<style scoped>
.log-container {
  max-width: 1400px;
  margin: 0 auto;
}

.header-section {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 24px;
}

.title-block h1 {
  margin: 0;
  font-size: 28px;
  color: #1d2129;
}

.title-block p {
  margin: 8px 0 0;
  font-size: 14px;
  color: #86909c;
}

.log-card {
  border-radius: 18px;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.05);
}

.empty-wrap {
  padding: 32px 0 8px;
}

.time-cell {
  font-size: 12px;
  line-height: 1.7;
  color: #4e5969;
}

.path-text,
.detail-path {
  color: #1d2129;
  word-break: break-all;
}

.action-group {
  display: flex;
  gap: 6px;
}

.action-bar {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .header-section {
    flex-direction: column;
    align-items: stretch;
  }

  .action-bar {
    flex-wrap: wrap;
  }

  .action-bar .n-button {
    flex: 1 1 auto;
  }
}
/* 移动端表格横向滑动：touch-action 让手指横滑稳定命中滚动容器 */
:deep(.n-data-table-wrapper) {
  -webkit-overflow-scrolling: touch;
  touch-action: pan-x;
}
</style>
