<template>
  <div class="data-platform">
    <!-- 1. Project Intro & Stats -->
    <n-card class="intro-card" :bordered="false">
      <div class="intro-content">
        <div class="intro-left">
           <div class="title-group">
             <div class="icon-wrapper">
               <n-icon size="32" color="#165DFF">
                 <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10s10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8s8 3.59 8 8s-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/></svg>
               </n-icon>
             </div>
             <div>
               <h1 class="page-title">数据管理控制台</h1>
               <p class="page-subtitle">锡基材料实验数据分析与管理中心</p>
             </div>
           </div>
        </div>
        <div class="intro-right">
           <div class="hero-stat-card">
             <span class="hero-stat-label">累计数据条目</span>
             <strong>{{ stats.total_count || 0 }}</strong>
           </div>
           <div class="hero-stat-card">
             <span class="hero-stat-label">涉及产品型号</span>
             <strong>{{ stats.models ? stats.models.length : 0 }}</strong>
           </div>
           <div class="hero-stat-card">
             <span class="hero-stat-label">黏度均值</span>
             <strong>{{ formatMetric(stats.viscosity_summary?.mean, 2) }}</strong>
           </div>
           <div class="hero-stat-card">
             <span class="hero-stat-label">Ti 中位值</span>
             <strong>{{ formatMetric(stats.ti_summary?.median, 4) }}</strong>
           </div>
        </div>
      </div>
    </n-card>

    <!-- 2. Data Visualization (Charts) -->
    <div class="charts-section">
      <n-grid :x-gap="24" :y-gap="24" cols="1 800:2" class="charts-grid">
        <n-grid-item>
          <n-card title="黏度分布" :bordered="false" class="chart-card hover-effect">
            <template #header-extra>
               <n-tag type="primary" size="small" round>Pa·s</n-tag>
            </template>
            <div class="chart-summary-grid">
              <div class="summary-chip">
                <span>均值</span>
                <strong>{{ formatMetric(stats.viscosity_summary?.mean, 2) }}</strong>
              </div>
              <div class="summary-chip">
                <span>中位值</span>
                <strong>{{ formatMetric(stats.viscosity_summary?.median, 2) }}</strong>
              </div>
              <div class="summary-chip">
                <span>范围</span>
                <strong>{{ formatRange(stats.viscosity_summary, 2) }}</strong>
              </div>
            </div>
            <div id="viscosityChart" class="chart-container"></div>
          </n-card>
        </n-grid-item>
        <n-grid-item>
          <n-card title="Ti值分布" :bordered="false" class="chart-card hover-effect">
            <template #header-extra>
               <n-tag type="success" size="small" round>Index</n-tag>
            </template>
            <div class="chart-summary-grid">
              <div class="summary-chip">
                <span>均值</span>
                <strong>{{ formatMetric(stats.ti_summary?.mean, 4) }}</strong>
              </div>
              <div class="summary-chip">
                <span>标准差</span>
                <strong>{{ formatMetric(stats.ti_summary?.std, 4) }}</strong>
              </div>
              <div class="summary-chip">
                <span>范围</span>
                <strong>{{ formatRange(stats.ti_summary, 4) }}</strong>
              </div>
            </div>
            <div id="tiChart" class="chart-container"></div>
          </n-card>
        </n-grid-item>
      </n-grid>
    </div>

    <!-- 3. Uploads Management (Main Table) -->
    <n-card title="上传记录管理" :bordered="false" class="main-table-card">
      <template #header-extra>
        <n-space v-if="isAdmin" :size="10" align="center">
          <n-button
            type="primary" size="medium"
            :disabled="hasData"
            @click="showUploadModal = true"
            class="action-btn"
          >
            <template #icon><n-icon>📥</n-icon></template>
            上传数据
          </n-button>
          <n-popconfirm negative-text="取消" positive-text="确认" @positive-click="handleClearAll">
            <template #trigger>
              <n-button
                type="error" size="medium"
                :disabled="!hasData"
                :loading="clearing"
                class="action-btn"
              >
                <template #icon><n-icon>🗑️</n-icon></template>
                清空数据
              </n-button>
            </template>
            确认清空上传数据？此操作不可逆，将删除所有上传记录。
          </n-popconfirm>
        </n-space>
      </template>
      
      <n-data-table
        :columns="uploadColumns"
        :data="uploadList"
        :loading="loadingUploads"
        :pagination="pagination"
        :scroll-x="900"
        :row-key="row => row.id"
        class="uploads-table"
      />
    </n-card>

    <!-- 4. Data Details Modal -->
    <n-modal
      v-model:show="showDetailModal"
      preset="card"
      style="width: 90%; max-width: 1400px; height: 80vh;"
      title="数据详情"
      :bordered="false"
      size="huge"
    >
      <template #header-extra>
         <n-tag type="info">Upload ID: {{ currentUploadId }}</n-tag>
      </template>
      
      <div class="modal-content">
         <n-data-table
            :columns="detailColumns"
            :data="detailData"
            :loading="loadingDetails"
            :max-height="600"
            :scroll-x="1800"
            virtual-scroll
            size="small"
            :row-key="row => row.id"
         />
      </div>
    </n-modal>

    <!-- 5. Edit Modal -->
    <n-modal v-model:show="showEditModal" preset="card" title="编辑数据" style="width: 90%; max-width: 600px;">
      <n-form
        ref="editFormRef"
        :model="editFormModel"
        label-placement="left"
        label-width="auto"
        require-mark-placement="right-hanging"
      >
        <n-form-item label="黏度初值 (Pa·s)" path="viscosity_initial">
          <n-input-number v-model:value="editFormModel.viscosity_initial" placeholder="Input Viscosity" />
        </n-form-item>
        <n-form-item label="Ti Index" path="ti_index">
          <n-input-number v-model:value="editFormModel.ti_index" placeholder="Input Ti" />
        </n-form-item>
        <n-form-item label="锡粉规格" path="powder_spec">
          <n-input v-model:value="editFormModel.powder_spec" placeholder="请输入锡粉规格" />
        </n-form-item>
        <n-form-item label="润湿等级" path="wetting_level">
          <n-input v-model:value="editFormModel.wetting_level" placeholder="请输入润湿等级" />
        </n-form-item>
        <n-form-item label="锡珠等级" path="solderball_level">
          <n-input v-model:value="editFormModel.solderball_level" placeholder="请输入锡珠等级" />
        </n-form-item>
        <n-form-item label="坍塌类别" path="collapse_category">
          <n-input v-model:value="editFormModel.collapse_category" placeholder="请输入坍塌类别" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 12px">
          <n-button @click="showEditModal = false">取消</n-button>
          <n-button type="primary" @click="handleSaveEdit" :loading="savingEdit">保存修改</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 6. Upload Modal -->
    <n-modal v-model:show="showUploadModal" preset="card" title="上传数据文件" style="width: 90%; max-width: 600px;">
      <n-space vertical size="large">
        <div class="upload-template-box">
          <div>
            <div class="upload-template-title">推荐先下载上传模板</div>
            <div class="upload-template-desc">模板已对齐当前 `processed_data.xlsx` 列结构，按模板填充可减少上传校验失败。</div>
          </div>
          <n-button v-if="isAdmin" type="info" secondary @click="downloadTemplate">下载模板</n-button>
        </div>
        <n-form-item label="自定义文件名称 (可选)">
          <n-input v-model:value="uploadForm.customFilename" placeholder="如果不填，将使用原文件名" />
        </n-form-item>
        
        <n-upload
          multiple={false}
          directory-dnd
          action=""
          :custom-request="customUploadRequest"
          @change="handleUploadChange"
          :max="1"
        >
          <n-upload-dragger>
            <div style="margin-bottom: 12px">
              <n-icon size="48" :depth="3">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M19.35 10.04C18.67 6.59 15.64 4 12 4C9.11 4 6.6 5.64 5.35 8.04C2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5c0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5l5 5h-3z"/></svg>
              </n-icon>
            </div>
            <n-text style="font-size: 16px">
              点击或者拖拽文件到此处上传
            </n-text>
            <n-p depth="3" style="margin: 8px 0 0 0">
              支持 .xlsx, .xls 格式文件
            </n-p>
          </n-upload-dragger>
        </n-upload>

        <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 16px;">
           <n-button @click="showUploadModal = false">取消</n-button>
           <n-button v-if="isAdmin" type="primary" @click="submitUpload" :loading="uploading" :disabled="!uploadFile">
             确认上传
           </n-button>
        </div>
      </n-space>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, h, computed } from 'vue'
import { roleState } from '../role'
import { useMessage, NButton, NTag, NTime, NInputNumber, NForm, NFormItem, NInput, NUpload, NUploadDragger, NIcon, NText, NP, NSpace, NPopconfirm } from 'naive-ui'
import axios from 'axios'
import * as echarts from 'echarts'

const message = useMessage()
const API_BASE_URL = import.meta.env.BASE_URL + 'api/v1'

// 权限：当前登录用户是否为管理员（来自门户 JWT）
const isAdmin = computed(() => roleState.role === 'Admin')

// --- State ---
const stats = ref({})
const loadingUploads = ref(false)
const uploadList = ref([])

// Upload Modal State
const showUploadModal = ref(false)
const uploading = ref(false)
const uploadFile = ref(null)
const uploadForm = reactive({
    customFilename: ''
})

// 互斥按钮状态：根据数据库是否有数据自动决定哪个按钮可用
// 有数据 → 只能清空；无数据 → 只能上传
const hasData = computed(() => (uploadList.value?.length || 0) > 0)
const clearing = ref(false)

// Details Modal State
const showDetailModal = ref(false)
const loadingDetails = ref(false)
const detailData = ref([])
const currentUploadId = ref(null)

// Edit Modal State
const showEditModal = ref(false)
const savingEdit = ref(false)
const editFormModel = reactive({
    id: null,
    viscosity_initial: null,
    ti_index: null,
    powder_spec: null,
    wetting_level: null,
    solderball_level: null,
    collapse_category: null
})

const pagination = reactive({
  page: 1,
  pageSize: 10,
  itemCount: 0,
  onChange: (page) => {
    pagination.page = page
    fetchUploads()
  }
})
let visChart = null
let tiChart = null

// --- Upload Columns ---
const uploadColumns = [
  { title: 'ID', key: 'id', width: 60, align: 'center' },
  { title: '文件名', key: 'filename', width: 200, ellipsis: true, align: 'center' },
  { title: '描述', key: 'description', width: 150, ellipsis: true, align: 'center' },
  { 
    title: '数据行数', 
    key: 'row_count', 
    width: 100,
    align: 'center',
    render: (row) => h(NTag, { type: 'success', round: true, size: 'small' }, { default: () => row.row_count + ' 行' })
  },
  { 
    title: '上传时间', 
    key: 'created_at', 
    width: 180,
    align: 'center',
    render: (row) => h(NTime, { time: new Date(row.created_at), format: 'yyyy-MM-dd HH:mm:ss' })
  },
  { 
    title: '操作', 
    key: 'actions', 
    width: 180, 
    fixed: 'right',
    align: 'center',
    render(row) {
      const actions = [
        h(
          NButton,
          {
            size: 'small',
            type: 'info',
            secondary: true,
            onClick: () => openDetails(row)
          },
          { default: () => '查看' }
        )
      ]
      if (isAdmin.value) {
        actions.push(
          h(
            NPopconfirm,
            {
              onPositiveClick: () => handleDeleteUpload(row),
              positiveText: '确认',
              negativeText: '取消'
            },
            {
              trigger: () => h(
                NButton,
                {
                  size: 'small',
                  type: 'error',
                  secondary: true
                },
                { default: () => '删除' }
              ),
              default: () => '确认删除该上传记录吗？这将同时删除包含的所有数据。'
            }
          )
        )
      }
      return h('div', { style: 'display: flex; gap: 8px; justify-content: center;' }, actions)
    }
  }
]

// --- Detail Data Columns ---
const detailColumns = [
  { title: 'ID', key: 'id', width: 60, fixed: 'left' },
  { title: '批号', key: 'product_batch', width: 120, fixed: 'left', ellipsis: true },
  { title: '型号', key: 'product_model', width: 120 },
  { title: '助焊膏', key: 'flux_paste', width: 90 },
  { title: '黏度初值', key: 'viscosity_initial', width: 100, 
    render: (row) => typeof row.viscosity_initial === 'number' ? row.viscosity_initial.toFixed(2) : (row.viscosity_initial || '-') },
  { title: 'Ti', key: 'ti_index', width: 80 },
  { title: '锡粉规格', key: 'powder_spec', width: 100 },
  { title: '润湿等级', key: 'wetting_level', width: 90 },
  { title: '锡珠等级', key: 'solderball_level', width: 90 },
  { title: '坍塌类别', key: 'collapse_category', width: 90 },
  { title: '助焊剂%', key: 'flux_percent', width: 100 },
  { title: '氧含量', key: 'oxygen_real', width: 100 },
  { 
    title: '操作', 
    key: 'actions', 
    width: 150, 
    fixed: 'right',
    render(row) {
      if (!isAdmin.value) return h('div', { style: 'display: flex; gap: 8px;' }, [])
      return h('div', { style: 'display: flex; gap: 8px;' }, [
        h(
          NButton,
          {
            size: 'tiny',
            type: 'warning',
            secondary: true,
            onClick: () => openEditModal(row)
          },
          { default: () => '编辑' }
        ),
        h(
            NPopconfirm,
            {
              onPositiveClick: () => handleDeleteDetail(row),
              positiveText: '确认',
              negativeText: '取消'
            },
            {
              trigger: () => h(
                NButton,
                {
                  size: 'tiny',
                  type: 'error'
                },
                { default: () => '删除' }
              ),
              default: () => '确认删除该条数据吗？'
            }
          )
      ])
    }
  }
]

// --- Methods ---

const fetchStats = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/data/stats`)
    stats.value = res.data
    initCharts()
  } catch (err) {
    console.error(err)
    message.error("获取统计数据失败")
  }
}

const fetchUploads = async () => {
  loadingUploads.value = true
  try {
    const skip = (pagination.page - 1) * pagination.pageSize
    const res = await axios.get(`${API_BASE_URL}/uploads`, {
      params: { skip, limit: pagination.pageSize }
    })
    uploadList.value = res.data
    // Note: Assuming backend doesn't return total count for uploads yet, simplified for now
    pagination.itemCount = res.data.length < pagination.pageSize ? (pagination.page - 1) * pagination.pageSize + res.data.length : 100 
  } catch (err) {
    message.error("获取上传记录失败")
  } finally {
    loadingUploads.value = false
  }
}

// Upload Handling
const customUploadRequest = ({ file }) => {
    uploadFile.value = file.file
    if (!uploadForm.customFilename) {
        uploadForm.customFilename = file.name
    }
}

const handleUploadChange = (data) => {
    if (data.fileList.length === 0) {
        uploadFile.value = null
    }
}

const formatMetric = (value, digits = 2) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '-'
}

const formatRange = (summary, digits = 2) => {
  if (!summary) return '-'
  const min = Number(summary.min)
  const max = Number(summary.max)
  return Number.isFinite(min) && Number.isFinite(max) ? `${min.toFixed(digits)} ~ ${max.toFixed(digits)}` : '-'
}

const downloadTemplate = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/data/template`, { responseType: 'blob' })
    const blob = new Blob([res.data], { type: res.headers['content-type'] || 'application/octet-stream' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'solder_upload_template.xlsx'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(link.href)
    message.success('模板已开始下载')
  } catch (err) {
    message.error('模板下载失败')
  }
}

const submitUpload = async () => {
    if (!uploadFile.value) return
    
    uploading.value = true
    const formData = new FormData()
    formData.append('file', uploadFile.value)
    if (uploadForm.customFilename) {
        formData.append('custom_filename', uploadForm.customFilename)
    }
    
    try {
        const res = await axios.post(`${API_BASE_URL}/data/upload`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        })
        if (res.data.rejected) {
            message.error(res.data.message)
        } else if (res.data.duplicate) {
            message.warning(res.data.message)
        } else {
            message.success(res.data.message)
        }
        showUploadModal.value = false
        uploadFile.value = null
        uploadForm.customFilename = ''
        await fetchStats()
        await fetchUploads()
    } catch (err) {
        message.error("上传失败: " + (err.response?.data?.detail || err.message))
    } finally {
        uploading.value = false
    }
}

const openDetails = async (upload) => {
    currentUploadId.value = upload.id
    showDetailModal.value = true
    loadingDetails.value = true
    try {
        const res = await axios.get(`${API_BASE_URL}/uploads/${upload.id}/data`)
        detailData.value = res.data
    } catch (err) {
        message.error("获取详情失败")
    } finally {
        loadingDetails.value = false
    }
}

const openEditModal = (row) => {
    editFormModel.id = row.id
    editFormModel.viscosity_initial = row.viscosity_initial
    editFormModel.ti_index = row.ti_index
    editFormModel.powder_spec = row.powder_spec
    editFormModel.wetting_level = row.wetting_level
    editFormModel.solderball_level = row.solderball_level
    editFormModel.collapse_category = row.collapse_category
    showEditModal.value = true
}

const handleSaveEdit = async () => {
    savingEdit.value = true
    try {
        const res = await axios.put(`${API_BASE_URL}/data/${editFormModel.id}`, editFormModel)
        message.success("修改成功")
        
        // Update local data
        const index = detailData.value.findIndex(d => d.id === editFormModel.id)
        if (index !== -1) {
            Object.assign(detailData.value[index], res.data)
        }
        
        showEditModal.value = false
        // Refresh stats if needed, or just charts
        await fetchStats()
    } catch (err) {
        message.error("保存失败")
    } finally {
        savingEdit.value = false
    }
}

const handleDeleteDetail = async (row) => {
  try {
    await axios.delete(`${API_BASE_URL}/data/${row.id}`)
    message.success("删除成功")
    // Refresh local data
    detailData.value = detailData.value.filter(d => d.id !== row.id)
    // Update row count in upload list (optimistic)
    const upload = uploadList.value.find(u => u.id === currentUploadId.value)
    if (upload) upload.row_count--
    await fetchStats()
  } catch (err) {
    message.error("删除失败")
  }
}

const handleDeleteUpload = async (row) => {
    try {
        await axios.delete(`${API_BASE_URL}/uploads/${row.id}`)
        message.success("删除上传记录成功")
        await fetchUploads()
        await fetchStats()
    } catch (err) {
        message.error("删除失败")
    }
}

const handleClearAll = async () => {
  clearing.value = true
  try {
    const res = await axios.delete(`${API_BASE_URL}/data/clear-all`)
    message.success(res.data.message)
    await fetchUploads()
    await fetchStats()
    // hasData 会因 uploadList 清空而自动变为 false → 上传按钮自动解锁
  } catch (err) {
    message.error(err.response?.data?.detail || "清空失败")
  } finally {
    clearing.value = false
  }
}

const initCharts = () => {
  if (!stats.value.viscosity_dist) return

  // Viscosity Chart
  if (visChart) visChart.dispose()
  visChart = echarts.init(document.getElementById('viscosityChart'))
  visChart.setOption({
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(255, 255, 255, 0.9)', borderRadius: 8 },
    grid: { left: '1%', right: '1%', bottom: '3%', top: '5%', containLabel: true },
    xAxis: { 
      type: 'category', 
      data: stats.value.viscosity_dist.map((_, i) => i),
      show: false 
    },
    yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
    series: [{
      data: stats.value.viscosity_dist,
      type: 'bar',
      itemStyle: { 
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#83Baff' },
              { offset: 1, color: '#165DFF' }
          ]),
          borderRadius: [4, 4, 0, 0]
      },
      showBackground: true,
      backgroundStyle: { color: 'rgba(180, 180, 180, 0.1)' }
    }]
  })

  // Ti Chart
  if (tiChart) tiChart.dispose()
  tiChart = echarts.init(document.getElementById('tiChart'))
  tiChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '1%', right: '1%', bottom: '3%', top: '5%', containLabel: true },
    xAxis: { type: 'category', show: false },
    yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
    series: [{
      data: stats.value.ti_dist,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 3, color: '#00B42A' },
      areaStyle: { 
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(0, 180, 42, 0.4)' },
              { offset: 1, color: 'rgba(0, 180, 42, 0.01)' }
          ])
      }
    }]
  })
  
  // Responsive Resize
  window.addEventListener('resize', () => {
      visChart.resize()
      tiChart.resize()
  })
}

onMounted(async () => {
  await fetchStats()
  await fetchUploads()
})
</script>

<style scoped>
.data-platform {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Intro Card */
.intro-card {
  background: linear-gradient(135deg, #FFFFFF 0%, #F9F9FB 100%);
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
}

.intro-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
}

.title-group {
    display: flex;
    align-items: center;
    gap: 16px;
}

.icon-wrapper {
    width: 48px;
    height: 48px;
    background: #E8F3FF;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: #1D2129;
  margin: 0 0 4px 0;
}

.page-subtitle {
    color: #86909C;
    margin: 0;
}

.intro-right {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-right: 12px;
    flex-wrap: wrap;
}

.hero-stat-card {
    min-width: 132px;
    padding: 12px 14px;
    border-radius: 12px;
    background: linear-gradient(180deg, #FFFFFF 0%, #F7FAFF 100%);
    border: 1px solid #EAF2FF;
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.hero-stat-card strong {
    font-size: 22px;
    color: #1D2129;
}

.hero-stat-label {
    font-size: 12px;
    color: #86909C;
}

/* Charts */
.charts-grid {
  justify-content: center;
  max-width: 1400px;
  margin: 0 auto;
}

.chart-card {
    border-radius: 12px;
    background: #fff;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.02);
    transition: all 0.3s ease;
}

.hover-effect:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
}

.chart-container {
  height: 320px;
  width: 100%;
}

.chart-summary-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 10px;
}

.summary-chip {
    background: #F7F8FA;
    border: 1px solid #EEF0F3;
    border-radius: 12px;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.summary-chip span {
    font-size: 12px;
    color: #86909C;
}

.summary-chip strong {
    color: #1D2129;
    font-size: 15px;
}

/* Main Table */
.main-table-card {
    border-radius: 12px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.02);
}

.action-btn {
    box-shadow: 0 4px 12px rgba(22, 93, 255, 0.2);
}

.uploads-table {
    margin-top: 12px;
}

.upload-template-box {
    padding: 14px 16px;
    border-radius: 12px;
    background: #F7FAFF;
    border: 1px solid #D8E7FF;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
}

.upload-template-title {
    font-size: 14px;
    font-weight: 600;
    color: #1D2129;
    margin-bottom: 4px;
}

.upload-template-desc {
    font-size: 12px;
    color: #86909C;
    line-height: 1.6;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .intro-content {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }

  .intro-right {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-right: 0;
  }

  .hero-stat-card {
    min-width: 0;
  }

  .hero-stat-card strong {
    font-size: 20px;
  }

  .charts-grid {
    max-width: 100%;
  }

  .upload-template-box {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .uploads-table {
    overflow-x: auto;
  }
}
/* 移动端表格横向滑动：touch-action 让手指横滑稳定命中滚动容器 */
:deep(.n-data-table-wrapper) {
  -webkit-overflow-scrolling: touch;
  touch-action: pan-x;
}
</style>
