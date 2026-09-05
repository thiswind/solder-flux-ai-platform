<template>
  <div class="records-container">
    <n-card :bordered="false" class="records-card">
      <template #header>
        <div class="card-header">
          <span class="title">操作记录</span>
          <n-tag type="info" size="small" round>Total: {{ pagination.itemCount }}</n-tag>
        </div>
      </template>
      <template #header-extra>
        <n-space>
          <!-- Sort Buttons -->
          <n-button-group>
            <n-button size="small" :type="sortState.by === 'created_at' ? 'primary' : 'default'" @click="handleSort('created_at')">
              <template #icon>
                <n-icon><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8s8 3.58 8 8s-3.58 8-8 8zm.5-13H11v6l5.25 3.15l.75-1.23l-4.5-2.67z"/></svg></n-icon>
              </template>
              按时间
              <n-icon v-if="sortState.by === 'created_at'" size="small">
                 <svg v-if="sortState.order === 'desc'" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8l-8 8z"/></svg>
                 <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M20 12l-1.41-1.41L13 16.17V4h-2v12.17l-5.58-5.59L4 12l8 8l8-8z"/></svg>
              </n-icon>
            </n-button>
            <n-button size="small" :type="sortState.by === 'id' ? 'primary' : 'default'" @click="handleSort('id')">
              <template #icon>
                <n-icon><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M10 20h4V4h-4v16zm-6 0h4v-8H4v8zM16 9v11h4V9h-4z"/></svg></n-icon>
              </template>
              按ID
              <n-icon v-if="sortState.by === 'id'" size="small">
                 <svg v-if="sortState.order === 'desc'" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8l-8 8z"/></svg>
                 <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M20 12l-1.41-1.41L13 16.17V4h-2v12.17l-5.58-5.59L4 12l8 8l8-8z"/></svg>
              </n-icon>
            </n-button>
          </n-button-group>

          <n-input-group>
            <n-input
                v-model:value="searchQuery"
                placeholder="搜索实验 ID / 名称..."
                :style="{ width: '100%', maxWidth: '240px' }"
                @keyup.enter="handleSearch"
            >
              <template #prefix>
                <n-icon color="#C2C2C2"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5A6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5S14 7.01 14 9.5S11.99 14 9.5 14z"/></svg></n-icon>
              </template>
            </n-input>
            <n-button type="primary" ghost @click="handleSearch">搜索</n-button>
          </n-input-group>
          <n-button secondary circle @click="fetchHistory">
            <template #icon><n-icon><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg></n-icon></template>
          </n-button>
          <n-button type="default" :loading="exporting" @click="handleExportRecords">导出记录</n-button>
          <n-button v-if="isAdmin" type="error" ghost @click="handleClearRecords">清空记录</n-button>
        </n-space>
      </template>
      
      <n-data-table
        :columns="columns"
        :data="data"
        :loading="loading"
        :pagination="false"
        :scroll-x="840"
        :row-key="row => row.id"
        size="large"
        class="fixed-height-table"
      />
      
      <!-- Custom Pagination (Centered) -->
      <div class="pagination-wrapper">
        <n-pagination
          v-model:page="pagination.page"
          :page-size="pagination.pageSize"
          :item-count="pagination.itemCount"
          @update:page="handlePageChange"
          size="large"
          show-quick-jumper
        >
        </n-pagination>
      </div>
    </n-card>

    <!-- Details Modal (Changed from Drawer) -->
    <n-modal 
      v-model:show="showModal" 
      preset="card"
      style="width: 90%; max-width: 700px;"
      :title="currentRecord?.experiment_name || '记录详情'"
    >
      <template #header>
         <n-space align="center">
           <span style="font-weight: 600; font-size: 16px;">{{ currentRecord?.experiment_name }}</span>
           <n-tag :type="getRecordType(currentRecord?.experiment_name).type" size="small">
             {{ getRecordType(currentRecord?.experiment_name).label }}
           </n-tag>
         </n-space>
      </template>
      
      <div v-if="currentRecord" class="modal-body">
         <n-divider title-placement="left">配方参数 (输入)</n-divider>
         <n-descriptions label-placement="left" bordered :column="2" size="small">
           <n-descriptions-item v-for="(val, key) in currentRecord.composition_x" :key="key" :label="translateKey(key)">
             <n-tag :bordered="false" type="info" size="small">{{ val }}</n-tag>
           </n-descriptions-item>
         </n-descriptions>

         <n-divider title-placement="left" style="margin-top: 24px;">性能指标 (输出/目标)</n-divider>
         <n-descriptions label-placement="left" bordered :column="2" size="small">
           <n-descriptions-item v-for="(val, key) in currentRecord.properties_y" :key="key" :label="translateKey(key)">
             <span style="font-weight: 600; color: #165DFF">{{ val }}</span>
           </n-descriptions-item>
         </n-descriptions>
         
         <div class="meta-info">
           <n-text depth="3">操作时间: {{ new Date(currentRecord.created_at).toLocaleString() }}</n-text>
           <br>
           <n-text depth="3">记录 ID: {{ currentRecord.id }}</n-text>
         </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, h, computed } from 'vue'
import { useMessage, useDialog, NTag, NTime, NButton, NSpace, NAvatar, NIcon, NPagination } from 'naive-ui'
import axios from 'axios'
import { roleState } from '../role'

const message = useMessage()
const dialog = useDialog()
const isAdmin = computed(() => roleState.role === 'Admin')
const exporting = ref(false)
const API_BASE_URL = import.meta.env.BASE_URL + 'api/v1'

const loading = ref(false)
const data = ref([])
const showModal = ref(false)
const currentRecord = ref(null)

// Sorting State
const sortState = reactive({
  by: 'created_at', // 'created_at' | 'id'
  order: 'desc'     // 'desc' | 'asc'
})

const pagination = reactive({
  page: 1,
  pageSize: 10,
  itemCount: 0
})

const handlePageChange = (page) => {
  pagination.page = page
  fetchHistory()
}

// Translation Map
const labelMap = {
  // Common
  'flux_type': '助焊膏型号',
  'flux_percent': '助焊剂比例',
  'alloy_content': '合金含量',
  'viscosity': '黏度初值 (Pa·s)',
  'ti': '触变指数 (Ti)',
  'powder_spec': '锡粉规格',
  'sn': '锡 (Sn)',
  'pb': '铅 (Pb)',
  'ag': '银 (Ag)',
  'cu': '铜 (Cu)',
  'fe': '铁 (Fe)',
  'bi': '铋 (Bi)',
  'sb': '锑 (Sb)',
  'oxygen': '氧含量 (O)',
  'oxygen_real': '氧含量 (O)',
  'accuracy': '模型精度',
  'data_count': '训练数据量',
  'result': '训练结果',
  // Backward specifics (sometimes keys are different or English)
  'Flux Type': '助焊膏型号',
  'Flux %': '助焊剂比例',
  'Alloy %': '合金含量',
  'Oxygen': '氧含量'
}

const translateKey = (key) => {
  // Normalize key
  const normalized = key.toLowerCase()
  // Check exact match first
  if (labelMap[key]) return labelMap[key]
  // Check normalized match
  for (const k in labelMap) {
      if (k.toLowerCase() === normalized) return labelMap[k]
  }
  // Common suffixes/prefixes check
  if (normalized.includes('flux')) return '助焊剂相关'
  
  return key // Fallback to original
}

// Helper to determine type
const getRecordType = (name) => {
    if (!name) return { type: 'default', label: 'Unknown' }
    if (name.includes('Forward')) return { type: 'success', label: '正向推理' }
    if (name.includes('Backward')) return { type: 'warning', label: '反向推理' }
    if (name.includes('Training')) return { type: 'info', label: '模型训练' }
    if (name.includes('Vision')) return { type: 'error', label: '图像识别' }
    if (name.includes('Upload')) return { type: 'primary', label: '数据上传' }
    return { type: 'default', label: '其他操作' }
}

const columns = [
  { 
      title: 'ID', 
      key: 'id', 
      width: 80,
      align: 'center',
      render: (row) => h('span', { style: 'font-family: monospace; color: #86909C;' }, `#${row.id}`)
  },
  { 
      title: '操作类型', 
      key: 'type', 
      width: 150,
      align: 'center',
      render(row) {
          const { type, label } = getRecordType(row.experiment_name)
          return h(NTag, { type, bordered: false, round: true }, { default: () => label })
      }
  },
  { 
      title: '操作名称', 
      key: 'experiment_name', 
      align: 'center',
      render: (row) => h('span', { style: 'font-weight: 500;' }, row.experiment_name)
  },
  { 
    title: '关键摘要', 
    key: 'summary',
    align: 'center',
    render(row) {
        // Create a mini summary string
        const x = row.composition_x || {}
        const y = row.properties_y || {}
        
        let content = []
        if (row.experiment_name?.includes('Forward')) {
            content.push(`Sn: ${x.sn || '-'}%`)
            content.push(`Flux: ${x.flux_percent || '-'}%`)
            content.push(`-> Visc: ${y.viscosity}`)
        } else if (row.experiment_name?.includes('Backward')) {
            content.push(`Target Visc: ${y.viscosity}`)
            content.push(`-> Rec Flux: ${x['助焊剂比例'] || x['Flux'] || '-'}`)
        } else if (row.experiment_name?.includes('Vision')) {
             content.push(`File: ${x.filename || '-'}`)
             content.push(`Result: ${y.count || 0} objects`)
         } else if (row.experiment_name?.includes('Upload')) {
            content.push(`File: ${x.filename || '-'}`)
            content.push(`Rows: ${y.row_count || '-'}`)
        } else {
            content.push('点击查看详情...')
        }
        
        return h(NSpace, { size: 'small', justify: 'center' }, { default: () => content.map(c => h(NTag, { size: 'small', color: { color: '#F7F8FA', textColor: '#1D2129', borderColor: '#E5E6EB' } }, { default: () => c })) })
    }
  },
  { 
    title: '操作时间', 
    key: 'created_at', 
    width: 180,
    align: 'center',
    render: (row) => h(NTime, { time: new Date(row.created_at), format: 'yyyy-MM-dd HH:mm' })
  },
  {
      title: '操作',
      key: 'actions',
      width: 100,
      fixed: 'right',
      align: 'center',
      render(row) {
          return h(
              NButton,
              {
                  size: 'small',
                  type: 'primary',
                  ghost: true,
                  onClick: () => {
                      currentRecord.value = row
                      showModal.value = true
                  }
              },
              { default: () => '查看详情' }
          )
      }
  }
]

const searchQuery = ref('')

const fetchHistory = async () => {
  loading.value = true
  try {
    const skip = (pagination.page - 1) * pagination.pageSize
    const res = await axios.get(`${API_BASE_URL}/history`, {
      params: { 
          skip, 
          limit: pagination.pageSize,
          search: searchQuery.value,
          sort_by: sortState.by,
          order: sortState.order
      }
    })
    
    // Updated response structure handling
    if (res.data.items && typeof res.data.total === 'number') {
        data.value = res.data.items
        pagination.itemCount = res.data.total
    } else if (Array.isArray(res.data)) {
        // Fallback for old API if needed (though we updated it)
        data.value = res.data
        if (res.data.length === pagination.pageSize) {
            pagination.itemCount = (pagination.page) * pagination.pageSize + 1 
        } else {
            pagination.itemCount = (pagination.page - 1) * pagination.pageSize + res.data.length
        }
    }
    
  } catch (err) {
    message.error("获取记录失败")
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
    pagination.page = 1
    fetchHistory()
}

const handleSort = (field) => {
    if (sortState.by === field) {
        // Toggle order
        sortState.order = sortState.order === 'desc' ? 'asc' : 'desc'
    } else {
        sortState.by = field
        sortState.order = 'desc' // Default new sort to desc
    }
    fetchHistory()
}

async function handleExportRecords() {
  exporting.value = true
  try {
    const res = await axios.get(`${API_BASE_URL}/history/export`, {
      params: { search: searchQuery.value, sort_by: sortState.by, order: sortState.order },
      responseType: 'blob',
    })
    // 检查是否实际是错误响应（blob 模式下 axios 不会自动抛非 2xx）
    const contentType = res.headers['content-type'] || ''
    if (contentType.includes('application/json') || res.data.type === 'application/json' || res.data.size < 200) {
      const text = await res.data.text()
      try {
        const errJson = JSON.parse(text)
        message.error(errJson.detail || '导出失败')
      } catch {
        message.error('导出失败: ' + text.slice(0, 200))
      }
      return
    }
    const blob = res.data
    const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '').replace(' ', '_')
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `operation_records_${ts}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  } catch (e) {
    // blob 模式下 500 响应的 data 是 Blob 对象，需要读出文本
    const errData = e?.response?.data
    if (errData instanceof Blob) {
      try {
        const text = await errData.text()
        try {
          const errJson = JSON.parse(text)
          message.error('导出失败: ' + (errJson.detail || text.slice(0, 200)))
        } catch {
          message.error('导出失败: ' + text.slice(0, 200))
        }
      } catch {
        message.error('导出失败: 无法读取错误信息')
      }
    } else {
      message.error('导出失败: ' + (e?.response?.data?.detail || e?.message || '未知错误'))
    }
  } finally {
    exporting.value = false
  }
}

function handleClearRecords() {
  dialog.warning({
    title: '清空全部操作记录',
    content: '将删除所有操作记录（不可恢复），不影响训练数据与上传记录。是否继续？',
    positiveText: '确认清空',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await axios.delete(`${API_BASE_URL}/history/clear`)
        message.success('已清空全部操作记录')
        pagination.page = 1
        fetchHistory()
      } catch (e) {
        message.error('清空失败')
      }
    },
  })
}

onMounted(() => {
  fetchHistory()
})
</script>

<style scoped>
.records-container {
    padding: 0;
}
.records-card {
    border-radius: 8px;
    box-shadow: 0 1px 2px -2px rgba(0, 0, 0, 0.08), 0 3px 6px 0 rgba(0, 0, 0, 0.06), 0 5px 12px 4px rgba(0, 0, 0, 0.04); 
}
.card-header {
    display: flex;
    align-items: center;
    gap: 12px;
}
.title {
    font-size: 18px;
    font-weight: 600;
    color: #1D2129;
}
.modal-body {
    padding: 0 4px;
}
.meta-info {
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px dashed #E5E6EB;
    font-size: 12px;
}

/* Pagination Centering */
.pagination-wrapper {
    display: flex;
    justify-content: center;
    margin-top: 20px;
    padding-bottom: 10px;
}

/* Fixed Table Height to prevent layout shift */
.fixed-height-table {
  /* Adjusted for exactly 10 rows + header */
  /* Each row is approx 55px (large size), header 50px */
  /* 55 * 10 + 50 = 600px approx */
  min-height: 500px; 
}

/* Ensure empty body fills the space */
:deep(.n-data-table-base-table-body) {
    min-height: 550px; 
}

/* 移动端适配 */
@media (max-width: 768px) {
  .fixed-height-table {
    min-height: auto;
  }

  :deep(.n-data-table-base-table-body) {
    min-height: auto;
  }

  .records-card :deep(.n-card-header) {
    flex-direction: column !important;
    align-items: stretch !important;
    padding: 12px 14px !important;
    row-gap: 12px;
  }

  .records-card :deep(.n-card-header__main) {
    width: 100% !important;
    min-width: 0 !important;
  }

  .records-card :deep(.n-card-header__extra) {
    width: 100% !important;
    margin-top: 0 !important;
  }

  .records-card :deep(.n-card-header__extra) > .n-space,
  .records-card :deep(.n-card-header__extra) .n-space {
    display: flex !important;
    flex-wrap: wrap !important;
    width: 100% !important;
    gap: 8px !important;
  }

  .records-card :deep(.n-card-header__extra) .n-space > * {
    margin-bottom: 0 !important;
  }

  .records-card :deep(.n-card-header__extra) .n-input-group {
    flex-wrap: wrap !important;
    width: 100%;
  }

  .records-card :deep(.n-card-header__extra) .n-input-group > .n-input {
    width: 100% !important;
    min-width: 0 !important;
    max-width: none !important;
  }

  .records-card :deep(.n-card-header__extra) .n-button,
  .records-card :deep(.n-card-header__extra) .n-button-group {
    width: 100% !important;
    justify-content: stretch;
  }

  .records-card :deep(.n-card-header__extra) .n-button-group > .n-button {
    flex: 1;
  }

  .records-card :deep(.n-card-header__extra) .n-button {
    min-height: 36px;
  }
}
</style>
