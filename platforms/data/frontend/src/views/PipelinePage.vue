<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  NButton,
  NCard,
  NDataTable,
  NDivider,
  NGrid,
  NGridItem,
  NIcon,
  NModal,
  NProgress,
  NResult,
  NSpace,
  NSwitch,
  useDialog,
  useMessage,
} from 'naive-ui'
import {
  CloudUploadOutline,
  DocumentTextOutline,
  DownloadOutline,
  FolderOpenOutline,
  ImageOutline,
  InformationCircleOutline,
  SettingsOutline,
  TrashOutline,
} from '@vicons/ionicons5'

import type { ArtifactInfo, RunSummary } from '../services/api'
import {
  clearAllUploads,
  fetchDashboardOverview,
  fetchLatestDeliveryArtifact,
  fetchReviewIssues,
  fetchRunReadiness,
  fetchUploadedFiles,
  getLatestDeliveryDownloadUrl,
  runPipeline,
  uploadSourceFiles,
} from '../services/api'

type UploadType = 'overall' | 'specific' | 'image'

const includeImages = ref(true)
const includeAutoGrade = ref(true)
const latestDelivery = ref<ArtifactInfo | null>(null)
const showResultModal = ref(false)
const currentRunId = ref<number | null>(null)
const dismissedRunId = ref<number | null>(null)
const showUploadConfirm = ref(false)
const showFeedbackModal = ref(false)
const lastRunResult = ref<RunSummary | null>(null)
const reviewIssues = ref<any[]>([])
const runLoading = ref(false)
const pendingUploadType = ref<UploadType | null>(null)
const pollTimer = ref<number | null>(null)
const feedbackStatus = ref<'success' | 'warning' | 'error' | 'info'>('info')
const feedbackTitle = ref('')
const feedbackDescription = ref('')

const dialog = useDialog()
const message = useMessage()
const clearLoading = ref(false)

// 磁盘上已上传的文件数（来自 /pipeline/upload-files），有文件即可启用"开始自动化匹配"
const uploadedFileCount = ref(0)
const hasImportedData = computed(() => uploadedFileCount.value > 0)

// DB 已入库的文件数（用于首页展示，不影响按钮状态）
const sourceFileCount = ref(0)

const selectedFiles = ref<Record<UploadType, File[]>>({
  overall: [],
  specific: [],
  image: [],
})

const uploadLoading = ref<Record<UploadType, boolean>>({
  overall: false,
  specific: false,
  image: false,
})

const uploadProgress = ref<{ done: number; total: number } | null>(null)

const reviewColumns = [
  { title: '类型', key: 'issue_type', width: 120 },
  { title: '批号', key: 'entity_key', width: 140 },
  { title: '消息', key: 'message' },
  { title: '来源', key: 'source_file', ellipsis: true },
]

const uploadCards = computed(() => [
  {
    key: 'overall' as UploadType,
    title: '锡膏检测数据',
    description: '选择锡膏检测数据 Excel 或文件夹。',
    accept: '.xlsx,.xls',
    icon: DocumentTextOutline,
    allowDirectory: true,
  },
  {
    key: 'specific' as UploadType,
    title: '锡膏配方数据',
    description: '选择锡膏配方数据 Excel 或文件夹。',
    accept: '.xlsx,.xls',
    icon: FolderOpenOutline,
    allowDirectory: true,
  },
  {
    key: 'image' as UploadType,
    title: '锡膏产品图片',
    description: '选择锡膏产品图片或文件夹。',
    accept: '.png,.jpg,.jpeg,.bmp,.tif,.tiff',
    icon: ImageOutline,
    allowDirectory: true,
  },
])

const currentUploadFiles = computed(() => {
  const type = pendingUploadType.value
  return type ? selectedFiles.value[type] : []
})

const processingVisible = computed(() => runLoading.value)

function getUploadTitle(type: UploadType | null) {
  return uploadCards.value.find((item) => item.key === type)?.title ?? '上传文件'
}

function openFeedback(
  status: 'success' | 'warning' | 'error' | 'info',
  title: string,
  description: string,
) {
  feedbackStatus.value = status
  feedbackTitle.value = title
  feedbackDescription.value = description
  showFeedbackModal.value = true
}

function onResultModalShow(visible: boolean) {
  // 任何方式关闭结果弹窗（×、遮罩、关闭按钮）都记录已关闭的任务，
  // 避免轮询回调或重渲染导致弹窗被反复重新打开。
  if (!visible) dismissedRunId.value = currentRunId.value
}

function handleFileChange(type: UploadType, event: Event) {
  const input = event.target as HTMLInputElement
  selectedFiles.value[type] = Array.from(input.files ?? [])
}

function openUploadConfirm(type: UploadType) {
  if (!selectedFiles.value[type].length) {
    openFeedback('warning', '尚未选择文件', '请先选择文件或文件夹后，再执行上传。')
    return
  }
  pendingUploadType.value = type
  showUploadConfirm.value = true
}

async function confirmUpload() {
  const type = pendingUploadType.value
  if (!type) return

  const files = selectedFiles.value[type]
  uploadLoading.value[type] = true
  uploadProgress.value = { done: 0, total: files.length }
  try {
    const result = await uploadSourceFiles(type, files, (done, total) => {
      uploadProgress.value = { done, total }
    })
    selectedFiles.value[type] = []
    showUploadConfirm.value = false
    // 有文件被跳过时用 warning 提示，否则正常 success
    if (result.skipped && result.skipped.length > 0) {
      const skipExamples = result.skipped.slice(0, 5).map((s: any) => s.filename).join('、')
      const more = result.skipped.length > 5 ? `等 ${result.skipped.length} 个` : ''
      openFeedback(
        'warning',
        `上传完成（${result.skipped.length} 个文件已跳过）`,
        `${getUploadTitle(type)}已成功写入 ${result.uploaded_count} 个文件。以下文件因格式不支持被跳过${more}：${skipExamples}`,
      )
    } else {
      openFeedback('success', '上传完成', `${getUploadTitle(type)}已成功写入系统目录，可继续启动自动化处理。`)
    }
    await loadUploadedCount()
  } catch (error: any) {
    console.error(error)
    openFeedback('error', '上传失败', error?.message ?? '文件上传失败，请检查文件格式或路径后重试。')
  } finally {
    uploadLoading.value[type] = false
    uploadProgress.value = null
  }
}

async function loadLatestDelivery() {
  try {
    latestDelivery.value = await fetchLatestDeliveryArtifact()
  } catch {
    latestDelivery.value = null
  }
}

async function refreshLatestRun() {
  try {
    const overview = await fetchDashboardOverview()
    lastRunResult.value = overview.latest_run
    sourceFileCount.value = overview.source_file_count ?? 0
    if (overview.latest_run?.status === 'running' && overview.latest_run.id) {
      runLoading.value = true
      startPollingProgress(overview.latest_run.id)
    } else {
      runLoading.value = false
      lastRunResult.value = null  // 清除已完成/失败任务的显示
      if (pollTimer.value) {
        clearInterval(pollTimer.value)
        pollTimer.value = null
      }
    }
  } catch (error) {
    console.error(error)
  }
}

async function startPollingProgress(runId: number) {
  currentRunId.value = runId
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
  }

  // 防止重叠的轮询回调：如果后台响应慢于 2s，多个回调可能同时检测到
  // 任务完成，导致结果弹窗被重复打开（点一次叉关不掉）。
  let hasHandledCompletion = false

  pollTimer.value = window.setInterval(async () => {
    if (hasHandledCompletion) {
      return
    }
    try {
      const overview = await fetchDashboardOverview()
      const latestRun = overview.latest_run
      if (!latestRun || latestRun.id !== runId) {
        return
      }

      lastRunResult.value = latestRun
      sourceFileCount.value = overview.source_file_count ?? 0
      if (latestRun.status !== 'running') {
        hasHandledCompletion = true
        runLoading.value = false
        if (pollTimer.value) clearInterval(pollTimer.value)
        pollTimer.value = null
        await loadLatestDelivery()

        if (latestRun.status === 'success') {
          try {
            reviewIssues.value = await fetchReviewIssues(runId)
          } catch {
            reviewIssues.value = []
          }
          if (dismissedRunId.value !== runId) {
            showResultModal.value = true
          }
        } else if (latestRun.status === 'failed') {
          openFeedback('error', '任务执行失败', latestRun.message || '后台处理任务执行失败。')
        }
      }
    } catch (error) {
      console.error('轮询进度失败', error)
    }
  }, 2000)
}

async function handleRun() {
  if (!hasImportedData.value) {
    openFeedback('warning', '暂无数据', '请先上传锡膏检测数据 / 配方数据 / 产品图片后，再启动自动化匹配。')
    return
  }
  try {
    const readiness = await fetchRunReadiness()
    if (readiness.has_files && !readiness.source_changed) {
      dialog.warning({
        title: '未检测到新文件',
        content: '当前上传目录中的文件与上次成功匹配的数据完全一致，没有新上传或改动的内容。确定要重新运行数据匹配吗？',
        positiveText: '仍然运行',
        negativeText: '取消',
        onPositiveClick: () => {
          void doRun()
        },
      })
      return
    }
    await doRun()
  } catch (error: any) {
    console.error(error)
    openFeedback('error', '启动失败', error?.message ?? '任务执行失败，请稍后重试。')
  }
}

async function doRun() {
  runLoading.value = true
  reviewIssues.value = []
  dismissedRunId.value = null
  try {
    const result = await runPipeline({
      include_images: includeImages.value,
      include_auto_grade: includeAutoGrade.value,
      trigger_source: 'frontend_manual',
    })
    lastRunResult.value = {
      id: result.run_id,
      status: result.status,
      include_images: includeImages.value,
      current_step: '任务已启动，等待后台接管...',
      progress_percent: 0,
      started_at: result.started_at,
      completed_at: result.completed_at,
      message: result.message,
      summary: result.summary,
    }
    openFeedback('success', '任务已启动', '自动化处理任务已成功提交，后续进度会在页面中持续更新。')
    await startPollingProgress(result.run_id)
  } catch (error: any) {
    runLoading.value = false
    console.error(error)
    openFeedback('error', '启动失败', error?.message ?? '任务执行失败，请稍后重试。')
  }
}

function handleClearUploads() {
  const d = dialog.warning({
    title: '清空所有上传文件',
    content: '此操作将删除所有已上传的 Excel / 图片文件，操作不可恢复，确认继续？',
    positiveText: '确认清空',
    negativeText: '取消',
    onPositiveClick: async () => {
      // 按钮前面显示转动小圈，弹窗保持打开不关闭
      d.loading = true
      clearLoading.value = true
      try {
        const result = await clearAllUploads()
        const dbCount = Object.values(result.deleted_db_records).reduce((a, b) => a + b, 0)
        if (result.failed_files && result.failed_files > 0) {
          message.error(`磁盘文件有 ${result.failed_files} 个删除失败（可能被运行环境拦截），已删除 ${result.deleted_files} 个、清除 ${dbCount} 条记录。请在本地终端启动后端后重试清空。`)
        } else {
          message.success(`已清空：删除 ${result.deleted_files} 个文件，清除 ${dbCount} 条数据库记录`)
        }
        latestDelivery.value = null
        await refreshLatestRun()
        await loadUploadedCount()
      } catch (error: any) {
        console.error(error)
        d.loading = false
        clearLoading.value = false
        message.error(error?.message ?? '清空失败，请稍后重试')
        return false // 阻止弹窗关闭，让用户看到错误
      }
      clearLoading.value = false
    },
  })
}

async function loadUploadedCount() {
  try {
    const data = await fetchUploadedFiles()
    uploadedFileCount.value = data.rows?.length ?? 0
  } catch (err) {
    console.error('[loadUploadedCount] 获取已上传文件列表失败，按钮状态可能不准确', err)
    // 不盲目归零：保留上次已知值，避免接口抖动导致按钮意外禁用
  }
}

onMounted(async () => {
  await Promise.all([loadLatestDelivery(), refreshLatestRun(), loadUploadedCount()])
})

onBeforeUnmount(() => {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
})
</script>

<template>
  <div class="upload-container">
    <div class="header-section">
      <div class="title-block">
        <div class="title-row">
          <h1>上传文件与处理</h1>
          <n-button type="error" ghost size="small" :loading="clearLoading" @click="handleClearUploads">
            <template #icon>
              <n-icon :component="TrashOutline" />
            </template>
            清空文件
          </n-button>
        </div>
        <p>选择文件后上传，再启动自动化匹配。</p>
      </div>
      <div class="header-help">
        <div class="header-help-title">
          <n-icon :component="InformationCircleOutline" />
          <span>操作提示</span>
        </div>
        <div class="header-help-line"> 每类都支持直接选择整个文件夹，无需逐个点选文件。</div>
      </div>
    </div>

    <n-grid cols="1 s:2 m:3" :x-gap="20" :y-gap="20" responsive="screen" item-responsive>
      <n-grid-item v-for="card in uploadCards" :key="card.key">
        <n-card :bordered="false" class="upload-card">
          <template #header>
            <div class="card-header">
              <n-icon :component="card.icon" size="18" color="#165DFF" />
              <span>{{ card.title }}</span>
            </div>
          </template>
          <p class="card-desc">{{ card.description }}</p>

          <div class="upload-box">
            <input
              :id="`file-${card.key}`"
              type="file"
              multiple
              :webkitdirectory="card.allowDirectory"
              :directory="card.allowDirectory"
              :accept="card.accept"
              class="hidden-input"
              @change="handleFileChange(card.key, $event)"
            />
            <label :for="`file-${card.key}`" class="upload-label">
              <n-icon :component="CloudUploadOutline" size="30" />
              <span>点击选择文件或文件夹</span>
              <span class="file-count">{{ selectedFiles[card.key].length ? `已选择 ${selectedFiles[card.key].length} 个` : '支持目录导入' }}</span>
            </label>
          </div>

          <div v-if="selectedFiles[card.key].length" class="selected-preview">
            <div class="preview-title">已选文件</div>
            <div class="preview-list">
              <span v-for="file in selectedFiles[card.key].slice(0, 3)" :key="file.name">{{ file.name }}</span>
              <span v-if="selectedFiles[card.key].length > 3">...</span>
            </div>
          </div>

          <n-button
            block
            type="primary"
            class="upload-btn"
            :loading="uploadLoading[card.key]"
            :disabled="!selectedFiles[card.key].length"
            @click="openUploadConfirm(card.key)"
          >
            确认上传
          </n-button>
          <p
            v-if="uploadLoading[card.key] && uploadProgress"
            :style="{ marginTop: '8px', fontSize: '13px', color: '#86909c', textAlign: 'center' }"
          >
            正在上传 {{ uploadProgress.done }} / {{ uploadProgress.total }}
          </p>
        </n-card>
      </n-grid-item>
    </n-grid>

    <n-grid cols="1 m:12" :x-gap="20" :y-gap="20" class="section-grid" responsive="screen" item-responsive>
      <n-grid-item span="1 m:8">
        <n-card title="处理配置" :bordered="false" class="panel-card">
          <template #header-extra>
            <n-icon :component="SettingsOutline" size="18" />
          </template>

          <div class="config-box">
            <div class="config-item">
              <div>
                <div class="config-label">开启图片关联</div>
                <div class="config-desc">同步统计图片并尝试关联。</div>
              </div>
              <n-switch v-model:value="includeImages" />
            </div>

            <div class="config-item">
              <div>
                <div class="config-label">开启图像分级</div>
                <div class="config-desc">对关联到的图片执行视觉质量分级（润湿 / 锡珠 / 坍塌）。</div>
              </div>
              <n-switch v-model:value="includeAutoGrade" />
            </div>

            <div class="run-actions">
              <n-button
                type="primary"
                size="large"
                :loading="runLoading"
                :disabled="!hasImportedData || runLoading"
                @click="handleRun"
              >
                开始数据匹配
              </n-button>
              <a v-if="latestDelivery?.exists" :href="getLatestDeliveryDownloadUrl()" target="_blank" class="delivery-link">
                最近结果：{{ latestDelivery.artifact_path }}
              </a>
            </div>
          </div>

          <div v-if="processingVisible" class="processing-panel">
            <div class="processing-top">
              <div>
                <div class="processing-title">当前处理进度</div>
                <div class="processing-step">{{ lastRunResult?.current_step || '后台处理中...' }}</div>
              </div>
              <div class="processing-percent">{{ lastRunResult?.progress_percent || 0 }}%</div>
            </div>
            <n-progress
              type="line"
              :percentage="lastRunResult?.progress_percent || 0"
              :indicator-placement="'inside'"
              processing
              status="info"
            />
            <div class="processing-note">
              扫描阶段会尽量显示当前文件名。
            </div>
          </div>
          <div v-else class="processing-panel locked">
            <div class="locked-mask">
              <div class="locked-title">等待启动</div>
              <div class="locked-text">点击“开始数据匹配”后显示处理进度</div>
            </div>
            <div class="locked-content">
              <div class="processing-top">
                <div>
                  <div class="processing-title">当前处理进度</div>
                  <div class="processing-step">后台处理中...</div>
                </div>
                <div class="processing-percent">0%</div>
              </div>
              <n-progress
                type="line"
                :percentage="0"
                :indicator-placement="'inside'"
                status="info"
              />
              <div class="processing-note">
                扫描阶段会尽量显示当前文件名。
              </div>
            </div>
          </div>
        </n-card>
      </n-grid-item>

      <n-grid-item span="1 m:4">
        <n-card title="上传注意事项" :bordered="false" class="panel-card notice-card">
          <template #header-extra>
            <n-icon :component="InformationCircleOutline" size="18" />
          </template>
          <div class="notice-list">
            <div class="notice-item">
              <div class="notice-title">1. 支持目录导入</div>
              <div class="notice-text">可直接选择整文件夹。</div>
            </div>
            <div class="notice-item">
              <div class="notice-title">2. 建议分类上传</div>
              <div class="notice-text">检测数据、配方数据、产品图片分开传。</div>
            </div>
            <div class="notice-item">
              <div class="notice-title">3. 图片路径可修改</div>
              <div class="notice-text">盘符变化时去总览页更新。</div>
            </div>
            <div class="notice-item">
              <div class="notice-title">4. 导出结果说明</div>
              <div class="notice-text">生成关联匹配后的Excel文件，包括图片齐全数据（filtered）和全部关联数据（raw），前者仅保留所有产品图片齐全的记录</div>
            </div>
          </div>
        </n-card>
      </n-grid-item>
    </n-grid>

    <n-modal v-model:show="showUploadConfirm" :mask-closable="true">
      <div class="confirm-modal">
        <div class="confirm-badge">上传确认</div>
        <h3>{{ getUploadTitle(pendingUploadType) }}</h3>
        <p>本次共选择 {{ currentUploadFiles.length }} 个文件，确认后将写入系统目录并参与后续处理。</p>
        <div class="confirm-list">
          <div v-for="file in currentUploadFiles.slice(0, 8)" :key="file.name" class="confirm-file">{{ file.name }}</div>
          <div v-if="currentUploadFiles.length > 8" class="confirm-more">还有 {{ currentUploadFiles.length - 8 }} 个文件未展开</div>
        </div>
        <div class="confirm-actions">
          <n-button @click="showUploadConfirm = false">取消</n-button>
          <n-button type="primary" :loading="pendingUploadType ? uploadLoading[pendingUploadType] : false" @click="confirmUpload">
            开始上传
          </n-button>
        </div>
      </div>
    </n-modal>

    <n-modal v-model:show="showFeedbackModal" :mask-closable="true">
      <div class="feedback-modal">
        <n-result :status="feedbackStatus" :title="feedbackTitle" :description="feedbackDescription">
          <template #footer>
            <n-button type="primary" @click="showFeedbackModal = false">我知道了</n-button>
          </template>
        </n-result>
      </div>
    </n-modal>

    <n-modal v-model:show="showResultModal" preset="card" style="width: 90%; max-width: 860px" title="处理完成" :mask-closable="true" @update:show="onResultModalShow">
      <n-result
        status="success"
        title="自动化处理已完成"
        description="系统已完成数据清洗、匹配与汇总导出。"
      >
        <template #footer>
          <n-space justify="center">
            <n-button type="primary" tag="a" :href="getLatestDeliveryDownloadUrl()" target="_blank">
              <template #icon>
                <n-icon :component="DownloadOutline" />
              </template>
              下载汇总 Excel
            </n-button>
            <n-button @click="showResultModal = false">关闭</n-button>
          </n-space>
        </template>
      </n-result>

      <div class="result-summary">
        <div class="summary-stat">
          <span>任务 ID</span>
          <strong>#{{ lastRunResult?.id }}</strong>
        </div>
        <div class="summary-stat">
          <span>处理结果</span>
          <strong>{{ lastRunResult?.message || '数据处理完成' }}</strong>
        </div>
      </div>

      <div class="result-extra">
        <n-divider title-placement="left">需关注的复核项</n-divider>
        <div class="review-tip">这些项目仅供按需排查，不必逐条人工核对。</div>
        <n-data-table
          v-if="reviewIssues.length"
          :columns="reviewColumns"
          :data="reviewIssues"
          :scroll-x="420"
          :pagination="{ pageSize: 5 }"
          size="small"
        />
        <div v-else class="review-empty">本次任务没有额外的复核提醒。</div>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.upload-container {
  max-width: 1280px;
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

.title-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.title-block p {
  margin: 8px 0 0;
  color: #86909c;
  font-size: 13px;
  line-height: 1.6;
}

.header-help {
  min-width: 340px;
  max-width: 400px;
  padding: 14px 16px;
  border: 1px solid #dbe7ff;
  border-radius: 18px;
  background: linear-gradient(180deg, #f8fbff 0%, #f2f7ff 100%);
  box-shadow: 0 10px 24px rgba(22, 93, 255, 0.08);
}

.header-help-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #165dff;
}

.header-help-line {
  font-size: 12px;
  line-height: 1.7;
  color: #4e5969;
}

.upload-card,
.panel-card {
  border-radius: 18px;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.05);
}

.panel-card {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}

.card-desc {
  min-height: 20px;
  margin: 0 0 12px;
  color: #86909c;
  font-size: 12px;
  line-height: 1.5;
}

.upload-box {
  border: 1px dashed #c9d5e8;
  border-radius: 18px;
  background: linear-gradient(180deg, #f9fbff 0%, #f4f7fb 100%);
}

.upload-label {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 22px 16px;
  color: #4e5969;
  cursor: pointer;
}

.file-count {
  font-size: 12px;
  color: #165dff;
}

.hidden-input {
  display: none;
}

.selected-preview {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 14px;
  background: #f7f8fa;
}

.preview-title {
  margin-bottom: 6px;
  font-size: 12px;
  color: #86909c;
}

.preview-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: #1d2129;
}

.upload-btn {
  margin-top: 12px;
}

.section-grid {
  margin-top: 24px;
}

.config-box {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.config-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 16px;
  background: #f7f8fa;
}

.config-label {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}

.config-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #86909c;
}

.run-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.delivery-link {
  color: #165dff;
  font-size: 12px;
  text-decoration: none;
  word-break: break-all;
}

.processing-panel {
  margin-top: 12px;
  padding: 14px 16px;
  border-radius: 18px;
  background: linear-gradient(180deg, #eef5ff 0%, #f7fbff 100%);
  border: 1px solid #d8e7ff;
}

.processing-panel.locked {
  position: relative;
  overflow: hidden;
}

.processing-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 10px;
}

.processing-title {
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
}

.processing-step {
  margin-top: 6px;
  font-size: 12px;
  color: #4e5969;
  word-break: break-all;
}

.processing-percent {
  font-size: 18px;
  font-weight: 700;
  color: #165dff;
}

.processing-note {
  margin-top: 8px;
  font-size: 12px;
  color: #86909c;
}

.locked-content {
  filter: blur(2px);
  opacity: 0.7;
  pointer-events: none;
}

.locked-mask {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 6px;
  background: rgba(247, 251, 255, 0.5);
}

.locked-title {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}

.locked-text {
  font-size: 12px;
  color: #86909c;
}

.notice-card {
  min-height: 100%;
}

.notice-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.notice-item {
  padding: 10px 12px;
  border-radius: 14px;
  background: #f7f8fa;
}

.notice-title {
  margin-bottom: 4px;
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
}

.notice-text {
  font-size: 13px;
  line-height: 1.6;
  color: #86909c;
}

.confirm-modal {
  width: 90%;
  max-width: 640px;
  margin: 10vh auto 0;
  padding: 28px;
  border-radius: 24px;
  background: #ffffff;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.18);
}

.confirm-badge {
  display: inline-block;
  margin-bottom: 12px;
  padding: 6px 12px;
  border-radius: 999px;
  background: #edf4ff;
  color: #165dff;
  font-size: 12px;
  font-weight: 600;
}

.confirm-modal h3 {
  margin: 0;
  font-size: 22px;
  color: #1d2129;
}

.confirm-modal p {
  margin: 10px 0 18px;
  font-size: 14px;
  line-height: 1.7;
  color: #4e5969;
}

.confirm-list {
  max-height: 260px;
  overflow: auto;
  padding: 8px;
  border-radius: 16px;
  background: #f7f8fa;
}

.confirm-file,
.confirm-more {
  padding: 10px 12px;
  font-size: 13px;
  color: #1d2129;
}

.confirm-file + .confirm-file {
  border-top: 1px solid #eceef2;
}

.confirm-more {
  color: #86909c;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

.feedback-modal {
  width: 90%;
  max-width: 520px;
  margin: 18vh auto 0;
  padding: 20px 16px 8px;
  border-radius: 24px;
  background: #ffffff;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.2);
}

.result-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.summary-stat {
  padding: 14px 16px;
  border-radius: 16px;
  background: #f7f8fa;
}

.summary-stat span {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  color: #86909c;
}

.summary-stat strong {
  font-size: 14px;
  color: #1d2129;
  word-break: break-all;
}

.result-extra {
  margin-top: 20px;
}

.review-tip,
.review-empty {
  margin-bottom: 12px;
  font-size: 13px;
  color: #86909c;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .header-section {
    flex-direction: column;
    align-items: stretch;
  }

  .result-summary {
    grid-template-columns: 1fr;
  }

  .confirm-actions {
    flex-direction: column-reverse;
  }

  .confirm-actions .n-button {
    width: 100%;
  }
}
/* 移动端表格横向滑动：touch-action 让手指横滑稳定命中滚动容器 */
:deep(.n-data-table-wrapper) {
  -webkit-overflow-scrolling: touch;
  touch-action: pan-x;
}
</style>
