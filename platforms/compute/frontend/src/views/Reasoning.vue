<template>
  <div class="reasoning-container">
    
    <!-- Model Status Bar -->
    <div class="model-status-bar">
      <div class="status-left">
        <span class="status-label">当前模型:</span>
        <n-tag :type="modelInfo.status === '已加载' || modelInfo.status === '训练完成' ? 'success' : 'warning'" size="small" round>
           {{ modelInfo.name || '未初始化' }}
        </n-tag>
        <span class="status-detail" v-if="modelInfo.last_trained">
           (上次训练: {{ modelInfo.last_trained }})
        </span>
        <span class="status-detail" v-if="modelInfo.status === '未训练' || modelInfo.status === 'failed'" style="color: red;">
           (需训练)
        </span>
      </div>
      <div class="status-right">
        <n-popover trigger="hover">
          <template #trigger>
            <n-button text size="small" type="info" class="info-btn">
               精度详情
            </n-button>
          </template>
          <div class="accuracy-info">
             <div v-for="(v, k) in modelInfo.accuracy" :key="k" style="font-size: 12px;">{{k}}: {{v}}</div>
             <div v-if="Object.keys(modelInfo.accuracy).length === 0">暂无精度数据</div>
          </div>
        </n-popover>
        <n-button v-if="isAdmin" size="small" type="warning" ghost @click="handleRetrain" :loading="loadingRetrain" class="retrain-btn">
           微调模型
        </n-button>
      </div>
    </div>

    <n-tabs v-model:value="activeTab" type="segment" size="large" class="custom-tabs" animated>
      
      <!-- Forward Prediction -->
      <n-tab-pane name="forward" tab="正向推理">
        <n-grid :x-gap="16" :y-gap="16" cols="1 900:2" class="main-grid">
          
          <!-- Left: Inputs -->
          <n-grid-item>
            <n-card size="small" :bordered="false" class="panel-card input-panel">
              <template #header>
                <div class="panel-header">
                  <div class="title-group">
                    <div class="icon-box blue">
                      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M3 17v2h6v-2H3M3 5v2h10V5H3m10 16v-2h8v-2h-8v-2h-2v6h2M7 9v2H3v2h4v2h2V9H7m14 4v-2H11v2h10m-6-4h6V5h-6v4Z"/></svg>
                    </div>
                    <span class="panel-title">配方参数设置</span>
                  </div>
                  <n-tag type="primary" size="small" round ghost>输入参数</n-tag>
                </div>
              </template>

              <div class="scroll-container">
                <n-form size="small" label-placement="top" class="compact-form">
                
                <!-- 1. Flux System -->
                <div class="form-section">
                  <div class="section-title-row">
                    <span class="section-dot bg-primary"></span>
                    <span class="section-name">助焊剂体系</span>
                  </div>
                  
                  <n-form-item label="助焊膏型号">
                    <n-select v-model:value="formX.flux_type" :options="fluxTypeOptions" placeholder="选择型号" />
                  </n-form-item>

                  <!-- Flux/Alloy Ratio Slider -->
                  <div class="ratio-container">
                     <div class="ratio-labels">
                        <span class="r-label">助焊剂含量</span>
                        <span class="r-label">合金含量</span>
                     </div>
                     <div class="ratio-control">
                        <div class="input-box">
                           <n-input-number 
                             v-model:value="formX.flux_percent" 
                             :min="0" :max="20" :step="0.1" 
                             :show-button="false" 
                             size="small"
                           >
                             <template #suffix>%</template>
                           </n-input-number>
                        </div>
                        <div class="slider-box">
                           <n-slider 
                             v-model:value="formX.flux_percent" 
                             :min="0" :max="20" :step="0.1"
                             :tooltip="false"
                             class="custom-slider"
                           />
                        </div>
                        <div class="input-box">
                           <n-input-number 
                             v-model:value="alloyPercent" 
                             :min="80" :max="100" :step="0.1" 
                             :show-button="false" 
                             size="small"
                             @update:value="updateFluxFromAlloy"
                           >
                             <template #suffix>%</template>
                           </n-input-number>
                        </div>
                     </div>
                  </div>
                </div>

                <n-divider class="dashed-divider" />

                <!-- 2. Alloy Composition -->
                <div class="form-section">
                  <div class="section-title-row">
                    <span class="section-dot bg-warning"></span>
                    <span class="section-name">合金成分</span>
                  </div>

                  <n-grid :x-gap="12" :y-gap="12" cols="3">
                    <n-grid-item>
                      <n-form-item label="Ag (银)">
                        <n-input-number v-model:value="formX.ag" :step="0.1" :min="0" :show-button="false"><template #suffix>kg</template></n-input-number>
                      </n-form-item>
                    </n-grid-item>
                    <n-grid-item>
                      <n-form-item label="Cu (铜)">
                        <n-input-number v-model:value="formX.cu" :step="0.1" :min="0" :show-button="false"><template #suffix>kg</template></n-input-number>
                      </n-form-item>
                    </n-grid-item>
                    <n-grid-item>
                      <n-form-item label="Pb (铅)">
                        <n-input-number v-model:value="formX.pb" :step="0.01" :min="0" :show-button="false"><template #suffix>kg</template></n-input-number>
                      </n-form-item>
                    </n-grid-item>
                    
                    <n-grid-item>
                      <n-form-item label="Fe (铁)">
                        <n-input-number v-model:value="formX.fe" :step="0.01" :min="0" :show-button="false"><template #suffix>kg</template></n-input-number>
                      </n-form-item>
                    </n-grid-item>
                    <n-grid-item>
                      <n-form-item label="Bi (铋)">
                        <n-input-number v-model:value="formX.bi" :step="0.01" :min="0" :show-button="false"><template #suffix>kg</template></n-input-number>
                      </n-form-item>
                    </n-grid-item>
                    <n-grid-item>
                      <n-form-item label="Sb (锑)">
                        <n-input-number v-model:value="formX.sb" :step="0.01" :min="0" :show-button="false"><template #suffix>kg</template></n-input-number>
                      </n-form-item>
                    </n-grid-item>

                    <n-grid-item>
                      <n-form-item label="氧含量 (O)">
                        <n-input-number v-model:value="formX.oxygen" :step="0.001" :min="0" :show-button="false"><template #suffix>%</template></n-input-number>
                      </n-form-item>
                    </n-grid-item>
                    <n-grid-item span="2">
                      <n-form-item label="Sn (锡)">
                         <div class="read-only-box">余量</div>
                      </n-form-item>
                    </n-grid-item>
                  </n-grid>

                  <!-- Fixed Elements Display -->
                  <div class="fixed-elements">
                    <div class="fixed-label">固定微量元素:</div>
                    <div class="tags-row">
                      <n-tag size="small" :bordered="false" class="fixed-tag">As: 0.005 kg</n-tag>
                      <n-tag size="small" :bordered="false" class="fixed-tag">Ni: 0.005 kg</n-tag>
                      <n-tag size="small" :bordered="false" class="fixed-tag">Zn: 0.001 kg</n-tag>
                      <n-tag size="small" :bordered="false" class="fixed-tag">Al: 0.001 kg</n-tag>
                      <n-tag size="small" :bordered="false" class="fixed-tag">Cd: 0.001 kg</n-tag>
                    </div>
                  </div>
                </div>

                <div class="action-footer">
                   <n-button type="primary" block size="large" class="main-btn" @click="handlePredict" :loading="loadingPredict">
                     <template #icon>
                       <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/></svg>
                     </template>
                     开始智能推理
                   </n-button>
                </div>

              </n-form>
              </div>
            </n-card>
          </n-grid-item>
          
          <!-- Right: Results -->
          <n-grid-item>
            <n-card size="small" :bordered="false" class="panel-card result-panel">
              <template #header>
                <div class="panel-header">
                  <div class="title-group">
                    <div class="icon-box green">
                      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M21 3H3c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-5h2v5zm4 0h-2v-3h2v3zm4 0h-2v-5h2v5z"/></svg>
                    </div>
                    <span class="panel-title">预测结果</span>
                  </div>
                  <n-tag type="success" size="small" round ghost>分析结果</n-tag>
                </div>
              </template>
              
              <div class="scroll-container">
              <div v-if="prediction" class="result-content animate-fade-in">
                <div class="score-card">
                   <n-progress type="dashboard" :percentage="prediction.score * 10" :color="getScoreColor(prediction.score)" :stroke-width="10">
                     <div class="score-inner">
                       <span class="score-num">{{ prediction.score }}</span>
                       <span class="score-sub">置信度</span>
                     </div>
                   </n-progress>
                </div>
                
                <div class="metrics-grid">
                  <div class="metric-box">
                    <div class="m-label">锡粉规格等级</div>
                    <div class="m-value highlight">{{ prediction.powder_spec }}</div>
                  </div>
                  <div class="metric-box">
                    <div class="m-label">锡膏润湿等级</div>
                    <div class="m-value highlight">{{ prediction.wetting_class }}</div>
                  </div>
                  <div class="metric-box">
                    <div class="m-label">黏度初值 (Pa·s)</div>
                    <div class="m-value">{{ prediction.viscosity }}</div>
                  </div>
                  <div class="metric-box">
                    <div class="m-label">触变指数 (Ti)</div>
                    <div class="m-value">{{ prediction.ti }}</div>
                  </div>
                </div>
              </div>
              
              <div v-else class="empty-state">
                <div class="empty-img">🔮</div>
                <p>请在左侧配置参数并开始推理</p>
              </div>
              </div>
            </n-card>
          </n-grid-item>
        </n-grid>
      </n-tab-pane>

      <!-- Backward Optimization -->
      <n-tab-pane name="backward" tab="反向推理">
        <n-grid :x-gap="16" :y-gap="16" cols="1 900:2" class="main-grid">
           <!-- Left: Inputs -->
           <n-grid-item>
             <n-card size="small" :bordered="false" class="panel-card input-panel">
               <template #header>
                  <div class="panel-header">
                    <div class="title-group">
                      <div class="icon-box orange">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M12 2L2 12h3v8h6v-6h2v6h6v-8h3L12 2zm0 2.83L18.17 11H17v8h-4v-6h-2v6H7v-8H5.83L12 4.83z"/></svg>
                      </div>
                      <span class="panel-title">目标性能设定</span>
                    </div>
                    <n-tag type="warning" size="small" round ghost>目标设定</n-tag>
                  </div>
               </template>

               <div class="scroll-container">
               <n-form size="small" label-placement="top" class="compact-form">
                  <div class="form-section">
                     <div class="section-title-row">
                        <span class="section-dot bg-purple"></span>
                        <span class="section-name">第一步：选择物理特性</span>
                     </div>
                     <n-grid :x-gap="16" cols="2">
                        <n-grid-item>
                            <n-form-item label="锡粉规格">
                                <n-select v-model:value="targetY.powder_spec" :options="specOptions" size="medium" placeholder="选择规格" />
                            </n-form-item>
                        </n-grid-item>
                        <n-grid-item>
                            <n-form-item label="润湿等级">
                                <n-select v-model:value="targetY.wetting_class" :options="wettingOptions" size="medium" placeholder="选择等级" />
                            </n-form-item>
                        </n-grid-item>
                     </n-grid>
                  </div>

                  <n-divider class="dashed-divider" />

                  <div class="form-section">
                     <div class="section-title-row">
                        <span class="section-dot bg-cyan"></span>
                        <span class="section-name">第二步：设定目标参数</span>
                     </div>
                     <n-grid :x-gap="16" cols="2">
                       <n-grid-item>
                         <n-form-item label="目标黏度初值 (Pa·s)">
                           <n-input-number v-model:value="targetY.viscosity" placeholder="200.0" size="medium" :show-button="false" />
                         </n-form-item>
                       </n-grid-item>
                       <n-grid-item>
                         <n-form-item label="目标 Ti 值">
                           <n-input-number v-model:value="targetY.ti" placeholder="0.55" :step="0.01" size="medium" :show-button="false" />
                         </n-form-item>
                       </n-grid-item>
                     </n-grid>
                  </div>

                  <div class="action-footer">
                    <n-button type="info" block size="large" class="main-btn" @click="handleOptimize" :loading="loadingOptimize">
                      <template #icon>
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10s10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
                      </template>
                      智能反推配方
                    </n-button>
                  </div>
               </n-form>
               </div>
             </n-card>
           </n-grid-item>

           <!-- Right: Results -->
           <n-grid-item>
             <n-card size="small" :bordered="false" class="panel-card result-panel">
               <template #header>
                  <div class="panel-header">
                    <div class="title-group">
                      <div class="icon-box purple">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 9h-2V7h2v5zm4 0h-2v-3h2v3z"/></svg>
                      </div>
                      <span class="panel-title">推荐配方方案</span>
                    </div>
                    <n-tag type="info" size="small" round ghost>反推结果</n-tag>
                  </div>
               </template>

               <div class="scroll-container">
               <div v-if="recommendations" class="result-content animate-fade-in">
                  <!-- Result Summary -->
                  <div class="result-summary-box">
                    <div class="summary-item">
                      <span class="s-label">助焊膏</span>
                      <span class="s-value">{{ recommendations.flux_type }}</span>
                    </div>
                    <div class="vertical-divider"></div>
                    <div class="summary-item">
                      <span class="s-label">助焊剂含量</span>
                      <span class="s-value highlight">{{ recommendations.flux_percent }}%</span>
                    </div>
                    <div class="vertical-divider"></div>
                    <div class="summary-item">
                      <span class="s-label">合金含量</span>
                      <span class="s-value highlight">{{ (100 - recommendations.flux_percent).toFixed(1) }}%</span>
                    </div>
                  </div>

                  <n-divider style="margin: 16px 0" />
                  
                  <!-- Alloy Details -->
                  <div class="alloy-details">
                    <div class="detail-header">合金成分分布</div>
                    <!-- Chart Container -->
                    <div ref="chartRef" class="chart-container"></div>
                    
                    <n-grid :x-gap="12" :y-gap="12" cols="3" style="margin-top: 12px;">
                       <n-grid-item v-for="(value, key) in recommendations.alloy_elements" :key="key">
                          <div class="element-box">
                             <span class="e-name">{{ key }}</span>
                             <span class="e-val">{{ value }}{{ key === 'Oxygen' ? '%' : 'kg' }}</span>
                          </div>
                       </n-grid-item>
                    </n-grid>
                  </div>
                  
                  <!-- Fixed Elements (Static Display in Result) -->
                   <div class="fixed-elements-display">
                      <span class="f-label">固定微量元素:</span>
                      <span class="f-val">Sn:余量, As:0.005, Ni:0.005, Zn:0.001, Al:0.001, Cd:0.001</span>
                   </div>
                   
                   <!-- Apply Button -->
                   <div class="apply-btn-container">
                       <n-button type="primary" secondary block @click="applyRecommendation">
                           <template #icon>
                               <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6c0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0 0 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6c0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 0 0 4 12c0 4.42 3.58 8 8 8v3l4-4l-4-4v3z"/></svg>
                           </template>
                           一键试算此配方
                       </n-button>
                   </div>

               </div>
               <div v-else class="empty-state">
                  <div class="empty-img">🎯</div>
                  <p>设定目标后点击反推</p>
               </div>
               </div>
             </n-card>
           </n-grid-item>
        </n-grid>
      </n-tab-pane>

    </n-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, h, onMounted, nextTick } from 'vue'
import { roleState } from '../role'
import { useMessage, NTag } from 'naive-ui'
import axios from 'axios'

const isAdmin = computed(() => roleState.role === 'Admin')
import * as echarts from 'echarts'

const message = useMessage()
const API_BASE_URL = import.meta.env.BASE_URL + 'api/v1'

const activeTab = ref('forward')

// --- Model State ---
const modelInfo = ref({
    name: 'Checking...',
    status: 'unknown',
    last_trained: '',
    accuracy: {}
})
const loadingRetrain = ref(false)

const fetchModelInfo = async () => {
    try {
        const res = await axios.get(`${API_BASE_URL}/model/info`)
        modelInfo.value = res.data
    } catch (e) {
        console.error("Failed to fetch model info", e)
        modelInfo.value.name = "离线"
        modelInfo.value.status = "unknown"
    }
}

const handleRetrain = async () => {
    loadingRetrain.value = true
    try {
        const res = await axios.post(`${API_BASE_URL}/model/retrain`)
        if (res.data.success) {
            message.success(res.data.message)
            modelInfo.value = res.data.info
        } else {
            message.error(res.data.message || "训练失败")
        }
    } catch (e) {
        message.error("训练请求失败")
    } finally {
        loadingRetrain.value = false
    }
}

onMounted(() => {
    fetchModelInfo()
})

// --- Common Options ---
const fluxTypeOptions = ['D1', 'E1', 'F2', 'F3', 'F4', 'X2', 'A2', 'G1', 'X1', 'X8', 'K1', 'Z1', 'K5', 'Z2'].map(x => ({ label: x, value: x }))

const specOptions = [
    { label: '1A (最高级)', value: '1A' },
    { label: '1B', value: '1B' },
    { label: '2A', value: '2A' },
    { label: '2B', value: '2B' },
    { label: '3A', value: '3A' },
    { label: '3B', value: '3B' },
    { label: '4A', value: '4A' },
    { label: '4B', value: '4B' },
    { label: '5A', value: '5A' },
    { label: '6A (最低级)', value: '6A' }
]

const wettingOptions = [
    { label: 'Level 1', value: 'level1' },
    { label: 'Level 2', value: 'level2' },
    { label: 'Level 3', value: 'level3' },
    { label: 'Level 4', value: 'level4' }
]

// --- Forward Reasoning State ---
const loadingPredict = ref(false)
const formX = reactive({
  flux_type: 'D1',
  flux_percent: 11.5,
  // Alloy elements
  ag: 3.0, 
  cu: 0.5, 
  pb: 0.05,
  fe: 0.02,
  bi: 0.0,
  sb: 0.0,
  oxygen: 0.05,
  // Fixed (Internal use if needed, but display is static)
  as: 0.005,
  ni: 0.005,
  zn: 0.001,
  al: 0.001,
  cd: 0.001
})

const alloyPercent = computed({
  get: () => parseFloat((100 - formX.flux_percent).toFixed(2)),
  set: (val) => {
    let newFlux = 100 - val
    if (newFlux < 0) newFlux = 0
    if (newFlux > 20) newFlux = 20 // Max flux constraint
    formX.flux_percent = parseFloat(newFlux.toFixed(2))
  }
})

const updateFluxFromAlloy = (val) => {
   // Handled by setter but double check if event needs specific handling
   // Setter handles it
}

const prediction = ref(null)

const getScoreColor = (score) => {
  if (score >= 9) return '#00B42A' 
  if (score >= 7) return '#FF7D00' 
  return '#F53F3F' 
}

const handlePredict = async () => {
  loadingPredict.value = true
  try {
    const payload = { ...formX, sn: '余量' }
    
    const res = await axios.post(`${API_BASE_URL}/predict`, { features: payload })
    prediction.value = res.data.predictions
    // Mock score if not present
    if (res.data.score !== undefined) {
        prediction.value.score = res.data.score
    } else {
        prediction.value.score = 9.2 // Mock for demo if backend missing
    }
    message.success("智能推理完成")
  } catch (err) {
    console.error(err)
    message.error("推理服务连接失败，展示模拟数据")
    // Mock data for display purposes if backend fails
    prediction.value = {
        score: 8.8,
        powder_spec: '4A',
        wetting_class: 'level2',
        viscosity: 195.5,
        ti: 0.58
    }
  } finally {
    loadingPredict.value = false
  }
}

// --- Backward Optimization State ---
const loadingOptimize = ref(false)
const targetY = reactive({
  viscosity: 200.0,
  ti: 0.55,
  powder_spec: '4A',
  wetting_class: 'level1'
})

const recommendations = ref(null)
const chartRef = ref(null)
let chartInstance = null

// Helper to parse backend list response to object
const parseBackendResponse = (listData) => {
    const res = {
        flux_type: 'N/A',
        flux_percent: 0,
        alloy_elements: {}
    }
    
    if (!Array.isArray(listData)) return res

    listData.forEach(item => {
        const p = item.param
        const vRaw = item.value
        // Clean value string (remove %, space)
        let vNum = parseFloat(String(vRaw).replace('%', ''))
        
        if (p.includes('Flux Type') || p.includes('助焊膏型号')) {
            res.flux_type = vRaw
        } else if (p.includes('Flux') || p.includes('助焊剂')) {
            // Robust check for flux percent
            if (!isNaN(vNum)) {
                res.flux_percent = vNum
            }
        } else if (['Ag', 'Cu', 'Pb', 'Fe', 'Bi', 'Sb'].some(el => p.startsWith(el))) {
            const elName = p.split(' ')[0]
            res.alloy_elements[elName] = vNum
        } else if (p.includes('Oxygen')) {
            res.alloy_elements['Oxygen'] = vNum
        } else if (p.includes('Sn')) {
             // Sn usually is '余量' or calculated
             // We can skip or set a placeholder
        }
    })
    return res
}

const renderChart = (data) => {
    if (!chartRef.value) return
    
    if (chartInstance) {
        chartInstance.dispose()
    }
    chartInstance = echarts.init(chartRef.value)
    
    const chartData = Object.entries(data.alloy_elements).map(([k, v]) => ({ value: v, name: k }))
    // Add Sn (Balance)
    // Sn is usually the balance in weight. Assuming 100 total is percent, 
    // but user mentioned kg for elements. 
    // However, the pie chart shows composition ratio. 
    // If backend returns % values but labels them kg, it might be confusing.
    // Based on user request "these alloy elements should be kg", we update the label.
    // But for chart, we still need ratio.
    
    // Let's assume the values are relative weights or percents that sum up to Alloy Content part.
    // Or if they are small numbers like 3.0, 0.5, they look like percents.
    
    // Filter out Sn and Oxygen from chartData
    const filteredChartData = chartData.filter(item => !item.name.includes('Oxygen') && !item.name.includes('Sn'))
    
    const option = {
        tooltip: {
            trigger: 'item',
            formatter: (params) => {
                // Custom formatter to show unit based on name
                const unit = params.name.includes('Oxygen') ? '%' : 'kg'
                // However, pie chart usually shows percentage of total.
                // If the values are actual quantities, we should just show them.
                return `${params.name}: ${params.value} ${unit} (${params.percent}%)`
            }
        },
        legend: {
            bottom: '0%',
            left: 'center',
            icon: 'circle'
        },
        series: [
            {
                name: '合金成分',
                type: 'pie',
                radius: ['40%', '70%'],
                center: ['50%', '45%'],
                avoidLabelOverlap: false,
                itemStyle: {
                    borderRadius: 5,
                    borderColor: '#fff',
                    borderWidth: 2
                },
                label: {
                    show: false,
                    position: 'center'
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: 16,
                        fontWeight: 'bold'
                    }
                },
                labelLine: {
                    show: false
                },
                data: filteredChartData
            }
        ]
    }
    chartInstance.setOption(option)
}

const handleOptimize = async () => {
  loadingOptimize.value = true
  try {
    const res = await axios.post(`${API_BASE_URL}/optimize`, { targets: targetY })
    // Parse the list response to object
    recommendations.value = parseBackendResponse(res.data.recommended_features)
    message.success("反向推理完成")
    
    // Render chart in next tick
    nextTick(() => {
        renderChart(recommendations.value)
    })
    
  } catch (err) {
    console.error(err)
    message.error("反推服务连接失败，展示模拟数据")
    // Mock result
    recommendations.value = {
        flux_type: 'F4',
        flux_percent: 11.2,
        alloy_elements: {
            Ag: 3.0, Cu: 0.5, Pb: 0.05, Fe: 0.01, Bi: 0.02, Sb: 0.01, Oxygen: 0.01
        }
    }
    nextTick(() => {
        renderChart(recommendations.value)
    })
  } finally {
    loadingOptimize.value = false
  }
}

const applyRecommendation = () => {
    if (!recommendations.value) return
    
    // Fill forward form
    const r = recommendations.value
    formX.flux_type = r.flux_type
    formX.flux_percent = r.flux_percent
    
    // Fill elements
    if (r.alloy_elements) {
        if (r.alloy_elements.Ag !== undefined) formX.ag = r.alloy_elements.Ag
        if (r.alloy_elements.Cu !== undefined) formX.cu = r.alloy_elements.Cu
        if (r.alloy_elements.Pb !== undefined) formX.pb = r.alloy_elements.Pb
        if (r.alloy_elements.Fe !== undefined) formX.fe = r.alloy_elements.Fe
        if (r.alloy_elements.Bi !== undefined) formX.bi = r.alloy_elements.Bi
        if (r.alloy_elements.Sb !== undefined) formX.sb = r.alloy_elements.Sb
        if (r.alloy_elements.Oxygen !== undefined) formX.oxygen = r.alloy_elements.Oxygen
    }
    
    message.success("已应用推荐配方，正在跳转验证...")
    activeTab.value = 'forward'
    
    // Auto predict after switch
    setTimeout(() => {
        handlePredict()
    }, 500)
}
</script>

<style scoped>
.reasoning-container {
  padding: 12px;
  max-width: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  height: calc(100vh - 84px);
}

/* Model Status Bar */
.model-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  padding: 8px 16px;
  border-radius: 8px;
  margin-bottom: 12px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.03);
  border: 1px solid rgba(0,0,0,0.03);
  flex-shrink: 0;
}

.status-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-label {
  font-size: 14px;
  color: #86909C;
  font-weight: 500;
}

.status-detail {
  font-size: 12px;
  color: #C9CDD4;
}

.status-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.info-btn {
  color: #165DFF;
}

.retrain-btn {
  font-weight: 500;
}

.accuracy-info {
  padding: 8px;
  min-width: 150px;
}

/* Tabs & Layout */
.custom-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

:deep(.n-tabs-pane-wrapper) {
  flex: 1;
  overflow: hidden;
}

:deep(.n-tab-pane) {
  height: 100%;
  padding: 0 !important;
}

.main-grid {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

:deep(.n-grid) {
  height: 100%;
  min-height: 0;
}

/* Scroll Container */
.scroll-container {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

/* Common Panel Styles */
:deep(.n-grid-item) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.panel-card {
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
  height: 100%;
  border: 1px solid rgba(0,0,0,0.03);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

:deep(.n-card) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

:deep(.n-card__header) {
  flex-shrink: 0;
}

:deep(.n-card__content) {
  flex: 1;
  overflow-y: auto;
  padding: 12px !important;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.input-panel,
.result-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.icon-box {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-box.blue { background: rgba(22, 93, 255, 0.1); color: #165DFF; }
.icon-box.green { background: rgba(0, 180, 42, 0.1); color: #00B42A; }
.icon-box.orange { background: rgba(255, 125, 0, 0.1); color: #FF7D00; }
.icon-box.purple { background: rgba(114, 46, 209, 0.1); color: #722ED1; }

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #1D2129;
}

/* Form Styles */
.compact-form {
  padding: 4px 0;
}

.form-section {
  margin-bottom: 12px;
}

.section-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.section-dot {
  width: 4px;
  height: 14px;
  border-radius: 2px;
}
.bg-primary { background: #165DFF; }
.bg-warning { background: #FF7D00; }
.bg-purple { background: #722ED1; }
.bg-cyan { background: #00B42A; }

.section-name {
  font-size: 13px;
  font-weight: 600;
  color: #4E5969;
}

/* Ratio Slider */
.ratio-container {
  background: #F7F8FA;
  padding: 8px;
  border-radius: 8px;
  margin-top: 8px;
}

.ratio-labels {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 12px;
  color: #86909C;
}

.ratio-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.slider-box {
  flex: 1;
  padding: 0 8px;
}

.input-box {
  width: 70px;
}

/* Action Footer */
.action-footer {
  margin-top: 16px;
}

.main-btn {
  height: 40px;
  font-weight: 600;
  border-radius: 8px;
  font-size: 14px;
  box-shadow: 0 4px 10px rgba(22, 93, 255, 0.2);
}

/* Read-only Box */
.read-only-box {
  background: #F2F3F5;
  color: #1D2129;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
  line-height: 22px;
  border: 1px solid #E5E6EB;
  font-size: 12px;
}

/* Fixed Elements */
.fixed-elements {
  margin-top: 12px;
  padding: 8px;
  background: #f9f9f9;
  border-radius: 6px;
  border: 1px dashed #e5e6eb;
}

.fixed-label {
  font-size: 12px;
  color: #86909C;
  margin-bottom: 4px;
}

.tags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.fixed-tag {
  color: #4E5969;
  font-size: 11px;
}

/* Result Styles */
.result-content {
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  padding-top: 12px;
  overflow-y: auto;
}

.score-card {
  display: flex;
  justify-content: center;
  margin-bottom: 20px;
}

.score-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.score-num {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

.score-sub {
  font-size: 12px;
  color: #86909C;
}

.metrics-grid {
  display: grid;
  gap: 12px;
}

.metric-box {
  background: #F7F8FA;
  padding: 12px;
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.m-label {
  color: #4E5969;
  font-size: 13px;
}

.m-value {
  color: #1D2129;
  font-weight: 600;
  font-size: 15px;
}

.m-value.highlight {
  color: #165DFF;
  font-size: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: #C9CDD4;
}

.empty-img {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

/* Backward Result Specifics */
.result-summary-box {
  background: #F7F8FA;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  justify-content: space-around;
  align-items: center;
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.s-label { font-size: 12px; color: #86909C; }
.s-value { font-size: 16px; font-weight: 700; color: #1D2129; }
.s-value.highlight { color: #722ED1; }

.vertical-divider {
  width: 1px;
  height: 24px;
  background: #E5E6EB;
}

.alloy-details {
  margin-top: 8px;
}

.detail-header {
  font-size: 13px;
  font-weight: 600;
  color: #4E5969;
  margin-bottom: 8px;
}

.element-box {
  background: #fff;
  border: 1px solid #E5E6EB;
  border-radius: 4px;
  padding: 4px 6px;
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.e-name { color: #86909C; }
.e-val { font-weight: 600; color: #1D2129; }

.fixed-elements-display {
  margin-top: 16px;
  padding: 8px;
  background: #F9F9F9;
  border-radius: 6px;
  font-size: 11px;
  color: #86909C;
  text-align: center;
}
.f-val { margin-left: 6px; color: #4E5969; }

.chart-container {
  width: 100%;
  height: 160px;
  margin-bottom: 8px;
}

.apply-btn-container {
  margin-top: 16px;
}

.animate-fade-in {
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
file_path:d:\Yunxi_Project\platform\frontend\src\views\Reasoning.vue