<script setup lang="ts">
// v2: removed empty-banner (2026-08-14)
import { computed, onMounted, ref } from 'vue'
import {
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NGrid,
  NGridItem,
  NIcon,
  NInput,
  NSpin,
  useMessage,
} from 'naive-ui'
import {
  AnalyticsOutline,
  BarChartOutline,
  CheckmarkCircleOutline,
  DocumentTextOutline,
  FolderOpenOutline,
  ImageOutline,
  LinkOutline,
  SearchOutline,
} from '@vicons/ionicons5'

import type { ArtifactInfo, DashboardOverview } from '../services/api'
import {
  fetchDashboardOverview,
  fetchDatasetRows,
  fetchLatestDeliveryArtifact,
  getLatestDeliveryDownloadUrl,
} from '../services/api'

type DashboardDisplayRow = {
  产品批号?: string
  锡膏型号?: string
  助焊膏?: string
  '助焊剂比例%'?: string | number
  '合金含量（%）'?: string | number
  合金牌号?: string
  锡粉批号?: string
  黏度初值?: string | number
  Ti?: string | number
  wetting_level?: string
  solderball_level?: string
  collapse_category?: string
}

const loading = ref(false)
const overview = ref<DashboardOverview | null>(null)
const latestDelivery = ref<ArtifactInfo | null>(null)
const displayRows = ref<DashboardDisplayRow[]>([])
const message = useMessage()

const displayColumns = [
  { title: '产品批号', key: '产品批号', width: 130 },
  { title: '锡膏型号', key: '锡膏型号', width: 130 },
  { title: '助焊膏', key: '助焊膏', width: 90 },
  { title: '助焊剂比例%', key: '助焊剂比例%', width: 110 },
  { title: '合金含量（%）', key: '合金含量（%）', width: 120 },
  { title: '合金牌号', key: '合金牌号', width: 120 },
  { title: '锡粉批号', key: '锡粉批号', width: 130 },
  { title: '黏度初值', key: '黏度初值', width: 100 },
  { title: 'Ti', key: 'Ti', width: 80 },
  { title: '润湿等级', key: '润湿等级', width: 100 },
  { title: '锡珠等级', key: '锡珠等级', width: 100 },
  { title: '坍塌类别', key: '坍塌类别', width: 100 },
]

const metricCards = computed(() => {
  const cards = overview.value?.metric_cards ?? {}
  return [
    {
      label: '已导入文件数',
      value: cards['已导入文件数'] ?? overview.value?.source_file_count ?? 0,
      icon: FolderOpenOutline,
      color: '#165DFF',
      note: '仅统计文件，不含文件夹',
    },
    {
      label: 'Excel 数据行数',
      value: cards['Excel数据行数'] ?? 0,
      icon: AnalyticsOutline,
      color: '#00B42A',
      note: '锡膏检测数据 + 锡膏配方数据行数',
    },
    {
      label: '图片齐全记录数',
      value: cards['图片齐全记录数'] ?? 0,
      icon: BarChartOutline,
      color: '#FF7D00',
      note: '4 类图片路径均非空',
    },
    {
      label: '待补图记录数',
      value: cards['待补图记录数'] ?? 0,
      icon: LinkOutline,
      color: '#F53F3F',
      note: 'Excel 行 - 图片齐全记录',
    },
  ]
})

const excelChartData = computed(() => {
  const breakdown = overview.value?.excel_breakdown ?? {}
  return ['有铅', '无铅'].map((lead) => ({
    lead,
    overall: breakdown[lead]?.overall ?? 0,
    specific: breakdown[lead]?.specific ?? 0,
  }))
})

const imageChartData = computed(() => {
  const breakdown = overview.value?.image_breakdown ?? {}
  return ['有铅', '无铅'].map((lead) => ({
    lead,
    value: breakdown[lead] ?? 0,
  }))
})

const excelSummary = computed(() => {
  const totalOverall = excelChartData.value.reduce((sum, item) => sum + item.overall, 0)
  const totalSpecific = excelChartData.value.reduce((sum, item) => sum + item.specific, 0)
  return {
    totalOverall,
    totalSpecific,
    totalExcel: totalOverall + totalSpecific,
  }
})

const excelHeaderStats = computed(() => [
  {
    label: 'Excel 合计',
    value: excelSummary.value.totalExcel,
    icon: DocumentTextOutline,
    tone: 'primary',
  },
  {
    label: '锡膏检测数据',
    value: excelSummary.value.totalOverall,
    icon: AnalyticsOutline,
    tone: 'overall',
  },
  {
    label: '锡膏配方数据',
    value: excelSummary.value.totalSpecific,
    icon: BarChartOutline,
    tone: 'specific',
  },
])

const imageMatchSummary = computed(() => {
  // 文件已清空时，强制全部归零，避免残留旧处理日志数据
  if ((overview.value?.source_file_count ?? 0) === 0) {
    return {
      total: 0,
      matched: 0,
      pending: 0,
      matchedLead: { leaded: 0, leadFree: 0 },
    }
  }
  const counts = overview.value?.latest_run?.summary?.counts ?? {}
  const totalFromSummary = Number(counts.image_inventory_records ?? 0)
  const totalFromBreakdown = imageChartData.value.reduce((sum, item) => sum + item.value, 0)
  const total = totalFromSummary > 0 ? totalFromSummary : totalFromBreakdown
  const matched = Number(counts.image_link_records ?? 0)
  const pending = Math.max(0, total - matched)
  const matchedBreakdown = overview.value?.image_match_breakdown ?? {}
  const matchedLead = {
    leaded: Number(matchedBreakdown['有铅'] ?? 0),
    leadFree: Number(matchedBreakdown['无铅'] ?? 0),
  }

  return {
    total,
    matched,
    pending,
    matchedLead,
  }
})

const imageHeaderStats = computed(() => [
  {
    label: '总图片数',
    value: imageMatchSummary.value.total,
    icon: ImageOutline,
    tone: 'image',
  },
  {
    label: '已匹配',
    value: imageMatchSummary.value.matched,
    icon: CheckmarkCircleOutline,
    tone: 'success',
  },
  {
    label: '待关联',
    value: imageMatchSummary.value.pending,
    icon: LinkOutline,
    tone: 'danger',
  },
])

const matchedLeadChartData = computed(() => {
  const leaded = imageMatchSummary.value.matchedLead.leaded
  const leadFree = imageMatchSummary.value.matchedLead.leadFree
  const total = Math.max(1, leaded + leadFree)
  return [
    { label: '有铅', value: leaded, tone: 'leaded', width: `${Math.round((leaded / total) * 100)}%` },
    { label: '无铅', value: leadFree, tone: 'leadfree', width: `${Math.round((leadFree / total) * 100)}%` },
  ]
})

const maxExcelValue = computed(() =>
  Math.max(1, ...excelChartData.value.flatMap((item) => [item.overall, item.specific])),
)
const maxImageValue = computed(() =>
  Math.max(1, ...imageChartData.value.map((item) => item.value)),
)
function calcBarWidth(value: number, maxValue: number) {
  return `${Math.max(10, Math.round((value / maxValue) * 100))}%`
}

async function loadOverview() {
  loading.value = true
  const minLoadingTimer = new Promise<void>((resolve) => setTimeout(resolve, 500))

  try {
    const [results] = await Promise.all([
      Promise.allSettled([
        fetchDashboardOverview(),
        fetchLatestDeliveryArtifact(),
      ]),
      minLoadingTimer,
    ])

    overview.value = results[0].status === 'fulfilled' ? results[0].value : null
    latestDelivery.value = results[1].status === 'fulfilled' ? results[1].value : null
  } catch (error: any) {
    console.error(error)
    message.error(error?.message ?? '系统总览加载失败')
  } finally {
    loading.value = false
  }
}

// 数据展示表：支持按产品批号模糊搜索（独立加载，搜索不刷新整个概览）
const searchKeyword = ref('')
const displayLoading = ref(false)

async function loadDisplayRows() {
  displayLoading.value = true
  try {
    const params: Record<string, unknown> = { page: 1, page_size: 200 }
    if (searchKeyword.value.trim()) {
      params.keyword = searchKeyword.value.trim()
    }
    const res = await fetchDatasetRows<DashboardDisplayRow>('delivery_dataset', params)
    displayRows.value = res.rows ?? []
  } catch (error: any) {
    console.error(error)
    message.error(error?.message ?? '数据展示表加载失败')
    displayRows.value = []
  } finally {
    displayLoading.value = false
  }
}

function handleSearch() {
  loadDisplayRows()
}

function handleClearSearch() {
  searchKeyword.value = ''
  loadDisplayRows()
}

onMounted(() => {
  loadOverview()
  loadDisplayRows()
})
</script>

<template>
  <div class="dashboard-container">
    <div class="header-section">
      <div class="title-block">
        <h1>数据概览</h1>
        <p>文件数按已导入文件统计，不含文件夹；图片齐全记录仅统计 4 类图片路径都已匹配的交付行。</p>
      </div>
      <n-button
        v-if="latestDelivery?.exists"
        tag="a"
        :href="getLatestDeliveryDownloadUrl()"
        target="_blank"
        type="primary"
        size="large"
      >
        下载最新汇总 Excel
      </n-button>
    </div>

    <n-spin :show="loading">
      <n-grid cols="1 s:2 m:4" :x-gap="20" :y-gap="20" responsive="screen" item-responsive>
        <n-grid-item v-for="item in metricCards" :key="item.label">
          <n-card :bordered="false" class="stat-card">
            <div class="stat-head">
              <div class="stat-icon" :style="{ backgroundColor: `${item.color}16`, color: item.color }">
                <n-icon :component="item.icon" size="22" />
              </div>
              <div class="stat-label">{{ item.label }}</div>
            </div>
            <div class="stat-value">{{ item.value }}</div>
            <div class="stat-note">{{ item.note }}</div>
          </n-card>
        </n-grid-item>
      </n-grid>

      <n-grid cols="1 m:12" :x-gap="20" :y-gap="20" class="section-grid" responsive="screen" item-responsive>
        <n-grid-item span="1 m:7">
          <n-card :bordered="false" class="panel-card chart-card">
            <template #header>
              <div class="panel-header">
                <div class="panel-title-block">
                  <span class="panel-title">Excel 数量分布</span>
                  <span class="panel-subtitle">按有铅 / 无铅查看锡膏检测与配方文件</span>
                </div>
                <div class="panel-header-stats">
                  <div v-for="item in excelHeaderStats" :key="item.label" class="summary-chip" :class="`summary-chip-${item.tone}`">
                    <div class="summary-chip-icon">
                      <n-icon :component="item.icon" size="15" />
                    </div>
                    <div class="summary-chip-body">
                      <span class="summary-chip-label">{{ item.label }}</span>
                      <strong class="summary-chip-value">{{ item.value }}</strong>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            <div class="chart-content">
              <div class="chart-legend">
                <span><i class="legend-dot overall"></i>锡膏检测数据</span>
                <span><i class="legend-dot specific"></i>锡膏配方数据</span>
              </div>
              <div v-if="excelChartData.every((item) => item.overall === 0 && item.specific === 0)" class="chart-empty">
                <n-empty description="暂无 Excel 统计结果" />
              </div>
              <div v-else class="chart-list">
                <div v-for="item in excelChartData" :key="item.lead" class="chart-row">
                  <div class="chart-label">{{ item.lead }}</div>
                  <div class="chart-bars">
                    <div class="bar-group">
                      <div class="bar-track">
                        <div class="bar-fill overall" :style="{ width: calcBarWidth(item.overall, maxExcelValue) }"></div>
                      </div>
                      <span class="bar-value">{{ item.overall }}</span>
                    </div>
                    <div class="bar-group">
                      <div class="bar-track">
                        <div class="bar-fill specific" :style="{ width: calcBarWidth(item.specific, maxExcelValue) }"></div>
                      </div>
                      <span class="bar-value">{{ item.specific }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </n-card>
        </n-grid-item>

        <n-grid-item span="1 m:5">
          <n-card :bordered="false" class="panel-card chart-card">
            <template #header>
              <div class="panel-header">
                <div class="panel-title-block">
                  <span class="panel-title">图片数量分布</span>
                  <span class="panel-subtitle">按有铅 / 无铅查看图片与匹配情况</span>
                </div>
                <div class="panel-header-stats">
                  <div v-for="item in imageHeaderStats" :key="item.label" class="summary-chip" :class="`summary-chip-${item.tone}`">
                    <div class="summary-chip-icon">
                      <n-icon :component="item.icon" size="15" />
                    </div>
                    <div class="summary-chip-body">
                      <span class="summary-chip-label">{{ item.label }}</span>
                      <strong class="summary-chip-value">{{ item.value }}</strong>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            <div class="chart-content">
              <div
                v-if="imageChartData.every((item) => item.value === 0) && imageMatchSummary.total === 0"
                class="chart-empty"
              >
                <n-empty description="暂无图片统计结果" />
              </div>
              <div v-else class="chart-list">
                <div v-for="item in imageChartData" :key="item.lead" class="chart-row image-row">
                  <div class="chart-label">{{ item.lead }}</div>
                  <div class="chart-bars">
                    <div class="bar-group single">
                      <div class="bar-track image">
                        <div class="bar-fill image" :style="{ width: calcBarWidth(item.value, maxImageValue) }"></div>
                      </div>
                      <span class="bar-value">{{ item.value }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div class="matched-section" v-if="imageMatchSummary.matched > 0">
              <div class="matched-section-head">
                <div class="matched-section-title">已匹配图片数量分布</div>
                <div class="matched-inline">
                  <div class="matched-inline-bar">
                    <div
                      v-for="item in matchedLeadChartData"
                      :key="item.label"
                      class="matched-inline-fill"
                      :class="item.tone"
                      :style="{ width: item.width }"
                    ></div>
                  </div>
                  <div class="matched-inline-legend">
                    <span v-for="item in matchedLeadChartData" :key="`${item.label}-legend`" class="matched-inline-legend-item">
                      <i class="matched-inline-dot" :class="item.tone"></i>
                      {{ item.label }} {{ item.value }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </n-card>
        </n-grid-item>
      </n-grid>

      <div class="section-grid">
        <n-card title="数据展示表" :bordered="false" class="panel-card data-card">
          <template #header-extra>
            <div class="search-bar">
              <n-input
                v-model:value="searchKeyword"
                placeholder="按产品批号搜索"
                clearable
                size="small"
                style="width: 100%; max-width: 200px"
                @keyup.enter="handleSearch"
                @clear="handleClearSearch"
              >
                <template #prefix>
                  <n-icon :component="SearchOutline" />
                </template>
              </n-input>
              <n-button type="primary" size="small" :loading="displayLoading" @click="handleSearch">
                搜索
              </n-button>
            </div>
          </template>
          <div v-if="searchKeyword.trim()" class="search-hint">
            当前筛选：产品批号 含「{{ searchKeyword.trim() }}」
          </div>
          <n-data-table
            v-if="displayRows.length"
            :columns="displayColumns"
            :data="displayRows"
            :loading="displayLoading"
            :scroll-x="820"
            :pagination="{ pageSize: 20, pageSizes: [10, 20, 50, 100] }"
            size="small"
            :bordered="false"
          />
          <div v-else class="table-empty">
            <n-empty :description="searchKeyword.trim() ? '未找到匹配的产品批号记录' : '暂无可展示的汇总数据'" />
          </div>
        </n-card>
      </div>
    </n-spin>
  </div>
</template>

<style scoped>
.dashboard-container {
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
  max-width: 820px;
  color: #86909c;
  font-size: 13px;
  line-height: 1.7;
}

.empty-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  margin-bottom: 24px;
  border: 1px dashed #b8d8ff;
  border-radius: 16px;
  background: linear-gradient(135deg, #eff6ff 0%, #f7fbff 100%);
}

.empty-title {
  margin-bottom: 4px;
  font-size: 16px;
  font-weight: 600;
  color: #1d2129;
}

.empty-sub {
  font-size: 13px;
  color: #4e5969;
}

.stat-card,
.panel-card {
  border-radius: 18px;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.05);
}

.stat-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-label {
  color: #4e5969;
  font-size: 14px;
  font-weight: 600;
}

.stat-value {
  margin-top: 20px;
  font-size: 34px;
  line-height: 1;
  font-weight: 700;
  color: #1d2129;
}

.stat-note {
  margin-top: 8px;
  font-size: 12px;
  color: #86909c;
}

.section-grid {
  margin-top: 24px;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  justify-content: space-between;
  width: 100%;
}

.panel-title-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 150px;
  flex: 1;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #1d2129;
}

.panel-subtitle {
  font-size: 11px;
  color: #86909c;
}

.panel-header-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: flex-start;
  justify-content: flex-end;
  max-width: 360px;
}

.summary-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 88px;
  padding: 5px 7px;
  border-radius: 10px;
  border: 1px solid transparent;
}

.summary-chip-icon {
  width: 22px;
  height: 22px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.summary-chip-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-chip-label {
  font-size: 10px;
  color: #86909c;
}

.summary-chip-value {
  font-size: 13px;
  line-height: 1;
  color: #1d2129;
}

.summary-chip-primary {
  background: #f5f9ff;
  border-color: #d9e8ff;
}

.summary-chip-primary .summary-chip-icon {
  background: #e8f3ff;
  color: #165dff;
}

.summary-chip-overall {
  background: #f5f9ff;
  border-color: #d9e8ff;
}

.summary-chip-overall .summary-chip-icon {
  background: #e8f3ff;
  color: #165dff;
}

.summary-chip-specific {
  background: #f3fffd;
  border-color: #d0f4ef;
}

.summary-chip-specific .summary-chip-icon {
  background: #e6fbf7;
  color: #14b8a6;
}

.summary-chip-image {
  background: #f7f5ff;
  border-color: #e5defd;
}

.summary-chip-image .summary-chip-icon {
  background: #efeaff;
  color: #7b61ff;
}

.summary-chip-success {
  background: #f2fbf7;
  border-color: #d4f3e3;
}

.summary-chip-success .summary-chip-icon {
  background: #e5f8ef;
  color: #00b578;
}

.summary-chip-danger {
  background: #fff5f5;
  border-color: #ffdede;
}

.summary-chip-danger .summary-chip-icon {
  background: #ffecec;
  color: #f53f3f;
}

.chart-legend {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
  color: #4e5969;
  font-size: 13px;
}

.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 6px;
  border-radius: 50%;
}

.legend-dot.overall {
  background: #165dff;
}

.legend-dot.specific {
  background: #36cfc9;
}

.chart-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0 
}

.chart-content {
  flex: 0 0 auto;
  padding: 5px 0 0px 0;
}

.chart-row {
  display: grid;
  grid-template-columns: 56px 1fr;
  gap: 15px;
  align-items: center;
}

.chart-label {
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
}

.chart-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bar-group {
  display: grid;
  grid-template-columns: 1fr 36px;
  align-items: center;
  gap: 8px;
}

.bar-group.single {
  grid-template-columns: 1fr 36px;
}

.bar-name,
.bar-value {
  font-size: 12px;
  color: #4e5969;
}

.bar-track {
  height: 12px;
  border-radius: 999px;
  background: #eef3fb;
  overflow: hidden;
}

.bar-track.image {
  height: 12px;
}

.bar-fill {
  height: 100%;
  border-radius: inherit;
}

.bar-fill.overall {
  background: linear-gradient(90deg, #165dff 0%, #4d8dff 100%);
}

.bar-fill.specific {
  background: linear-gradient(90deg, #36cfc9 0%, #63e0d5 100%);
}

.bar-fill.image {
  background: linear-gradient(90deg, #7b61ff 0%, #a38bff 100%);
}

.chart-empty {
  padding: 8px 0 2px;
}

.chart-card {
  height: 100%;
  min-height: 180px;
}

.chart-card :deep(.n-card-header) {
  padding-bottom: 6px;
}

.chart-card :deep(.n-card__content) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: auto;
  padding-top: 6px;
  padding-bottom: 12px;
}

.matched-section {
  margin-top: 15px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 8px;
  border-top: 1px solid #f2f3f5;
}

.matched-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.matched-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #1d2129;
}

.matched-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}

.matched-inline-bar {
  display: flex;
  width: 240px;
  height: 10px;
  border-radius: 999px;
  background: #eef3fb;
  overflow: hidden;
}

.matched-inline-fill {
  height: 100%;
}

.matched-inline-fill.leaded {
  background: linear-gradient(90deg, #6a5cff 0%, #8f82ff 100%);
}

.matched-inline-fill.leadfree {
  background: linear-gradient(90deg, #16c2a3 0%, #51ddc0 100%);
}

.matched-inline-legend {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.matched-inline-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #4e5969;
}

.matched-inline-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.matched-inline-dot.leaded {
  background: #6a5cff;
}

.matched-inline-dot.leadfree {
  background: #16c2a3;
}

.data-card :deep(.n-card__content) {
  padding-top: 8px;
}

.data-card :deep(.n-data-table-th),
.data-card :deep(.n-data-table-td) {
  padding-top: 10px;
  padding-bottom: 10px;
}

.table-empty {
  padding: 16px 0 8px;
}

.search-hint {
  font-size: 13px;
  color: #86909c;
  margin-bottom: 8px;
}

/* 卡片右上角搜索栏 */
.search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 卡片右上角搜索框与标题的垂直对齐微调 */
.data-card :deep(.n-card-header__extra) {
  padding-top: 2px;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .header-section {
    flex-direction: column;
    align-items: stretch;
  }

  .header-section .n-button {
    width: 100%;
  }

  .panel-header {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  .panel-header-stats {
    max-width: 100%;
    justify-content: flex-start;
  }

  .search-bar {
    flex-wrap: wrap;
  }
}
</style>
