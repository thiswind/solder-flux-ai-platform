<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NButton, NCard, NDataTable, NEmpty, NIcon, NInput, NSpin, useMessage } from 'naive-ui'
import { SearchOutline } from '@vicons/ionicons5'

import { fetchSourceGraph } from '../services/api'

const loading = ref(false)
const searchKeyword = ref('')
const traceRows = ref<any[]>([])
const message = useMessage()

const resultColumns = [
  { title: '批号', key: '批号', width: 180 },
  { title: '检测数据来源', key: 'overall数据源', ellipsis: true },
  { title: '配方数据来源', key: 'specific数据源', ellipsis: true },
  { title: '图片来源', key: '图片关联', ellipsis: true },
]

async function loadTraceRows() {
  loading.value = true
  try {
    const result = await fetchSourceGraph(searchKeyword.value)
    traceRows.value = result?.rows ?? []
  } catch (error) {
    console.error(error)
    message.error('来源数据加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadTraceRows)
</script>

<template>
  <div class="source-container">
    <div class="header-section">
      <div class="title-block">
        <h1>数据来源追溯</h1>
        <p>产品批号与生产批号已统一按“批号”展示，仅保留与追溯相关的来源信息。</p>
      </div>
    </div>

    <n-card :bordered="false" class="search-card">
      <template #header>
        <div class="card-title">数据追溯搜索</div>
      </template>
      <template #header-extra>
        <div class="search-bar">
          <n-input
            v-model:value="searchKeyword"
            placeholder="输入批号或文件名"
            clearable
            @keyup.enter="loadTraceRows"
          >
            <template #suffix>
              <n-icon :component="SearchOutline" />
            </template>
          </n-input>
          <n-button type="primary" @click="loadTraceRows">搜索</n-button>
        </div>
      </template>

      <n-spin :show="loading">
        <n-data-table
          :columns="resultColumns"
          :data="traceRows"
          :pagination="{ pageSize: 10 }"
          :bordered="false"
          size="small"
        />
        <div v-if="!loading && !traceRows.length" class="table-empty">
          <n-empty description="未找到匹配的来源记录" />
        </div>
      </n-spin>
    </n-card>
  </div>
</template>

<style scoped>
.source-container {
  max-width: 1400px;
  margin: 0 auto;
}

.header-section {
  margin-bottom: 24px;
}

.title-block h1 {
  margin: 0;
  font-size: 28px;
  color: #1d2129;
}

.title-block p {
  margin: 8px 0 0;
  color: #86909c;
  font-size: 14px;
}

.search-card {
  border-radius: 18px;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.05);
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  color: #1d2129;
}

.search-bar {
  display: flex;
  gap: 12px;
  width: 420px;
}

.table-empty {
  padding: 28px 0 8px;
}
</style>
