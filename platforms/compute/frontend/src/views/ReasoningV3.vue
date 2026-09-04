<template>
  <div class="reasoning-container">
    <div class="model-status-bar">
      <div class="status-left">
        <span class="status-label">{{ text.currentModel }}</span>
        <n-tag :type="isModelReady ? 'success' : 'warning'" size="small" round>
          {{ modelInfo.name || text.uninitialized }}
        </n-tag>
        <span v-if="modelInfo.last_trained" class="status-detail">
          {{ text.lastTrained }}: {{ modelInfo.last_trained }}
        </span>
        <span v-if="!isModelReady || modelInfo.status === 'failed'" class="status-warning">
          {{ text.needTrain }}
        </span>
      </div>
      <div class="status-right">
        <n-button text size="small" type="info" @click="showAccuracyModal = true">
          {{ text.accuracyDetail }}
        </n-button>
        <n-button v-if="isAdmin" size="small" type="warning" ghost :loading="loadingRetrain" @click="handleRetrain">
          {{ text.retrain }}
        </n-button>
      </div>
    </div>

    <n-modal v-model:show="showAccuracyModal">
      <n-card class="accuracy-modal" :bordered="false">
        <template #header>
          <div class="panel-title">{{ text.modelAccuracy }}</div>
        </template>
        <div class="accuracy-kpi-grid">
          <div class="accuracy-kpi">
            <span>训练样本</span>
            <strong>{{ modelInfo.training_rows || 0 }}</strong>
          </div>
          <div class="accuracy-kpi">
            <span>总特征数</span>
            <strong>{{ modelInfo.feature_count || 0 }}</strong>
          </div>
          <div class="accuracy-kpi">
            <span>粒度特征</span>
            <strong>{{ modelInfo.particle_feature_count || 0 }}</strong>
          </div>
        </div>
        <div v-if="hasAccuracyData" ref="accuracyChartRef" class="chart-lg"></div>
        <div v-if="hasAccuracyData" class="accuracy-metric-grid">
          <div v-for="item in accuracyMetricCards" :key="item.key" class="accuracy-metric-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.hint }}</small>
          </div>
        </div>
        <div v-else class="empty-text">{{ text.noAccuracy }}</div>
        <div class="modal-hint">{{ text.accuracyHint }}</div>
      </n-card>
    </n-modal>

    <n-modal v-model:show="showImpactModal" :mask-closable="false" transform-origin="center">
      <n-card class="impact-modal" :bordered="false" :style="impactModalStyle">
        <template #header>
          <div class="modal-title-row draggable-title" @pointerdown="startImpactDrag">
            <div>
              <div class="panel-title">{{ text.impactAnalysis }}</div>
              <div class="impact-hint">{{ text.impactHint }}</div>
            </div>
            <div class="modal-header-actions">
              <n-button class="impact-close-btn" quaternary circle size="small" @pointerdown.stop @click="showImpactModal = false">X</n-button>
            </div>
          </div>
        </template>

        <div class="impact-toolbar">
          <n-button type="primary" size="small" :loading="loadingImpact" @click="runImpactAnalysis">
            {{ text.analyzeAll }}
          </n-button>
          <div v-if="loadingImpact" class="impact-loading-box">
            <n-progress
              type="line"
              :percentage="loadingProgress"
              :indicator-placement="'inside'"
              processing
              class="impact-progress"
            />
            <span class="loading-text">分析计算中，请稍候...</span>
          </div>
        </div>

        <div v-if="bestTuningResult" class="best-tuning-card">
          <div class="best-tuning-head">
            <div>
              <div class="recommend-title">{{ text.bestTuningResult }}</div>
              <div class="recommend-copy">{{ text.bestTuningCopy }}</div>
            </div>
            <div class="score-pill">
              <span>{{ text.compositeScore }}</span>
              <strong>{{ bestTuningResult.score }}</strong>
            </div>
          </div>
          <div class="best-tuning-grid">
            <div>
              <span>{{ text.xCombination }}</span>
              <strong>{{ bestTuningResult.xText }}</strong>
              <div class="mini-dist" :title="text.particleDetail">
                <span v-for="seg in bestTuningResult.distribution" :key="seg.label" :style="{ width: seg.width, background: seg.color }">{{ seg.value }}</span>
              </div>
            </div>
            <div v-for="item in bestTuningResult.outputs" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <small>{{ item.extra }}</small>
            </div>
          </div>
          <div class="impact-note">{{ bestTuningResult.note }}</div>
          <div class="export-row" style="margin-top: 8px;">
            <n-button type="primary" secondary size="small" :loading="reporting" @click="exportOptimizationReport">
              <template #icon>📄</template>
              导出优化报告
            </n-button>
          </div>
        </div>

        <div v-if="impactReady" class="impact-table-stack">
          <div class="impact-table-section">
            <div class="table-title">{{ text.singleParamOptimization }}</div>
            <div v-for="group in groupedSingleParamCards" :key="group.key" class="variable-impact-row">
              <div class="variable-row-head">
                <span class="var-dot"></span>
                <span class="var-name">{{ group.name }}</span>
              </div>
              <div class="variable-row-grid">
                <div v-for="card in group.cards" :key="card.key" class="single-param-card">
                  <div class="single-card-head">
                    <span class="y-name">{{ card.yName }}</span>
                  </div>
                  <div :ref="(el) => setSingleImpactChartRef(card.key, el)" class="single-impact-chart"></div>
                  <div class="single-card-mini-meta">
                    <div class="meta-item">
                      <span class="m-label">基准:</span>
                      <span class="m-val">{{ card.baseline }}</span>
                    </div>
                    <div class="meta-item">
                      <span class="m-label">范围:</span>
                      <span class="m-val">{{ card.rangeText }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="impact-table-section">
            <div class="table-title">{{ text.multiParamOptimization }}</div>
            <div class="score-formula">{{ text.scoreFormulaText }}</div>
            <div class="combo-top-grid">
              <div v-for="row in multiXMultiYRows" :key="row.key" class="combo-top-card">
                <div class="combo-rank">Top {{ row.rank }}</div>
                <div class="combo-main">{{ row.combo }}</div>
                <div class="mini-dist combo-dist">
                  <span v-for="seg in row.distribution" :key="seg.label" :style="{ width: seg.width, background: seg.color }">{{ seg.value }}</span>
                </div>
                <div class="particle-detail-grid">
                  <span v-for="seg in row.distribution" :key="seg.label">
                    <i :style="{ background: seg.color }"></i>{{ seg.label }} {{ seg.value }}
                  </span>
                </div>
                <div class="combo-metrics">
                  <span>{{ text.viscosity }}: {{ row.viscosity }}</span>
                  <span>Ti: {{ row.ti }}</span>
                  <span>{{ text.powderSpec }}: {{ row.powder }}</span>
                  <span>{{ text.wettingClass }}: {{ row.wetting }}</span>
                  <span>坍塌类别: {{ row.collapse }}</span>
                  <span>锡珠等级: {{ row.solderball }}</span>
                </div>
                <div class="combo-score">{{ text.compositeScore }} {{ row.score }}</div>
              </div>
            </div>
            <div class="surface-chart-grid">
              <div v-for="chart in multiSurfaceCards" :key="chart.key" class="surface-chart-card">
                <div class="surface-title">{{ chart.title }}</div>
                <div :ref="(el) => setMultiSurfaceChartRef(chart.key, el)" class="surface-chart"></div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="analysis-empty">{{ text.analysisEmpty }}</div>

        <div class="impact-footer">
          <n-button size="small" @click="showImpactModal = false">{{ text.closeModal }}</n-button>
        </div>
      </n-card>
    </n-modal>

    <n-grid :x-gap="12" :y-gap="12" cols="1 900:2" class="main-grid">
      <n-grid-item>
        <n-card size="small" :bordered="false" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div class="title-group">
                <div class="icon-box blue">
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24">
                    <path fill="currentColor" d="M3 17v2h6v-2H3M3 5v2h10V5H3m10 16v-2h8v-2h-8v-2h-2v6h2M7 9v2H3v2h4v2h2V9H7m14 4v-2H11v2h10m-6-4h6V5h-6v4Z" />
                  </svg>
                </div>
                <span class="panel-title">{{ text.formTitle }}</span>
              </div>
              <n-tag type="primary" size="small" round ghost>{{ text.inputParams }}</n-tag>
            </div>
          </template>

          <div class="scroll-container">
          <n-form size="small" label-placement="top" class="compact-form">
            <n-collapse v-model:expanded-names="expandedInputSections" :accordion="false">
              <n-collapse-item name="flux">
                <template #header>
                  <div class="collapse-header">
                    <span class="section-dot bg-primary"></span>
                    <span class="section-name">{{ text.fluxSystem }}</span>
                  </div>
                </template>
                <div class="section-body">
                  <div class="flux-row">
                    <n-form-item :label="text.fluxType" class="no-mb">
                      <n-select
                        v-model:value="formX.flux_type"
                        :options="fluxTypeOptions"
                        :placeholder="text.selectType"
                        filterable
                      />
                    </n-form-item>
                    <n-form-item :label="text.oxygen" class="no-mb">
                      <n-input-number v-model:value="formX.oxygen" :step="0.001" :min="0" :show-button="false" size="small">
                        <template #suffix>%</template>
                      </n-input-number>
                    </n-form-item>
                  </div>
                  <div class="compact-row compact-row-tight">
                    <div class="ratio-compact-card">
                      <div class="ratio-inline-head">
                        <div>
                          <span>{{ text.fluxAlloyRatio }}</span>
                          <strong>{{ Number(formX.flux_percent || 0).toFixed(1) }} / {{ Number(alloyContent || 0).toFixed(1) }}</strong>
                        </div>
                        <n-input-number v-model:value="formX.flux_percent" :step="0.1" :min="0" :max="40" :show-button="false" size="small" class="ratio-floating-input">
                          <template #suffix>%</template>
                        </n-input-number>
                      </div>
                      <n-slider v-model:value="formX.flux_percent" :min="0" :max="40" :step="0.1" :tooltip="false" />
                    </div>
                  </div>
                </div>
              </n-collapse-item>

              <n-collapse-item name="alloy">
                <template #header>
                  <div class="collapse-header">
                    <span class="section-dot bg-warning"></span>
                    <span class="section-name">{{ text.alloyComposition }}</span>
                  </div>
                </template>
                <div class="section-body">
                  <div class="alloy-top-row">
                    <n-form-item :label="text.alloyGrade" class="no-mb alloy-grade-item">
                      <n-select
                        v-model:value="formX.alloy_grade"
                        :options="alloyOptions"
                        :placeholder="text.selectAlloy"
                        clearable
                        filterable
                        @update:value="handleAlloyPreset"
                      />
                    </n-form-item>
                    <div class="toggle-box alloy-toggle-box">
                      <n-switch v-model:value="showAlloyFineTune" size="small" :disabled="!formX.alloy_grade" />
                      <span class="toggle-text">{{ text.showFineTune }}</span>
                    </div>
                  </div>

                  <div v-if="!formX.alloy_grade" class="empty-hint">{{ text.alloyHint }}</div>

                  <div v-else>
                    <div class="fine-hint">{{ text.fineTuneHint }}</div>
                    <n-collapse-transition :show="showAlloyFineTune">
                      <div class="alloy-table">
                        <div v-for="item in alloyElementFields" :key="item.key" class="alloy-cell">
                          <div class="alloy-label">{{ item.label }}</div>
                          <n-input-number v-model:value="formX[item.key]" :step="item.step" :min="0" :show-button="false" size="small">
                            <template #suffix>%</template>
                          </n-input-number>
                        </div>
                      </div>
                    </n-collapse-transition>

                    <div class="fixed-elements compact-fixed">
                      <div class="fixed-label">{{ text.fixedElements }}</div>
                      <div class="tags-row">
                        <n-tag size="small" :bordered="false" class="fixed-tag">As: 0.005</n-tag>
                        <n-tag size="small" :bordered="false" class="fixed-tag">Ni: 0.005</n-tag>
                        <n-tag size="small" :bordered="false" class="fixed-tag">Zn: 0.001</n-tag>
                        <n-tag size="small" :bordered="false" class="fixed-tag">Al: 0.001</n-tag>
                        <n-tag size="small" :bordered="false" class="fixed-tag">Cd: 0.001</n-tag>
                      </div>
                    </div>
                  </div>
                </div>
              </n-collapse-item>

              <n-collapse-item name="particle">
                <template #header>
                  <div class="collapse-header">
                    <span class="section-dot bg-purple"></span>
                    <span class="section-name">{{ text.particleDistribution }}</span>
                  </div>
                </template>
                <div class="section-body">
                  <div class="particle-top-row compact-row">
                    <n-form-item label="粒度模板" class="no-mb particle-template-item">
                      <n-select
                        v-model:value="selectedParticleTemplateId"
                        :options="particleTemplateOptions"
                        placeholder="选择粒度模板"
                        clearable
                        filterable
                        @update:value="applyParticleTemplateById"
                      />
                    </n-form-item>
                    <div class="particle-boundary-panel">
                      <div class="particle-boundary-grid">
                        <div v-for="(seg, index) in editableParticleSegments" :key="seg.key" class="boundary-card">
                          <div class="boundary-head">
                            <strong>{{ seg.label }}</strong>
                          </div>
                          <div class="boundary-row">
                            <n-input-number :value="seg.start" :disabled="seg.kind === 'lt'" :show-button="false" size="small" @update:value="(val) => updateParticleBoundary(index, 'start', val)">
                              <template #suffix>µm</template>
                            </n-input-number>
                            <span class="boundary-sep">~</span>
                            <n-input-number :value="seg.end" :disabled="seg.kind === 'gt'" :show-button="false" size="small" @update:value="(val) => updateParticleBoundary(index, 'end', val)">
                              <template #suffix>µm</template>
                            </n-input-number>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="particle-distribution-editor">
                    <div class="particle-editor-top">
                      <span>{{ text.distributionViz }}</span>
                      <strong>{{ text.total100 }}</strong>
                    </div>
                    <div ref="particleTrackRef" class="particle-track" @pointerdown="startParticleTrackDrag">
                      <div v-for="seg in particleSegments" :key="seg.key" class="particle-segment" :style="{ width: seg.width, background: seg.color }">
                        <span>{{ seg.label }}</span>
                        <strong>{{ seg.value }}</strong>
                      </div>
                      <button
                        v-for="(cut, index) in particleCuts"
                        :key="index"
                        class="particle-handle"
                        :style="{ left: `${cut}%` }"
                        type="button"
                        @pointerdown.stop.prevent="startParticleDrag(index, $event)"
                      ></button>
                    </div>
                    <div class="particle-manual-grid">
                      <div v-for="(seg, index) in editableParticleSegments" :key="seg.key" class="particle-manual-cell">
                        <span>{{ seg.label }}</span>
                        <n-input-number
                          :value="Number(seg.value.replace('%', ''))"
                          :min="0"
                          :max="100"
                          :step="0.1"
                          :show-button="false"
                          size="small"
                          @update:value="(val) => updateParticleManual(index, val)"
                        >
                          <template #suffix>%</template>
                        </n-input-number>
                      </div>
                    </div>
                    <div class="fine-hint">{{ text.dragParticleHint }}</div>
                  </div>
                </div>
              </n-collapse-item>
            </n-collapse>

            <div class="action-footer sticky-footer">
              <n-space :size="12" justify="center">
                <n-button type="primary" size="large" class="main-btn" :loading="loadingPredict" :disabled="!canPredict" @click="handlePredict" style="min-width: 160px">
                  {{ text.startReasoning }}
                </n-button>
                <n-button type="primary" size="large" class="main-btn" secondary strong :disabled="!canPredict" @click="openImpactModal" style="min-width: 160px">
                  {{ text.impactAnalysis }}
                </n-button>
              </n-space>
              <div v-if="!canPredict" class="gate-hint">{{ predictGateHint }}</div>
            </div>
          </n-form>
          </div>
        </n-card>
      </n-grid-item>

      <n-grid-item>
        <n-card size="small" :bordered="false" class="panel-card">
          <template #header>
            <div class="panel-header">
              <div class="title-group">
                <div class="icon-box green">
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24">
                    <path fill="currentColor" d="M21 3H3c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-5h2v5zm4 0h-2v-3h2v3zm4 0h-2v-5h2v5z" />
                  </svg>
                </div>
                <span class="panel-title">{{ text.predictionResult }}</span>
              </div>
              <div class="result-actions">
              </div>
            </div>
          </template>

          <div class="scroll-container">
          <div v-if="prediction" class="result-content animate-fade-in">
            <div class="result-hero">
              <div class="hero-left">
                <n-progress
                  type="line"
                  :percentage="Math.max(0, Math.min(100, prediction.score * 10))"
                  :color="getScoreColor(prediction.score)"
                  :height="10"
                  :border-radius="8"
                  :show-indicator="false"
                />
                <div class="hero-score-text">
                  <span class="hero-score-num">{{ prediction.score }}</span>
                  <span class="hero-score-sub">{{ text.confidence }}</span>
                </div>
              </div>
            </div>

            <n-grid :x-gap="10" :y-gap="10" cols="2" class="tight-grid metric-grid">
              <n-grid-item>
                <div class="metric-mini">
                  <div class="m-label">{{ text.viscosity }}</div>
                  <div class="m-value">{{ prediction.viscosity }}</div>
                </div>
              </n-grid-item>
              <n-grid-item>
                <div class="metric-mini">
                  <div class="m-label">{{ text.tiIndex }}</div>
                  <div class="m-value">{{ prediction.ti }}</div>
                </div>
              </n-grid-item>
            </n-grid>

            <n-grid :x-gap="10" :y-gap="10" cols="2" class="tight-grid metric-grid">
              <n-grid-item>
                <div class="metric-mini">
                  <div class="m-label">{{ text.powderSpec }}</div>
                  <div class="m-value">{{ prediction.powder_spec }}</div>
                </div>
              </n-grid-item>
              <n-grid-item>
                <div class="metric-mini">
                  <div class="m-label">{{ text.wettingClass }}</div>
                  <div class="m-value">{{ prediction.wetting_level }}</div>
                </div>
              </n-grid-item>
            </n-grid>

            <n-grid :x-gap="10" :y-gap="10" cols="2" class="tight-grid metric-grid">
              <n-grid-item>
                <div class="metric-mini">
                  <div class="m-label">坍塌类别</div>
                  <div class="m-value">{{ prediction.collapse_category }}</div>
                </div>
              </n-grid-item>
              <n-grid-item>
                <div class="metric-mini">
                  <div class="m-label">锡珠等级</div>
                  <div class="m-value">{{ prediction.solderball_level }}</div>
                </div>
              </n-grid-item>
            </n-grid>

            <div class="export-row">
              <n-button type="primary" secondary size="small" :loading="reporting" @click="exportPredictionReport">
                <template #icon>📄</template>
                导出预测报告
              </n-button>
            </div>

            <n-collapse v-model:expanded-names="expandedResultSections" class="result-collapse">
              <n-collapse-item name="viz">
                <template #header>
                  <div class="collapse-header">
                    <span class="section-dot bg-cyan"></span>
                    <span class="section-name">{{ text.resultViz }}</span>
                  </div>
                </template>
                <div class="section-body">
                  <div class="chart-card">
                    <div class="detail-header">{{ text.performanceMetrics }}</div>
                    <n-grid :x-gap="10" :y-gap="10" cols="2" class="tight-grid">
                      <n-grid-item>
                        <div class="chart-tile">
                          <div class="tile-title">{{ text.viscosity }}</div>
                          <div ref="visGaugeRef" class="chart-gauge"></div>
                        </div>
                      </n-grid-item>
                      <n-grid-item>
                        <div class="chart-tile">
                          <div class="tile-title">{{ text.tiIndex }}</div>
                          <div ref="tiGaugeRef" class="chart-gauge"></div>
                        </div>
                      </n-grid-item>
                    </n-grid>
                  </div>
                  <div class="chart-card chart-card-gap">
                    <div class="detail-header">{{ text.categoryTop3 }}</div>
                    <n-grid :x-gap="10" :y-gap="10" cols="2" class="tight-grid">
                      <n-grid-item>
                        <div class="chart-tile">
                          <div class="tile-title">{{ text.powderSpec }}</div>
                          <div ref="powderDonutRef" class="chart-donut"></div>
                        </div>
                      </n-grid-item>
                      <n-grid-item>
                        <div class="chart-tile">
                          <div class="tile-title">{{ text.wettingClass }}</div>
                          <div ref="wettingDonutRef" class="chart-donut"></div>
                        </div>
                      </n-grid-item>
                      <n-grid-item>
                        <div class="chart-tile">
                          <div class="tile-title">坍塌类别</div>
                          <div ref="collapseDonutRef" class="chart-donut"></div>
                        </div>
                      </n-grid-item>
                      <n-grid-item>
                        <div class="chart-tile">
                          <div class="tile-title">锡珠等级</div>
                          <div ref="solderballDonutRef" class="chart-donut"></div>
                        </div>
                      </n-grid-item>
                    </n-grid>
                  </div>
                </div>
              </n-collapse-item>
            </n-collapse>
          </div>

          <div v-else class="empty-state">
            <div class="empty-img">AI</div>
            <p>{{ text.emptyResult }}</p>
          </div>
          </div>
        </n-card>
      </n-grid-item>
    </n-grid>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { roleState } from '../role';
import axios from "axios";

const isAdmin = computed(() => roleState.role === 'Admin');
import * as echarts from "echarts";
import "echarts-gl";
import { useMessage } from "naive-ui";

const zh = (codes) => String.fromCharCode(...codes);
const text = {
  currentModel: zh([24403, 21069, 27169, 22411]) + ":",
  uninitialized: zh([26410, 21021, 22987, 21270]),
  lastTrained: zh([19978, 27425, 35757, 32451]),
  needTrain: zh([38656, 35201, 35757, 32451]),
  accuracyDetail: zh([31934, 24230, 35814, 24773]),
  retrain: zh([24494, 35843, 27169, 22411]),
  modelAccuracy: zh([27169, 22411, 31934, 24230, 20449, 24687]),
  noAccuracy: zh([26242, 26080, 31934, 24230, 25968, 25454, 65292, 35831, 20808, 35757, 32451, 25110, 37325, 36733, 27169, 22411, 12290]),
  accuracyHint: zh([31934, 24230, 20026, 24403, 21069, 27169, 22411, 36820, 22238, 30340, 32479, 35745, 25351, 26631, 65292, 29992, 20110, 24555, 36895, 21028, 26029, 27169, 22411, 29366, 24577, 12290]),
  impactAnalysis: zh([37197, 26041, 20248, 21270]),
  impactHint: zh([22260, 32469, 24403, 21069, 37197, 26041, 25195, 25551, 27687, 21547, 37327, 19982, 31890, 24230, 21306, 38388, 65292, 26597, 30475, 21333, 21442, 25968, 19982, 21452, 21442, 25968, 32452, 21512, 23545, 32467, 26524, 30340, 24433, 21709, 12290]),
  selfTuning: zh([33258, 25105, 35843, 21442]),
  runAnalysis: zh([36816, 34892, 20998, 26512]),
  comprehensiveAnalysis: zh([32508, 21512, 24433, 21709, 20998, 26512]),
  analyzeAll: zh([19968, 38190, 32508, 21512, 20998, 26512]),
  bestTuningResult: zh([26368, 20248, 35843, 21442, 32467, 26524]),
  bestTuningCopy: zh([27169, 22411, 32508, 21512, 35780, 20998, 26368, 39640, 30340, 19968, 32452, 88, 21442, 25968, 32452, 21512, 65292, 89, 20540, 26469, 33258, 24403, 21069, 21518, 31471, 39044, 27979, 27169, 22411, 12290]),
  xCombination: zh([88, 32452, 21512]),
  yResult: zh([89, 32467, 26524]),
  compositeScore: zh([32508, 21512, 24471, 20998]),
  resultInterpretation: zh([32467, 26524, 35299, 35835]),
  singleXSingleYTitle: zh([21333, 19968, 88, 21464, 21270, 21040, 21333, 19968, 89, 21464, 21270]),
  singleXMultiYTitle: zh([21333, 19968, 88, 21464, 21270, 21040, 22810, 89, 21464, 21270]),
  multiXMultiYTitle: zh([22810, 88, 32452, 21512, 21464, 21270, 21040, 22810, 89, 21464, 21270]),
  xParam: zh([88, 21442, 25968]),
  yMetric: zh([89, 25351, 26631]),
  baselineResult: zh([22522, 20934, 32467, 26524]),
  minResult: zh([26368, 23567, 32467, 26524]),
  maxResult: zh([26368, 22823, 32467, 26524]),
  changeRange: zh([21464, 21270, 24133, 24230]),
  bestPosition: zh([26368, 20248, 20301, 32622]),
  interpretation: zh([35299, 35835]),
  oxygenScan: zh([27687, 21547, 37327, 25195, 25551]),
  particleScan: zh([31890, 24230, 20998, 24067, 25195, 25551]),
  categoryChange: zh([31867, 21035, 21464, 21270]),
  representativeCombo: zh([20195, 34920, 32452, 21512]),
  viscosityRange: zh([40655, 24230, 33539, 22260]),
  tiRange: zh([84, 105, 33539, 22260]),
  specChange: zh([35268, 26684, 21464, 21270]),
  wettingChange: zh([28070, 28287, 21464, 21270]),
  particleDetail: zh([31890, 24230, 35814, 24773]),
  currentRecipe: zh([24403, 21069, 37197, 26041]),
  bestTuningNote: zh([27169, 22411, 35748, 20026, 36825, 32452, 27687, 21547, 37327, 21644, 31890, 24230, 20998, 24067, 30340, 32508, 21512, 36755, 20986, 26368, 20248, 12290]),
  comboTableCopy: zh([25353, 32508, 21512, 24471, 20998, 25490, 24207, 65292, 23637, 31034, 21069, 20960, 32452, 20505, 36873, 32452, 21512, 12290]),
  singleXSingleYCopy: zh([22266, 23450, 20854, 20182, 21442, 25968, 65292, 20165, 25913, 21464, 19968, 20010, 88, 21442, 25968, 65292, 35266, 23519, 27599, 19968, 20010, 89, 25351, 26631, 22914, 20309, 21464, 21270, 12290]),
  singleXMultiYCopy: zh([22266, 23450, 20854, 20182, 21442, 25968, 65292, 20165, 25913, 21464, 19968, 20010, 88, 21442, 25968, 65292, 35266, 23519, 22235, 20010, 89, 25351, 26631, 19968, 36215, 22914, 20309, 21464, 21270, 12290]),
  multiXMultiYCopy: zh([21516, 26102, 25913, 21464, 27687, 21547, 37327, 21644, 31890, 24230, 20998, 24067, 65292, 35266, 23519, 22235, 20010, 89, 25351, 26631, 30340, 32452, 21512, 21464, 21270, 12290]),
  scoreGuide: zh([24471, 20998, 36234, 39640, 34920, 31034, 25968, 20540, 25351, 26631, 26356, 39640, 19988, 20998, 31867, 32622, 20449, 24230, 26356, 39640, 65292, 24182, 38750, 20154, 24037, 30446, 26631, 12290]),
  highestConfidence: zh([26368, 39640, 32622, 20449]),
  noChange: zh([26080, 21464, 21270]),
  changed: zh([21464, 21270]),
  valueRange: zh([21462, 20540, 33539, 22260]),
  predictedValue: zh([39044, 27979, 20540]),
  impactExplanation: zh([24433, 21709, 35828, 26126]),
  total100: zh([24635, 21644, 32, 49, 48, 48, 37]),
  dragParticleHint: zh([25302, 21160, 20998, 21106, 28857, 35843, 25972, 22235, 27573, 31890, 24230, 21344, 27604, 65292, 31995, 32479, 20250, 33258, 21160, 20445, 25345, 24635, 21644, 20026, 32, 49, 48, 48, 37, 12290]),
  singleParamOptimization: zh([21333, 37197, 26041, 21442, 25968, 20248, 21270]),
  multiParamOptimization: zh([22810, 37197, 26041, 21442, 25968, 20248, 21270]),
  relatedMetric: zh([30456, 20851, 25351, 26631]),
  lastInferenceResult: zh([19978, 27425, 25512, 29702, 32467, 26524]),
  tuningResultRange: zh([35843, 21442, 32467, 26524, 33539, 22260]),
  scoreFormulaText: zh([32508, 21512, 24471, 20998, 32, 61, 32, 50, 53, 37, 215, 40655, 24230, 24402, 19968, 21270, 32, 43, 32, 50, 53, 37, 215, 84, 105, 24402, 19968, 21270, 32, 43, 32, 50, 53, 37, 215, 38177, 31881, 35268, 26684, 32622, 20449, 24230, 32, 43, 32, 50, 53, 37, 215, 28070, 28287, 31561, 32423, 32622, 20449, 24230, 65307, 29992, 20110, 22312, 27809, 26377, 20154, 24037, 30446, 26631, 26435, 37325, 26102, 32473, 20986, 22343, 34913, 25490, 24207, 12290]),
  particleProjection: zh([31890, 24230, 20998, 24067, 25237, 24433]),
  oxygenShort: zh([27687, 21547, 37327]),
  particleShort: zh([31890, 24230, 20998, 24067]),
  singleTrend: zh([21333, 21442, 25968, 36235, 21183]),
  classConfidence: zh([20998, 31867, 32622, 20449, 24230]),
  predictedClass: zh([39044, 27979, 31867, 21035]),
  higherIsBetter: zh([36234, 39640, 36234, 22909]),
  manualAdjust: zh([25163, 21160, 20462, 27491]),
  particleBreakdown: zh([31890, 24230, 26126, 32454]),
  projectionValue: zh([25237, 24433, 20540]),
  bestPoint: zh([26368, 20248, 28857]),
  surfaceHeight: zh([26354, 38754, 39640, 24230]),
  ratio: zh([21344, 27604]),
  oxygenFactor: zh([27687, 21547, 37327, 21333, 22240, 32032]),
  particleFactor: zh([31890, 24230, 20998, 24067, 21333, 22240, 32032]),
  comboFactor: zh([27687, 21547, 37327, 32, 215, 32, 31890, 24230, 20998, 24067, 32452, 21512]),
  particleProfile: zh([31890, 24230, 20998, 24067, 26041, 26696]),
  bestX: zh([26368, 20248, 88, 32452, 21512]),
  yChange: zh([89, 20540, 21464, 21270]),
  factorGuide: zh([21333, 22240, 32032, 20998, 21035, 21482, 25913, 21464, 27687, 21547, 37327, 25110, 25972, 32452, 31890, 24230, 20998, 24067, 65307, 22810, 22240, 32032, 21516, 26102, 25913, 21464, 27687, 21547, 37327, 21644, 31890, 24230, 20998, 24067, 26041, 26696, 65292, 35266, 23519, 22235, 20010, 89, 20540, 21464, 21270, 24182, 36873, 21462, 26368, 20248, 32452, 21512, 12290]),
  allTargets: zh([20840, 37096, 30446, 26631]),
  viscosityBest: zh([40655, 24230, 25512, 33616]),
  tiBest: zh([84, 105, 25512, 33616]),
  specBest: zh([35268, 26684, 25512, 33616]),
  wettingBest: zh([28070, 28287, 25512, 33616]),
  targetName: zh([30446, 26631]),
  bestCombination: zh([26368, 20248, 32452, 21512]),
  resultEstimate: zh([32467, 26524, 20272, 35745]),
  sensitivity: zh([25935, 24863, 24230]),
  particleDimension: zh([31890, 24230, 32500, 24230]),
  fullAutoGuide: zh([31995, 32479, 20250, 22522, 20110, 30495, 23454, 25968, 25454, 33539, 22260, 65292, 19968, 27425, 24615, 25195, 25551, 27687, 21547, 37327, 19982, 21508, 31890, 24230, 21306, 38388, 65292, 24182, 20998, 21035, 32473, 20986, 40655, 24230, 12289, 84, 105, 12289, 38177, 31881, 35268, 26684, 12289, 28070, 28287, 31561, 32423, 30340, 25512, 33616, 32452, 21512, 12290]),
  selectedMap: zh([24403, 21069, 23637, 31034, 22320, 22270]),
  noManualTarget: zh([26080, 38656, 25163, 21160, 36873, 25321, 30446, 26631, 65292, 25512, 33616, 32467, 26524, 30001, 27169, 22411, 36880, 39033, 25195, 25551, 29983, 25104, 12290]),
  targetResult: zh([30446, 26631, 32467, 26524]),
  optMode: zh([20248, 21270, 26041, 24335]),
  targetValue: zh([30446, 26631, 20540]),
  targetClass: zh([30446, 26631, 31867, 21035]),
  dataSource: zh([25968, 25454, 26469, 28304]),
  dataRange: zh([25968, 25454, 33539, 22260]),
  noDataRange: zh([26410, 33719, 21462, 21040, 30495, 23454, 25968, 25454, 33539, 22260, 65292, 26080, 27861, 36827, 34892, 21487, 20449, 35843, 21442, 12290]),
  modelUnavailable: zh([27169, 22411, 25110, 21518, 31471, 19981, 21487, 29992, 65292, 26080, 27861, 23436, 25104, 30495, 23454, 39044, 27979, 12290]),
  dbData: zh([25968, 25454, 24211]),
  fileData: zh([35757, 32451, 25991, 20214]),
  noMock: zh([24403, 21069, 32467, 26524, 26469, 33258, 27169, 22411, 25509, 21475, 65292, 19981, 20877, 20351, 29992, 21069, 31471, 28436, 31034, 25968, 25454, 12290]),
  singleVariable: zh([21333, 21442, 25968]),
  maximize: zh([36234, 39640, 36234, 22909]),
  minimize: zh([36234, 20302, 36234, 22909]),
  matchTarget: zh([25509, 36817, 30446, 26631]),
  recommendedParams: zh([25512, 33616, 21442, 25968]),
  recommendation: zh([25512, 33616, 26041, 26696]),
  bestOxygen: zh([25512, 33616, 27687, 21547, 37327]),
  bestParticle: zh([25512, 33616, 31890, 24230, 20540]),
  expectedResult: zh([39044, 26399, 32467, 26524]),
  expectedScore: zh([21305, 37197, 24230]),
  currentValue: zh([24403, 21069, 20540]),
  bestValue: zh([26368, 20248, 20540]),
  changeSuggestion: zh([35843, 25972, 24314, 35758]),
  runOptimization: zh([35745, 31639, 26368, 20248, 21442, 25968]),
  objectiveScore: zh([30446, 26631, 24471, 20998]),
  targetProbability: zh([30446, 26631, 27010, 29575]),
  numericGuide: zh([36873, 25321, 30446, 26631, 32467, 26524, 21644, 35843, 21442, 26041, 21521, 65292, 31995, 32479, 20250, 25195, 25551, 27687, 21547, 37327, 19982, 36873, 23450, 31890, 24230, 21306, 38388, 65292, 25512, 33616, 30446, 26631, 24471, 20998, 26368, 39640, 30340, 32452, 21512, 12290]),
  newBarNote: zh([36825, 37324, 21482, 26174, 31034, 24403, 21069, 36873, 25321, 30340, 19968, 20010, 21487, 35843, 21442, 25968, 65292, 25968, 20540, 34920, 31034, 35813, 21442, 25968, 22312, 25195, 25551, 33539, 22260, 20869, 33021, 24102, 26469, 30340, 32467, 26524, 21464, 21270, 24133, 24230, 12290]),
  newLineNote: zh([21482, 23637, 31034, 24403, 21069, 36873, 25321, 21442, 25968, 30340, 25200, 21160, 26354, 32447, 65292, 26041, 20415, 21028, 26029, 22686, 20943, 26041, 21521, 12290]),
  newHeatNote: zh([39068, 33394, 36234, 28145, 30446, 26631, 24471, 20998, 36234, 39640, 65292, 22278, 28857, 20026, 25512, 33616, 32452, 21512, 12290]),
  singleParamChart: zh([21333, 21442, 25968, 35843, 21442, 26354, 32447]),
  comboOptMap: zh([21452, 21442, 25968, 20248, 21270, 22320, 22270]),
  targetPlaceholder: zh([36755, 20837, 30446, 26631, 31867, 21035]),
  categoryGuide: zh([31867, 21035, 30446, 26631, 20250, 20248, 20808, 35835, 21462, 27169, 22411, 27010, 29575, 65307, 39068, 33394, 36234, 28145, 34920, 31034, 36234, 25509, 36817, 25351, 23450, 35268, 26684, 25110, 28070, 28287, 31561, 32423, 12290]),
  metricLabel: zh([24403, 21069, 25351, 26631]),
  particleLabel: zh([31890, 24230, 32500, 24230]),
  closeModal: zh([20851, 38381, 24377, 31383]),
  chartGuide: zh([22270, 34920, 35299, 35835]),
  barGuide: zh([21333, 21442, 25968, 24433, 21709, 24378, 24230, 65306, 26609, 36234, 39640, 65292, 34920, 31034, 35813, 21442, 25968, 22312, 24403, 21069, 25200, 21160, 33539, 22260, 20869, 23545, 25152, 36873, 25351, 26631, 24433, 21709, 36234, 22823, 12290]),
  curveGuide: zh([21333, 21442, 25968, 25200, 21160, 26354, 32447, 65306, 27178, 36724, 20026, 25200, 21160, 27493, 38271, 65292, 32437, 36724, 20026, 25152, 36873, 25351, 26631, 65307, 26354, 32447, 36234, 38497, 35828, 26126, 36234, 25935, 24863, 12290]),
  heatmapGuide: zh([21452, 21442, 25968, 32452, 21512, 28909, 21147, 22270, 65306, 39068, 33394, 36234, 28145, 34920, 31034, 25152, 36873, 25351, 26631, 36234, 39640, 65292, 21487, 35266, 23519, 27687, 21547, 37327, 19982, 31890, 24230, 21306, 38388, 30340, 32452, 21512, 25928, 24212, 12290]),
  barNote: zh([26609, 36234, 39640, 65292, 20195, 34920, 35813, 21442, 25968, 29420, 31435, 35843, 33410, 26102, 36755, 20986, 21464, 21270, 36234, 22823, 12290]),
  lineNote: zh([27178, 36724, 32, 45, 50, 32, 21040, 32, 43, 50, 32, 20026, 25200, 21160, 27493, 38271, 65292, 26354, 32447, 36234, 38497, 20195, 34920, 36234, 25935, 24863, 12290]),
  heatNote: zh([39068, 33394, 36234, 28145, 65292, 20195, 34920, 24403, 21069, 25351, 26631, 20540, 36234, 39640, 65307, 27178, 36724, 20026, 27687, 21547, 37327, 65292, 32437, 36724, 20026, 25152, 36873, 31890, 24230, 21306, 38388, 12290]),
  singleImpact: zh([21333, 21442, 25968, 24433, 21709, 24378, 24230]),
  singleCurve: zh([21333, 21442, 25968, 25200, 21160, 26354, 32447]),
  comboHeatmap: zh([21452, 21442, 25968, 32452, 21512, 24433, 21709, 28909, 21147, 22270]),
  analysisEmpty: zh([28857, 20987, 36816, 34892, 20998, 26512, 21518, 65292, 31995, 32479, 20250, 22522, 20110, 24403, 21069, 36755, 20837, 33258, 21160, 25200, 21160, 27687, 21547, 37327, 21644, 31890, 24230, 20998, 24067, 65292, 24182, 29983, 25104, 24433, 21709, 31243, 24230, 22270, 12290]),
  formTitle: zh([37197, 26041, 21442, 25968, 35774, 32622]),
  inputParams: zh([36755, 20837, 21442, 25968]),
  fluxSystem: zh([21161, 28938, 21058, 20307, 31995]),
  fluxType: zh([21161, 28938, 33167, 22411, 21495]),
  selectType: zh([36873, 25321, 22411, 21495]),
  flux: zh([21161, 28938, 21058]),
  alloy: zh([21512, 37329]),
  fluxAlloyRatio: zh([21161, 28938, 21058, 47, 21512, 37329, 27604, 20363]),
  alloyComposition: zh([21512, 37329, 25104, 20998]),
  alloyGrade: zh([21512, 37329, 29260, 21495, 65288, 26679, 21697, 22522, 20934, 65289]),
  selectAlloy: zh([36873, 25321, 21512, 37329, 29260, 21495]),
  leadType: zh([38145, 20307, 31867, 22411]),
  detectedLeadType: zh([33258, 21160, 35782, 21035, 38145, 20307, 31867, 22411]),
  showFineTune: zh([26174, 31034, 24494, 35843]),
  alloyHint: zh([35831, 20808, 36873, 25321, 21512, 37329, 29260, 21495, 65292, 20877, 26597, 30475, 25110, 24494, 35843, 37329, 23646, 25104, 20998, 12290]),
  fineTuneHint: zh([24050, 25353, 26679, 21697, 22343, 20540, 22635, 20837, 65292, 21487, 26681, 25454, 24037, 20917, 24494, 35843, 12290]),
  oxygen: zh([27687, 21547, 37327]) + " (O)",
  fixedElements: zh([22266, 23450, 24494, 37327, 20803, 32032]) + ":",
  balance: zh([20313, 37327]),
  particleDistribution: zh([31890, 24230, 20998, 24067, 65288, 23454, 27979, 20540, 65289]),
  distributionViz: zh([20998, 24067, 21487, 35270, 21270]),
  particleTemplateHint: zh([27169, 26495, 19982, 21306, 38388, 21487, 32852, 21160, 35843, 25972]),
  particleTotal: zh([31890, 24230, 21512, 35745]),
  noParticle: zh([26242, 26080, 31890, 24230, 25968, 25454]),
  inputAnyParticle: zh([35831, 36755, 20837, 20219, 24847, 21306, 38388, 25968, 20540]),
  particleHint: zh([32570, 22833, 25110, 26080, 25928, 25353, 48, 22635, 20805, 65307, 27169, 22411, 25353, 25968, 20540, 22788, 29702, 65292, 19981, 24378, 21046, 35201, 27714, 24635, 21644, 20026, 49, 48, 48, 37, 12290]),
  startReasoning: zh([24615, 33021, 39044, 27979]),
  predictionResult: zh([39044, 27979, 32467, 26524]),
  analysisResult: zh([20998, 26512, 32467, 26524]),
  confidence: zh([32622, 20449, 24230]),
  powderSpec: zh([38177, 31881, 35268, 26684]),
  wettingClass: zh([28070, 28287, 31561, 32423]),
  viscosity: zh([40655, 24230, 21021, 20540]) + " (Pa.s)",
  tiIndex: zh([35302, 21464, 25351, 25968]) + " (Ti)",
  resultViz: zh([32467, 26524, 21487, 35270, 21270]),
  performanceMetrics: zh([24615, 33021, 25351, 26631]),
  categoryTop3: zh([31867, 21035, 39044, 27979]) + " Top3 " + zh([27010, 29575]),
  emptyResult: zh([35831, 22312, 24038, 20391, 37197, 32622, 21442, 25968, 24182, 24320, 22987, 25512, 29702]),
  baseline: zh([22522, 20934, 20540]),
  mostSensitive: zh([26368, 25935, 24863, 21442, 25968]),
  comboDimension: zh([32452, 21512, 32500, 24230]),
  impactValue: zh([24433, 21709, 20540]),
  analysisFailed: zh([24433, 21709, 20998, 26512, 22833, 36133, 65292, 35831, 30830, 35748, 21518, 31471, 25512, 29702, 26381, 21153, 21487, 29992]),
  reasoningDone: zh([26234, 33021, 25512, 29702, 23436, 25104]),
  reasoningFailed: zh([25512, 29702, 26381, 21153, 36830, 25509, 22833, 36133, 65292, 23637, 31034, 27169, 25311, 25968, 25454]),
  trainSuccess: zh([35757, 32451, 25104, 21151]),
  trainFailed: zh([35757, 32451, 22833, 36133]),
  trainRequestFailed: zh([35757, 32451, 35831, 27714, 22833, 36133]),
  offline: zh([31163, 32447]),
};

const message = useMessage();
const API_BASE_URL = import.meta.env.BASE_URL + 'api/v1';

const showAccuracyModal = ref(false);
const showImpactModal = ref(false);
const accuracyChartRef = ref(null);
let accuracyChartInstance = null;

const expandedInputSections = ref(["flux", "alloy"]);
const expandedResultSections = ref(["viz"]);
const showAlloyFineTune = ref(false);
const selectedParticleTemplateId = ref(null);

const modelInfo = ref({ name: "Checking...", status: "unknown", last_trained: "", accuracy: {} });
const loadingRetrain = ref(false);
const loadingPredict = ref(false);
const prediction = ref(null);
const featureRanges = ref(null);

const formX = reactive({
  alloy_grade: null,
  flux_type: "D1",
  flux_percent: 11.5,
  ag: 3.0,
  cu: 0.5,
  pb: 0.05,
  fe: 0.02,
  bi: 0,
  sb: 0,
  oxygen: 0.05,
  particle_size_real_lt_20: 0,
  particle_size_real_20_38: 0,
  particle_size_real_38_40: 0,
  particle_size_real_gt_40: 0,
});

const fallbackFluxTypes = ["D1", "E1", "F2", "F3", "F4", "X2", "A2", "G1", "X1", "X8", "K1", "Z1", "K5", "Z2"];
const detectLeadType = (alloyGrade, pbValue) => {
  const grade = String(alloyGrade || "").trim().toUpperCase();
  const pbText = String(pbValue ?? "").trim().toUpperCase();
  if (pbText.includes("余量")) return "leaded";
  if (grade.includes("PB") || grade.includes("铅")) return "leaded";
  if (/(^63A$|63\/?37|37\/?63|SN\d+(?:\.\d+)?PB|PBBI)/.test(grade)) return "leaded";
  const pbNum = Number(pbValue);
  return Number.isFinite(pbNum) && pbNum > 1 ? "leaded" : "lead_free";
};
const fluxTypeOptions = computed(() => {
  const source = featureRanges.value?.flux_pastes?.length ? featureRanges.value.flux_pastes : fallbackFluxTypes;
  return source.map((x) => ({ label: x, value: x }));
});
const alloyOptions = ref([]);
const alloyPresetMap = ref(new Map());
const alloyElementFields = [
  { key: "ag", label: "Ag", step: 0.1, unit: "kg" },
  { key: "cu", label: "Cu", step: 0.1, unit: "kg" },
  { key: "pb", label: "Pb", step: 0.01, unit: "kg" },
  { key: "fe", label: "Fe", step: 0.01, unit: "kg" },
  { key: "bi", label: "Bi", step: 0.01, unit: "kg" },
  { key: "sb", label: "Sb", step: 0.01, unit: "kg" },
];
const particleColors = ["#165DFF", "#00B42A", "#FF7D00", "#722ED1"];
const particleFields = [
  { key: "particle_size_real_lt_20", label: "<20um", color: particleColors[0] },
  { key: "particle_size_real_20_38", label: "20~38um", color: particleColors[1] },
  { key: "particle_size_real_38_40", label: "38~40um", color: particleColors[2] },
  { key: "particle_size_real_gt_40", label: ">40um", color: particleColors[3] },
];
const particleTemplateSegments = reactive([
  { key: particleFields[0].key, label: "<20µm", kind: "lt", start: null, end: 20, active: true, color: particleColors[0], slotIndex: 0 },
  { key: particleFields[1].key, label: "20～38µm", kind: "range", start: 20, end: 38, active: true, color: particleColors[1], slotIndex: 1 },
  { key: particleFields[2].key, label: "38～40µm", kind: "range", start: 38, end: 40, active: true, color: particleColors[2], slotIndex: 2 },
  { key: particleFields[3].key, label: ">40µm", kind: "gt", start: 40, end: null, active: true, color: particleColors[3], slotIndex: 3 },
]);

const alloyContent = computed(() => Math.max(0, Math.min(100, Number((100 - Number(formX.flux_percent || 0)).toFixed(2)))));
const currentLeadType = computed(() => {
  const preset = alloyPresetMap.value.get(formX.alloy_grade);
  if (preset) return detectLeadType(formX.alloy_grade, preset.raw_pb ?? preset.pb);
  return detectLeadType(formX.alloy_grade, formX.pb);
});
const particleSum = computed(() => particleFields.reduce((sum, item) => sum + Math.max(0, Number(formX[item.key] || 0)), 0));
const normalizedParticleValues = computed(() => {
  const total = particleSum.value;
  if (total <= 0) return [25, 25, 25, 25];
  const raw = particleFields.map((item) => Math.max(0, Number(formX[item.key] || 0)) / total * 100);
  const rounded = raw.map((value) => Number(value.toFixed(1)));
  const delta = Number((100 - rounded.reduce((sum, value) => sum + value, 0)).toFixed(1));
  rounded[rounded.length - 1] = Number((rounded[rounded.length - 1] + delta).toFixed(1));
  return rounded;
});
// 核心参数校验门：只有填了真实材料身份（合金牌号）+ 比例/氧含量/粒度分布后，两个按钮才可用
const canPredict = computed(() => {
  const fp = Number(formX.flux_percent || 0);
  const ox = Number(formX.oxygen || 0);
  return (
    !!formX.flux_type &&
    fp > 0 && fp <= 60 &&
    Number.isFinite(ox) && ox >= 0 &&
    !!formX.alloy_grade &&
    particleSum.value > 0
  );
});
const predictGateHint = computed(() => {
  if (!formX.alloy_grade) return "请先选择合金牌号";
  if (particleSum.value <= 0) return "请设置粒度分布（各段占比之和需大于 0）";
  if (!(Number(formX.flux_percent || 0) > 0)) return "请设置助焊剂/合金比例";
  if (!(Number(formX.oxygen || 0) >= 0)) return "请设置氧含量";
  return "";
});
const particleCuts = computed(() => {
  const values = normalizedParticleValues.value;
  return [values[0], values[0] + values[1], values[0] + values[1] + values[2]].map((value) => Math.max(0, Math.min(100, Number(value.toFixed(1)))));
});
const particleSegments = computed(() => normalizedParticleValues.value.map((value, index) => ({
  ...particleFields[index],
  label: particleTemplateSegments[index]?.label || particleFields[index].label,
  kind: particleTemplateSegments[index]?.kind || "range",
  start: particleTemplateSegments[index]?.start ?? null,
  end: particleTemplateSegments[index]?.end ?? null,
  active: particleTemplateSegments[index]?.active !== false,
  slotIndex: index,
  value: `${value.toFixed(1)}%`,
  width: `${Math.max(0, value)}%`,
})));
const editableParticleSegments = computed(() => particleSegments.value.filter((seg) => seg.active));
const isModelReady = computed(() => {
  const status = String(modelInfo.value?.status || "").toLowerCase();
  return status.includes("loaded") || status.includes("success") || status.includes("complete");
});
const hasAccuracyData = computed(() => {
  const a = modelInfo.value?.accuracy || {};
  return ["spec_acc", "wetting_acc", "collapse_acc", "solderball_acc", "viscosity_r2", "ti_r2"].some((key) => Number(a[key] || 0) !== 0);
});
const accuracyMetricCards = computed(() => {
  const acc = modelInfo.value?.accuracy || {};
  const metrics = modelInfo.value?.metrics || {};
  return [
    { key: "spec", label: text.powderSpec, value: `${(Number(acc.spec_acc || 0) * 100).toFixed(1)}%`, hint: "分类准确率" },
    { key: "wetting", label: text.wettingClass, value: `${(Number(acc.wetting_acc || 0) * 100).toFixed(1)}%`, hint: "分类准确率" },
    { key: "collapse", label: "坍塌类别", value: `${(Number(acc.collapse_acc || 0) * 100).toFixed(1)}%`, hint: "分类准确率" },
    { key: "solderball", label: "锡珠等级", value: `${(Number(acc.solderball_acc || 0) * 100).toFixed(1)}%`, hint: "分类准确率" },
    { key: "vis", label: text.viscosity, value: `${(Number(acc.viscosity_r2 || 0) * 100).toFixed(1)}%`, hint: `MAE ${Number(metrics["黏度初值"]?.mae || 0).toFixed(4)}` },
    { key: "ti", label: "Ti", value: `${(Number(acc.ti_r2 || 0) * 100).toFixed(1)}%`, hint: `MAE ${Number(metrics["Ti"]?.mae || 0).toFixed(4)}` },
  ];
});
const particleTemplateOptions = computed(() => {
  const items = Array.isArray(featureRanges.value?.particle_templates) ? featureRanges.value.particle_templates : [];
  return items
    .filter((item) => (item.lead_type || "lead_free") === currentLeadType.value)
    .map((item) => ({ label: item.label, value: item.id }));
});

const particleTrackRef = ref(null);
const visGaugeRef = ref(null);
const tiGaugeRef = ref(null);
const powderDonutRef = ref(null);
const wettingDonutRef = ref(null);
const collapseDonutRef = ref(null);
const solderballDonutRef = ref(null);
let visGaugeInstance = null;
let tiGaugeInstance = null;
let powderDonutInstance = null;
let wettingDonutInstance = null;
let collapseDonutInstance = null;
let solderballDonutInstance = null;

const loadingImpact = ref(false);
const reporting = ref(false);
const loadingProgress = ref(0);
const impactReady = ref(false);
const bestTuningResult = ref(null);
const lastImpactGroups = ref([]);
const singleParamCards = ref([]);
const multiXMultiYRows = ref([]);
const multiSurfaceCards = ref([]);
const singleImpactChartRefs = new Map();
const multiSurfaceChartRefs = new Map();
const singleImpactChartInstances = new Map();
const multiSurfaceChartInstances = new Map();
const impactModalPosition = reactive({ x: 0, y: 0 });
const impactPredictionCache = new Map();
const impactTargetConfigs = computed(() => [
  { key: "viscosity", title: text.viscosityBest, mode: "max" },
  { key: "ti", title: text.tiBest, mode: "max" },
  { key: "powder_spec", title: text.specBest, mode: "class", target: cleanPowderSpec(prediction.value?.powder_spec || featureRanges.value?.powder_specs?.[0] || "4A") },
  { key: "wetting_level", title: text.wettingBest, mode: "class", target: prediction.value?.wetting_level || featureRanges.value?.wetting_classes?.[0] || "1" },
  { key: "collapse_category", title: "坍塌最优", mode: "class", target: prediction.value?.collapse_category || featureRanges.value?.collapse_categories?.[0] || "冷" },
  { key: "solderball_level", title: "锡珠最优", mode: "class", target: prediction.value?.solderball_level || featureRanges.value?.solderball_levels?.[0] || "1" },
]);
const buildParticleDistributionJson = (source = formX) => {
  const payload = {};
  particleTemplateSegments.forEach((segment, index) => {
    if (!segment.active || !segment.label) return;
    const field = particleFields[index];
    payload[segment.label] = Number(source[field.key] || 0);
  });
  return JSON.stringify(payload);
};

const disposeChart = (chart) => {
  if (chart) chart.dispose();
};
const buildPredictionPayload = (overrides = {}) => {
  const merged = {
    flux_type: formX.flux_type,
    flux_percent: Number(formX.flux_percent || 0),
    alloy_content: Number(alloyContent.value || 0),
    pb: Number(formX.pb || 0),
    ag: Number(formX.ag || 0),
    fe: Number(formX.fe || 0),
    cu: Number(formX.cu || 0),
    bi: Number(formX.bi || 0),
    sb: Number(formX.sb || 0),
    oxygen_real: Number(formX.oxygen || 0),
    particle_size_real_lt_20: Number(formX.particle_size_real_lt_20 || 0),
    particle_size_real_20_38: Number(formX.particle_size_real_20_38 || 0),
    particle_size_real_38_40: Number(formX.particle_size_real_38_40 || 0),
    particle_size_real_gt_40: Number(formX.particle_size_real_gt_40 || 0),
    ...overrides,
  };
  return {
    flux_paste: merged.flux_type,
    flux_percent: Number(merged.flux_percent || 0),
    alloy_content: Number(merged.alloy_content || 0),
    pb: Number(merged.pb || 0),
    ag: Number(merged.ag || 0),
    fe: Number(merged.fe || 0),
    cu: Number(merged.cu || 0),
    bi: Number(merged.bi || 0),
    sb: Number(merged.sb || 0),
    oxygen_real: Number(merged.oxygen_real || 0),
    particle_size_real_lt_20: Number(merged.particle_size_real_lt_20 || 0),
    particle_size_real_20_38: Number(merged.particle_size_real_20_38 || 0),
    particle_size_real_38_40: Number(merged.particle_size_real_38_40 || 0),
    particle_size_real_gt_40: Number(merged.particle_size_real_gt_40 || 0),
    粒度分布_实测值_JSON: buildParticleDistributionJson(merged),
  };
};

const fetchModelInfo = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/model/info`);
    modelInfo.value = res.data;
  } catch {
    modelInfo.value = { name: text.offline, status: "unknown", last_trained: "", accuracy: {} };
  }
};
const loadFeatureRanges = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/feature-ranges`);
    featureRanges.value = res.data;
    if (!selectedParticleTemplateId.value && particleTemplateOptions.value.length) {
      selectedParticleTemplateId.value = particleTemplateOptions.value[0].value;
      applyParticleTemplateById(selectedParticleTemplateId.value);
    }
  } catch {
    featureRanges.value = null;
  }
};
const loadAlloys = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/alloys`);
    const presets = Array.isArray(res.data) ? res.data : [];
    alloyOptions.value = presets.map((p) => ({ label: p.alloy_grade, value: p.alloy_grade, lead_type: detectLeadType(p.alloy_grade, p.raw_pb ?? p.pb) }));
    alloyPresetMap.value = new Map(presets.map((p) => [p.alloy_grade, p]));
  } catch {
    alloyOptions.value = [];
    alloyPresetMap.value = new Map();
  }
};
const handleAlloyPreset = (val) => {
  const preset = alloyPresetMap.value.get(val);
  if (!preset) return;
  showAlloyFineTune.value = true;
  formX.pb = Number(preset.pb || 0);
  formX.ag = Number(preset.ag || 0);
  formX.fe = Number(preset.fe || 0);
  formX.cu = Number(preset.cu || 0);
  formX.bi = Number(preset.bi || 0);
  formX.sb = Number(preset.sb || 0);
  formX.oxygen = Number(preset.oxygen_real || 0);
};
const handleRetrain = async () => {
  loadingRetrain.value = true;
  try {
    const res = await axios.post(`${API_BASE_URL}/model/retrain`);
    if (res.data.success) {
      message.success(res.data.message || text.trainSuccess);
      modelInfo.value = res.data.info || res.data;
      if (showAccuracyModal.value) nextTick(renderAccuracyChart);
    } else {
      message.error(res.data.message || text.trainFailed);
    }
  } catch {
    message.error(text.trainRequestFailed);
  } finally {
    loadingRetrain.value = false;
  }
};
const getScoreColor = (score) => (score >= 9 ? "#00B42A" : score >= 7 ? "#FF7D00" : "#F53F3F");
const normalizeTop = (arr, fallbackLabel) => {
  const cleaned = (Array.isArray(arr) ? arr : [])
    .map((x) => ({ label: String(x?.label ?? ""), prob: Number(x?.prob ?? x?.value ?? 0) }))
    .filter((x) => x.label && Number.isFinite(x.prob));
  const sum = cleaned.reduce((s, x) => s + Math.max(0, x.prob), 0);
  if (!cleaned.length || sum <= 0) return [{ label: String(fallbackLabel || "N/A"), prob: 1 }];
  return cleaned.map((x) => ({ ...x, prob: Math.max(0, x.prob) / sum }));
};
const cleanPowderSpec = (value) => {
  const spec = String(value || "N/A").trim();
  return /-75|75\s*(u|μ|µ)m/i.test(spec) ? "N/A" : spec;
};
const sanitizePrediction = (item = {}) => ({
  ...item,
  wetting_level: String(item.wetting_level ?? item.wetting_class ?? "N/A"),
  collapse_category: String(item.collapse_category ?? "N/A"),
  solderball_level: String(item.solderball_level ?? "N/A"),
  powder_spec: cleanPowderSpec(item.powder_spec),
  powder_spec_top_probs: (Array.isArray(item.powder_spec_top_probs) ? item.powder_spec_top_probs : [])
    .map((x) => ({ ...x, label: cleanPowderSpec(x?.label) }))
    .filter((x) => x.label !== "N/A"),
  wetting_level_top_probs: Array.isArray(item.wetting_level_top_probs)
    ? item.wetting_level_top_probs
    : (Array.isArray(item.wetting_class_top_probs) ? item.wetting_class_top_probs : []),
  collapse_category_top_probs: Array.isArray(item.collapse_category_top_probs) ? item.collapse_category_top_probs : [],
  solderball_level_top_probs: Array.isArray(item.solderball_level_top_probs) ? item.solderball_level_top_probs : [],
});

const renderAccuracyChart = () => {
  if (!accuracyChartRef.value) return;
  disposeChart(accuracyChartInstance);
  accuracyChartInstance = echarts.init(accuracyChartRef.value);
  const acc = modelInfo.value?.accuracy || {};
  const data = [
    { name: text.powderSpec, v: Number(acc.spec_acc || 0) },
    { name: text.wettingClass, v: Number(acc.wetting_acc || 0) },
    { name: "坍塌类别", v: Number(acc.collapse_acc || 0) },
    { name: "锡珠等级", v: Number(acc.solderball_acc || 0) },
    { name: text.viscosity, v: Number(acc.viscosity_r2 || 0) },
    { name: "Ti R2", v: Number(acc.ti_r2 || 0) },
  ].map((d) => ({ ...d, v: Math.max(0, Math.min(1, d.v)) }));
  accuracyChartInstance.setOption({
    tooltip: { trigger: "item", formatter: (p) => `${p.name}: ${(Number(p.value) * 100).toFixed(1)}%` },
    radar: { radius: "68%", center: ["50%", "52%"], indicator: data.map((d) => ({ name: d.name, max: 1 })) },
    series: [{ type: "radar", data: [{ value: data.map((d) => d.v), name: text.modelAccuracy }], areaStyle: { color: "rgba(22,93,255,0.22)" } }],
  });
};
const applyParticlePercentages = (values) => {
  const fixed = values.map((value) => Math.max(0, Number(value || 0)));
  const total = fixed.reduce((sum, value) => sum + value, 0) || 100;
  const normalized = fixed.map((value) => value / total * 100);
  particleFields.forEach((field, index) => {
    formX[field.key] = Number(normalized[index].toFixed(1));
  });
};
const updateParticleLabelFromSegment = (segment) => {
  if (segment.kind === "lt") segment.label = `<${Number(segment.end || 0).toFixed(0)}µm`;
  else if (segment.kind === "gt") segment.label = `>${Number(segment.start || 0).toFixed(0)}µm`;
  else segment.label = `${Number(segment.start || 0).toFixed(0)}～${Number(segment.end || 0).toFixed(0)}µm`;
};
const applyParticleTemplateById = (templateId) => {
  const templates = Array.isArray(featureRanges.value?.particle_templates) ? featureRanges.value.particle_templates : [];
  const template = templates.find((item) => item.id === templateId);
  if (!template) return;
  selectedParticleTemplateId.value = templateId;
  particleTemplateSegments.forEach((segment, index) => {
    const source = template.segments?.[index];
    if (!source) {
      segment.active = false;
      segment.label = `未使用${index + 1}`;
      segment.kind = "range";
      segment.start = null;
      segment.end = null;
      formX[particleFields[index].key] = 0;
      return;
    }
    segment.active = true;
    segment.kind = source.kind || "range";
    segment.start = source.start ?? null;
    segment.end = source.end ?? null;
    segment.label = source.label || segment.label;
    updateParticleLabelFromSegment(segment);
  });
  const activeCount = particleTemplateSegments.filter((item) => item.active).length || 1;
  applyParticlePercentages(particleFields.map((_, index) => particleTemplateSegments[index].active ? Number((100 / activeCount).toFixed(2)) : 0));
};
const updateParticleBoundary = (visibleIndex, field, value) => {
  const segment = editableParticleSegments.value[visibleIndex];
  if (!segment) return;
  const target = particleTemplateSegments[segment.slotIndex];
  if (!target) return;
  const nextValue = value == null ? null : Number(value);
  if (field === "start") target.start = nextValue;
  if (field === "end") target.end = nextValue;
  if (target.kind === "range" && target.start != null && target.end != null && target.start > target.end) {
    const temp = target.start;
    target.start = target.end;
    target.end = temp;
  }
  updateParticleLabelFromSegment(target);
};
const updateParticleCut = (handleIndex, percent) => {
  const cuts = particleCuts.value.slice();
  const minGap = 0.1;
  const min = handleIndex === 0 ? minGap : cuts[handleIndex - 1] + minGap;
  const max = handleIndex === 2 ? 100 - minGap : cuts[handleIndex + 1] - minGap;
  cuts[handleIndex] = Math.max(min, Math.min(max, percent));
  applyParticlePercentages([cuts[0], cuts[1] - cuts[0], cuts[2] - cuts[1], 100 - cuts[2]]);
};
const updateParticleManual = (index, value) => {
  const targetIndex = editableParticleSegments.value[index]?.slotIndex ?? index;
  const next = normalizedParticleValues.value.slice();
  const oldValue = next[targetIndex];
  const newValue = Math.max(0, Math.min(100, Number(value ?? 0)));
  const delta = newValue - oldValue;
  const otherIndexes = next.map((_, i) => i).filter((i) => i !== targetIndex);
  const otherTotal = otherIndexes.reduce((sum, i) => sum + next[i], 0);
  next[targetIndex] = newValue;
  if (otherTotal <= 0) {
    const share = (100 - newValue) / otherIndexes.length;
    otherIndexes.forEach((i) => { next[i] = share; });
  } else {
    otherIndexes.forEach((i) => {
      next[i] = Math.max(0, next[i] - delta * (next[i] / otherTotal));
    });
  }
  applyParticlePercentages(next);
};
const startParticleDrag = (handleIndex, event) => {
  const rect = particleTrackRef.value?.getBoundingClientRect();
  if (!rect) return;
  const move = (e) => updateParticleCut(handleIndex, ((e.clientX - rect.left) / rect.width) * 100);
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
};
const startParticleTrackDrag = (event) => {
  const rect = particleTrackRef.value?.getBoundingClientRect();
  if (!rect) return;
  const percent = ((event.clientX - rect.left) / rect.width) * 100;
  const nearest = particleCuts.value.reduce((best, cut, index) => (Math.abs(cut - percent) < Math.abs(particleCuts.value[best] - percent) ? index : best), 0);
  updateParticleCut(nearest, percent);
  startParticleDrag(nearest, event);
};
const renderGauge = (elRef, prevInstance, title, value, color) => {
  if (!elRef.value) return prevInstance;
  disposeChart(prevInstance);
  const inst = echarts.init(elRef.value);
  const v = Number(value || 0);
  const max = title.includes("Ti") ? Math.max(1, v * 1.2, 0.6) : Math.max(300, v * 1.2, 50);
  inst.setOption({
    series: [{ type: "gauge", startAngle: 210, endAngle: -30, min: 0, max, progress: { show: true, width: 10 }, axisLine: { lineStyle: { width: 10, color: [[1, "#E5E6EB"]] } }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, pointer: { show: false }, detail: { formatter: (val) => Number(val).toFixed(title.includes("Ti") ? 4 : 2), color: "#1D2129", fontSize: 16, fontWeight: 800, offsetCenter: [0, "10%"] }, data: [{ value: v }], itemStyle: { color } }],
  });
  return inst;
};
const renderDonut = (elRef, prevInstance, items, colors) => {
  if (!elRef.value) return prevInstance;
  disposeChart(prevInstance);
  const inst = echarts.init(elRef.value);
  inst.setOption({
    tooltip: { trigger: "item", formatter: (p) => `${p.name}: ${(Number(p.value) * 100).toFixed(2)}%` },
    legend: { bottom: 0, left: "center", icon: "circle", textStyle: { fontSize: 11 } },
    color: colors,
    series: [{ type: "pie", radius: ["55%", "78%"], center: ["50%", "42%"], label: { formatter: (p) => `${(Number(p.value) * 100).toFixed(2)}%`, fontSize: 11, fontWeight: 700 }, data: items.map((x) => ({ name: x.label, value: x.prob })) }],
  });
  return inst;
};
const renderResultCharts = () => {
  if (!prediction.value) return;
  visGaugeInstance = renderGauge(visGaugeRef, visGaugeInstance, text.viscosity, prediction.value.viscosity, "#00B42A");
  tiGaugeInstance = renderGauge(tiGaugeRef, tiGaugeInstance, "Ti", prediction.value.ti, "#165DFF");
  powderDonutInstance = renderDonut(powderDonutRef, powderDonutInstance, normalizeTop(prediction.value.powder_spec_top_probs, prediction.value.powder_spec), ["#165DFF", "#4080FF", "#8FB8FF"]);
  wettingDonutInstance = renderDonut(wettingDonutRef, wettingDonutInstance, normalizeTop(prediction.value.wetting_level_top_probs, prediction.value.wetting_level), ["#722ED1", "#9C6BFF", "#D3B5FF"]);
  collapseDonutInstance = renderDonut(collapseDonutRef, collapseDonutInstance, normalizeTop(prediction.value.collapse_category_top_probs, prediction.value.collapse_category), ["#FF7D00", "#FFB65D", "#FFD8A8"]);
  solderballDonutInstance = renderDonut(solderballDonutRef, solderballDonutInstance, normalizeTop(prediction.value.solderball_level_top_probs, prediction.value.solderball_level), ["#00B42A", "#66DDAA", "#B8F5D2"]);
};
const handlePredict = async () => {
  loadingPredict.value = true;
  try {
    const res = await axios.post(`${API_BASE_URL}/predict`, { features: buildPredictionPayload() });
    prediction.value = sanitizePrediction({ ...res.data.predictions, score: res.data.score ?? 0, execution_time_ms: res.data.execution_time_ms ?? 0 });
    message.success(text.reasoningDone);
    await nextTick();
    renderResultCharts();
  } catch {
    message.error(text.reasoningFailed);
    prediction.value = null;
  } finally {
    loadingPredict.value = false;
  }
};

const exportPredictionReport = async () => {
  if (!prediction.value) {
    message.warning("请先执行性能预测");
    return;
  }
  reporting.value = true;
  try {
    const res = await axios.post(`${API_BASE_URL}/report`, {
      report_type: "prediction",
      predictions: prediction.value,
      score: prediction.value.score || 0,
      input_features: buildPredictionPayload(),
      execution_time_ms: prediction.value.execution_time_ms || 0,
    }, { responseType: "blob" });
    const blob = new Blob([res.data], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `锡膏性能预测报告_${new Date().toISOString().slice(0,19).replace(/[T:]/g,"")}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success("报告已导出");
  } catch (err) {
    message.error("报告生成失败：" + (err.response?.data?.detail || err.message));
  } finally {
    reporting.value = false;
  }
};

const exportOptimizationReport = async () => {
  if (!bestTuningResult.value) {
    message.warning("请先执行配方优化");
    return;
  }
  reporting.value = true;
  try {
    const res = await axios.post(`${API_BASE_URL}/report`, {
      report_type: "optimization",
      predictions: prediction.value || {},
      input_features: buildPredictionPayload(),
      best_result: bestTuningResult.value,
      recommended_params: bestTuningResult.value?.recommendedParams || null,
      impact_groups: (lastImpactGroups.value || []).map((g) => {
        const scores = (g.points || []).map((p) => Number(p.result?.predictions?.score || 0));
        const range = scores.length ? Math.max(...scores) - Math.min(...scores) : 0;
        return { name: g.name, impact_pct: Math.round(range * 1000) / 10, raw_range: range };
      }),
    }, { responseType: "blob" });
    const blob = new Blob([res.data], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `锡膏配方优化报告_${new Date().toISOString().slice(0,19).replace(/[T:]/g,"")}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success("报告已导出");
  } catch (err) {
    message.error("报告生成失败：" + (err.response?.data?.detail || err.message));
  } finally {
    reporting.value = false;
  }
};

const probePrediction = async (overrides = {}) => {
  const payload = buildPredictionPayload(overrides);
  const cacheKey = JSON.stringify(payload);
  if (impactPredictionCache.has(cacheKey)) {
    return impactPredictionCache.get(cacheKey);
  }
  const res = await axios.post(`${API_BASE_URL}/predict`, { features: payload, log: false });
  const normalized = { ...res.data, predictions: sanitizePrediction(res.data.predictions || {}) };
  impactPredictionCache.set(cacheKey, normalized);
  if (impactPredictionCache.size > 180) {
    const firstKey = impactPredictionCache.keys().next().value;
    if (firstKey) impactPredictionCache.delete(firstKey);
  }
  return normalized;
};
const classProbability = (predictions, metric, target) => {
  const listKeyMap = {
    powder_spec: "powder_spec_top_probs",
    wetting_level: "wetting_level_top_probs",
    collapse_category: "collapse_category_top_probs",
    solderball_level: "solderball_level_top_probs",
  };
  const predictedKeyMap = {
    powder_spec: "powder_spec",
    wetting_level: "wetting_level",
    collapse_category: "collapse_category",
    solderball_level: "solderball_level",
  };
  const listKey = listKeyMap[metric];
  const predictedKey = predictedKeyMap[metric];
  const wanted = String(target || "").trim().toLowerCase();
  const items = Array.isArray(predictions?.[listKey]) ? predictions[listKey] : [];
  const hit = items.find((x) => String(x?.label || "").trim().toLowerCase() === wanted);
  if (hit) return Number(hit.prob || 0);
  return String(predictions?.[predictedKey] || "").trim().toLowerCase() === wanted ? 1 : 0;
};
const objectiveFor = (result, config) => {
  const predictions = result?.predictions || result || {};
  if (config.mode === "class") return topClassProb(predictions, config.key);
  return Number(predictions?.[config.key] ?? 0);
};
const displayFor = (result, config) => {
  const p = result?.predictions || result || {};
  if (config.key === "powder_spec") return cleanPowderSpec(p.powder_spec);
  if (config.key === "wetting_level") return String(p.wetting_level || "-");
  if (config.key === "collapse_category") return String(p.collapse_category || "-");
  if (config.key === "solderball_level") return String(p.solderball_level || "-");
  return Number(p?.[config.key] || 0).toFixed(4);
};
const scanValuesFor = (key, fallbackBase) => {
  const item = featureRanges.value?.features?.[key];
  const base = Number(fallbackBase || 0);
  const minRaw = Number(item?.q10 ?? item?.min);
  const maxRaw = Number(item?.q90 ?? item?.max);
  let min = Number.isFinite(minRaw) ? Math.max(0, minRaw) : Math.max(0, base - Math.max(base * 0.5, key === "oxygen_real" ? 0.02 : 10));
  let max = Number.isFinite(maxRaw) ? Math.max(min, maxRaw) : base + Math.max(base * 0.5, key === "oxygen_real" ? 0.02 : 10);
  min = Math.min(min, base);
  max = Math.max(max, base);
  if (max === min) max = min + (key === "oxygen_real" ? 0.02 : 10);
  const count = key === "oxygen_real" ? 6 : 6;
  const step = (max - min) / Math.max(1, count - 1);
  return Array.from({ length: count }, (_, index) => Number((min + step * index).toFixed(4)));
};
const currentParticleProfile = () => ({
  label: text.currentValue,
  values: Object.fromEntries(particleFields.map((field) => [field.key, Number(formX[field.key] || 0)])),
});
const particleProfiles = computed(() => {
  const profiles = Array.isArray(featureRanges.value?.particle_profiles) ? featureRanges.value.particle_profiles : [];
  const normalized = profiles
    .filter((profile) => profile?.values)
    .map((profile) => ({ label: profile.label || `P`, values: profile.values }));
  const current = currentParticleProfile();
  const seen = new Set();
  return [current, ...normalized].filter((profile) => {
    const signature = particleFields.map((field) => Number(profile.values?.[field.key] || 0).toFixed(4)).join("|");
    if (seen.has(signature)) return false;
    seen.add(signature);
    return true;
  });
});
const impactModalStyle = computed(() => ({
  transform: `translate(${impactModalPosition.x}px, ${impactModalPosition.y}px)`,
}));
const groupedSingleParamCards = computed(() => {
  const groups = {};
  singleParamCards.value.forEach((card) => {
    if (!groups[card.xKey]) {
      groups[card.xKey] = {
        key: card.xKey,
        name: card.xName,
        cards: [],
      };
    }
    groups[card.xKey].cards.push(card);
  });
  return Object.values(groups);
});

const resetImpactAnalysis = () => {
  impactReady.value = false;
  loadingProgress.value = 0;
  bestTuningResult.value = null;
  singleParamCards.value = [];
  multiXMultiYRows.value = [];
  multiSurfaceCards.value = [];
  impactPredictionCache.clear();
  singleImpactChartInstances.forEach((chart) => chart.dispose());
  singleImpactChartInstances.clear();
  multiSurfaceChartInstances.forEach((chart) => chart.dispose());
  multiSurfaceChartInstances.clear();
};
const openImpactModal = () => {
  resetImpactAnalysis();
  showImpactModal.value = true;
};
const startImpactDrag = (event) => {
  if (event.button !== 0) return;
  const startX = event.clientX;
  const startY = event.clientY;
  const baseX = impactModalPosition.x;
  const baseY = impactModalPosition.y;
  const move = (e) => {
    impactModalPosition.x = baseX + e.clientX - startX;
    impactModalPosition.y = baseY + e.clientY - startY;
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
};
const distributionSegmentsFor = (profile) => {
  const total = particleFields.reduce((sum, field) => sum + Math.max(0, Number(profile?.values?.[field.key] || 0)), 0) || 100;
  return particleFields.map((field) => {
    const value = Math.max(0, Number(profile?.values?.[field.key] || 0)) / total * 100;
    return { label: field.label, value: `${value.toFixed(1)}%`, width: `${Math.max(0, value)}%`, color: field.color };
  });
};
const particleProjectionScore = (profile) => {
  const weights = [10, 29, 39, 50];
  const total = particleFields.reduce((sum, field) => sum + Math.max(0, Number(profile?.values?.[field.key] || 0)), 0) || 100;
  return particleFields.reduce((sum, field, index) => sum + (Math.max(0, Number(profile?.values?.[field.key] || 0)) / total) * weights[index], 0);
};
const profileAtProjection = (profiles, projection) => {
  if (!profiles.length) return currentParticleProfile();
  return profiles.slice().sort((a, b) => Math.abs(particleProjectionScore(a) - projection) - Math.abs(particleProjectionScore(b) - projection))[0];
};
const interpolatePredictions = (points, oxygen, projection, metricKey) => {
  if (!points.length) return 0;
  let weighted = 0;
  let weightSum = 0;
  for (const point of points) {
    const dx = Number(point.oxygen) - oxygen;
    const dy = particleProjectionScore(point.profile) - projection;
    const distance = Math.sqrt(dx * dx + dy * dy);
    const weight = 1 / Math.max(distance, 0.0001);
    weighted += valueForSurface(point, metricKey) * weight;
    weightSum += weight;
  }
  return weightSum ? weighted / weightSum : 0;
};
const particleDetailText = (profile) => particleFields.map((field) => `${field.label} ${Number(profile?.values?.[field.key] || 0).toFixed(1)}`).join(" / ");
const numericRangeText = (points, key) => {
  const values = points.map((point) => Number(point.result?.predictions?.[key])).filter((value) => Number.isFinite(value));
  if (!values.length) return "-";
  return `${Math.min(...values).toFixed(4)} ~ ${Math.max(...values).toFixed(4)}`;
};
const categorySetText = (points, key) => {
  const values = [...new Set(points.map((point) => {
    if (key === "powder_spec") return cleanPowderSpec(point.result?.predictions?.powder_spec);
    if (key === "wetting_level") return String(point.result?.predictions?.wetting_level || "-");
    if (key === "collapse_category") return String(point.result?.predictions?.collapse_category || "-");
    return String(point.result?.predictions?.solderball_level || "-");
  }).filter((value) => value && value !== "-"))];
  return values.length <= 1 ? `${values[0] || "-"} (${text.noChange})` : `${values.join(" / ")} (${text.changed})`;
};
const topClassProb = (predictions, key) => {
  const listMap = {
    powder_spec: predictions?.powder_spec_top_probs,
    wetting_level: predictions?.wetting_level_top_probs,
    collapse_category: predictions?.collapse_category_top_probs,
    solderball_level: predictions?.solderball_level_top_probs,
  };
  const list = listMap[key];
  const first = Array.isArray(list) && list.length ? Number(list[0]?.prob || 0) : 0;
  return Number.isFinite(first) ? first : 0;
};
const normalizeScores = (points) => {
  const valuesFor = (key) => points.map((point) => Number(point.result?.predictions?.[key])).filter((value) => Number.isFinite(value));
  const visValues = valuesFor("viscosity");
  const tiValues = valuesFor("ti");
  const visMin = visValues.length ? Math.min(...visValues) : 0;
  const visMax = visValues.length ? Math.max(...visValues) : 0;
  const tiMin = tiValues.length ? Math.min(...tiValues) : 0;
  const tiMax = tiValues.length ? Math.max(...tiValues) : 0;
  const scaled = (value, min, max) => (max > min ? (value - min) / (max - min) : 0.5);
  return points.map((point) => {
    const p = point.result?.predictions || {};
    const score = (
      scaled(Number(p.viscosity || 0), visMin, visMax) +
      scaled(Number(p.ti || 0), tiMin, tiMax) +
      topClassProb(p, "powder_spec") +
      topClassProb(p, "wetting_level") +
      topClassProb(p, "collapse_category") +
      topClassProb(p, "solderball_level")
    ) / 6;
    return { ...point, score: Number.isFinite(score) ? score : 0 };
  });
};
const buildSingleParamCards = (groups, base) => {
  const cards = [];
  for (const group of groups) {
    for (const config of impactTargetConfigs.value) {
      const points = group.points.map((point, index) => ({
        ...point,
        axisValue: group.key === "oxygen"
          ? Number(point.oxygen).toFixed(4)
          : (group.key === "ratio" ? `${Number(point.flux_percent || 0).toFixed(2)} / ${Number(point.alloy_content || 0).toFixed(2)}` : point.profile.label),
        x: index,
        score: objectiveFor(point.result, config),
        value: displayFor(point.result, config),
      }));
      const scores = points.map((point) => point.score).filter((value) => Number.isFinite(value));
      const best = points.reduce((acc, point) => (!acc || point.score > acc.score ? point : acc), null);
      const values = [...new Set(points.map((point) => point.value))];
      const rangeText = config.mode === "class"
        ? values.join(" / ")
        : `${Math.min(...scores).toFixed(4)} ~ ${Math.max(...scores).toFixed(4)}`;
      cards.push({
        key: `${group.key}-${config.key}`,
        xKey: group.key,
        xName: group.name,
        yKey: config.key,
        yName: config.title,
        mode: config.mode,
        baseline: displayFor(base, config),
        rangeText,
        bestAxisValue: best?.axisValue || "-",
        points,
      });
    }
  }
  return cards;
};
const buildComboRows = (scored) => scored
  .slice()
  .sort((a, b) => b.score - a.score)
  .slice(0, 3)
  .map((point, index) => {
    const p = point.result?.predictions || {};
    return {
      rank: index + 1,
      key: `combo-${index}-${point.oxygen}-${point.profile.label}`,
      combo: `${text.oxygen} ${Number(point.oxygen).toFixed(4)} / ${point.profile.label}`,
      distribution: distributionSegmentsFor(point.profile),
      viscosity: Number(p.viscosity || 0).toFixed(4),
      ti: Number(p.ti || 0).toFixed(4),
      powder: cleanPowderSpec(p.powder_spec),
      wetting: String(p.wetting_level || "-"),
      collapse: String(p.collapse_category || "-"),
      solderball: String(p.solderball_level || "-"),
      score: point.score.toFixed(4),
      note: index === 0 ? text.bestTuningNote : text.comboTableCopy,
    };
  });
const setSingleImpactChartRef = (key, el) => {
  if (el) singleImpactChartRefs.set(key, el);
};
const setMultiSurfaceChartRef = (key, el) => {
  if (el) multiSurfaceChartRefs.set(key, el);
};
const resizeImpactCharts = () => {
  singleImpactChartInstances.forEach((chart) => chart.resize());
  multiSurfaceChartInstances.forEach((chart) => chart.resize());
};
const adaptiveYAxisFor = (card, data) => {
  const values = data.filter((value) => Number.isFinite(value));
  if (!values.length) return { min: 0, max: 1 };
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (card.mode === "class") {
    const span = max - min;
    const pad = Math.max(span * 0.35, 0.04);
    return {
      min: Math.max(0, Number((min - pad).toFixed(4))),
      max: Math.min(1, Number((max + pad).toFixed(4))),
      interval: null,
    };
  }
  const span = max - min;
  const basePad = Math.max(Math.abs(max || min) * 0.006, card.yKey === "ti" ? 0.006 : 0.8);
  const pad = span > 0 ? Math.max(span * 0.35, basePad) : basePad;
  return {
    min: Number((min - pad).toFixed(card.yKey === "ti" ? 4 : 2)),
    max: Number((max + pad).toFixed(card.yKey === "ti" ? 4 : 2)),
    interval: null,
  };
};
const renderSingleImpactCharts = () => {
  singleImpactChartInstances.forEach((chart) => chart.dispose());
  singleImpactChartInstances.clear();
  for (const card of singleParamCards.value) {
    const el = singleImpactChartRefs.get(card.key);
    if (!el) continue;
    const chart = echarts.init(el);
    const labels = card.points.map((point) => point.axisValue);
    const data = card.points.map((point) => Number(point.score.toFixed(4)));
    const bestIndex = card.points.reduce((best, point, index) => (point.score > card.points[best].score ? index : best), 0);
    const yAxisRange = adaptiveYAxisFor(card, data);
    chart.setOption({
      grid: { left: 48, right: 14, top: 28, bottom: 58 },
      tooltip: {
        trigger: "axis",
        formatter: (params) => {
          const idx = params?.[0]?.dataIndex || 0;
          const point = card.points[idx];
          return `${card.xName}: ${point.axisValue}<br/>${card.yName}: ${point.value}<br/>${card.mode === "class" ? text.classConfidence : text.predictedValue}: ${Number(point.score).toFixed(4)}`;
        },
      },
      xAxis: { type: "category", data: labels, axisLabel: { fontSize: 10, interval: 0, rotate: 35, margin: 14 } },
      yAxis: {
        type: "value",
        scale: true,
        min: yAxisRange.min,
        max: yAxisRange.max,
        name: card.mode === "class" ? text.classConfidence : text.predictedValue,
        nameTextStyle: { fontSize: 10, color: "#86909c" },
        axisLabel: { fontSize: 10, formatter: (value) => Number(value).toFixed(card.mode === "class" || card.yKey === "ti" ? 3 : 1) },
        splitLine: { lineStyle: { type: "dashed", color: "#dbeafe" } },
      },
      series: [{
        type: "line",
        smooth: true,
        symbolSize: 7,
        data,
        areaStyle: { opacity: 0.12 },
        lineStyle: { width: 2, color: "#165DFF" },
        itemStyle: { color: "#165DFF" },
        markPoint: {
          symbolSize: 42,
          label: { formatter: text.bestValue, fontSize: 10 },
          data: [{ coord: [labels[bestIndex], data[bestIndex]], value: data[bestIndex] }],
        },
      }],
    });
    singleImpactChartInstances.set(card.key, chart);
  }
};
const valueForSurface = (point, key) => {
  const p = point.result?.predictions || {};
  if (key === "score") return point.score;
  if (key === "powder_spec") return topClassProb(p, "powder_spec");
  if (key === "wetting_level") return topClassProb(p, "wetting_level");
  if (key === "collapse_category") return topClassProb(p, "collapse_category");
  if (key === "solderball_level") return topClassProb(p, "solderball_level");
  return Number(p[key] || 0);
};
const buildMultiSurfaceCards = (scored) => ([
  { key: "viscosity", title: text.viscosity, metricKey: "viscosity" },
  { key: "ti", title: "Ti", metricKey: "ti" },
  { key: "powder_spec", title: `${text.powderSpec}${text.classConfidence}`, metricKey: "powder_spec" },
  { key: "wetting_level", title: `${text.wettingClass}${text.classConfidence}`, metricKey: "wetting_level" },
  { key: "collapse_category", title: `坍塌类别${text.classConfidence}`, metricKey: "collapse_category" },
  { key: "solderball_level", title: `锡珠等级${text.classConfidence}`, metricKey: "solderball_level" },
  { key: "score", title: text.compositeScore, metricKey: "score" },
]).map((card) => {
  const best = scored.reduce((acc, point) => (!acc || valueForSurface(point, card.metricKey) > valueForSurface(acc, card.metricKey) ? point : acc), null);
  return { ...card, best };
});
const mixColor = (a, b, t) => {
  const ah = Number.parseInt(a.replace("#", ""), 16);
  const bh = Number.parseInt(b.replace("#", ""), 16);
  const ar = (ah >> 16) & 255;
  const ag = (ah >> 8) & 255;
  const ab = ah & 255;
  const br = (bh >> 16) & 255;
  const bg = (bh >> 8) & 255;
  const bb = bh & 255;
  const rr = Math.round(ar + (br - ar) * t);
  const rg = Math.round(ag + (bg - ag) * t);
  const rb = Math.round(ab + (bb - ab) * t);
  return `rgb(${rr}, ${rg}, ${rb})`;
};
const terrainRgb = (ratio) => {
  const palette = ["#2b6cb0", "#39a0ca", "#4fbe82", "#d9d45b", "#f4a340", "#d94d32"];
  const scaled = Math.max(0, Math.min(1, ratio)) * (palette.length - 1);
  const index = Math.min(palette.length - 2, Math.floor(scaled));
  const color = mixColor(palette[index], palette[index + 1], scaled - index);
  const [r, g, b] = color.match(/\d+/g).map(Number);
  return { r, g, b };
};
const terrainColor = (ratio, light = 1) => {
  const { r, g, b } = terrainRgb(ratio);
  const clamp = (value) => Math.max(0, Math.min(255, Math.round(value * light)));
  return `rgb(${clamp(r)}, ${clamp(g)}, ${clamp(b)})`;
};
const clampNumber = (value, min, max) => Math.max(min, Math.min(max, value));
const drawTerrainSurface = (canvas, scored, card, xGrid, yGrid, bounds) => {
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(520, Math.floor(rect.width || 640));
  const height = Math.max(360, Math.floor(rect.height || 360));
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const { xMin, xMax, yMin, yMax } = bounds;
  const zMatrix = yGrid.map((y) => xGrid.map((x) => interpolatePredictions(scored, x, y, card.metricKey)));
  const flatZ = zMatrix.flat();
  const zMin = Math.min(...flatZ);
  const zMax = Math.max(...flatZ);
  const zRange = zMax - zMin || 1;
  const originX = width * 0.5;
  const originY = height * 0.78;
  const scaleX = width * 0.7;
  const scaleY = height * 0.62;
  const scaleZ = height * 0.44;
  const project = (x, y, z) => {
    const nx = xMax > xMin ? (x - xMin) / (xMax - xMin) : 0.5;
    const ny = yMax > yMin ? (y - yMin) / (yMax - yMin) : 0.5;
    const nz = (z - zMin) / zRange;
    return {
      x: originX + (nx - ny) * scaleX * 0.58,
      y: originY + (nx + ny) * scaleY * 0.22 - nz * scaleZ,
      nx,
      ny,
      nz,
    };
  };
  const shadeFor = (xi, yi, z) => {
    const left = zMatrix[yi]?.[Math.max(0, xi - 1)] ?? z;
    const right = zMatrix[yi]?.[Math.min(xGrid.length - 1, xi + 1)] ?? z;
    const up = zMatrix[Math.max(0, yi - 1)]?.[xi] ?? z;
    const down = zMatrix[Math.min(yGrid.length - 1, yi + 1)]?.[xi] ?? z;
    const sx = right - left;
    const sy = down - up;
    return 0.92 + Math.max(-0.16, Math.min(0.24, (-sx * 0.55 - sy * 0.35) / zRange));
  };
  const bg = ctx.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, "#f7fbff");
  bg.addColorStop(1, "#eef7f4");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);
  const axisOrigin = project(xMin, yMin, zMin);
  const xEnd = project(xMax, yMin, zMin);
  const yEnd = project(xMin, yMax, zMin);
  const zEnd = project(xMin, yMin, zMax);
  const drawLine = (a, b, color = "#4e5969", widthLine = 1.2) => {
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.strokeStyle = color;
    ctx.lineWidth = widthLine;
    ctx.stroke();
  };
  const drawText = (label, x, y, options = {}) => {
    const padding = options.padding ?? 3;
    ctx.font = options.font || "11px sans-serif";
    ctx.textAlign = options.align || "left";
    ctx.textBaseline = options.baseline || "alphabetic";
    const widthText = ctx.measureText(label).width;
    const safeY = clampNumber(y, 16, height - 10);
    const textX = options.align === "center"
      ? clampNumber(x, padding + widthText / 2, width - padding - widthText / 2)
      : options.align === "right"
        ? clampNumber(x, widthText + padding, width - padding)
        : clampNumber(x, padding, width - widthText - padding);
    if (options.background) {
      const rectX = options.align === "center" ? textX - widthText / 2 - padding : textX - padding;
      const rectY = safeY - 13;
      ctx.fillStyle = options.background;
      ctx.fillRect(rectX, rectY, widthText + padding * 2, 17);
    }
    ctx.fillStyle = options.color || "#1d2129";
    ctx.fillText(label, textX, safeY);
  };
  ctx.save();
  ctx.translate(width * 0.5, height * 0.82);
  ctx.scale(1, 0.32);
  const shadow = ctx.createRadialGradient(0, 0, 20, 0, 0, width * 0.42);
  shadow.addColorStop(0, "rgba(37, 74, 111, 0.18)");
  shadow.addColorStop(1, "rgba(37, 74, 111, 0)");
  ctx.fillStyle = shadow;
  ctx.beginPath();
  ctx.ellipse(0, 0, width * 0.38, height * 0.2, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  const baseCorners = [
    project(xMin, yMin, zMin),
    project(xMax, yMin, zMin),
    project(xMax, yMax, zMin),
    project(xMin, yMax, zMin),
  ];
  ctx.beginPath();
  ctx.moveTo(baseCorners[0].x, baseCorners[0].y);
  baseCorners.slice(1).forEach((p) => ctx.lineTo(p.x, p.y));
  ctx.closePath();
  ctx.fillStyle = "rgba(255, 255, 255, 0.72)";
  ctx.fill();
  ctx.strokeStyle = "rgba(78, 89, 105, 0.24)";
  ctx.stroke();
  const cells = [];
  let peak = { x: xGrid[0], y: yGrid[0], z: zMatrix[0]?.[0] ?? zMin, xi: 0, yi: 0 };
  for (let yi = 0; yi < yGrid.length - 1; yi++) {
    for (let xi = 0; xi < xGrid.length - 1; xi++) {
      if (zMatrix[yi][xi] > peak.z) peak = { x: xGrid[xi], y: yGrid[yi], z: zMatrix[yi][xi], xi, yi };
      const corners = [
        { x: xGrid[xi], y: yGrid[yi], z: zMatrix[yi][xi], xi, yi },
        { x: xGrid[xi + 1], y: yGrid[yi], z: zMatrix[yi][xi + 1], xi, yi },
        { x: xGrid[xi + 1], y: yGrid[yi + 1], z: zMatrix[yi + 1][xi + 1], xi, yi },
        { x: xGrid[xi], y: yGrid[yi + 1], z: zMatrix[yi + 1][xi], xi, yi },
      ];
      cells.push({ corners, depth: yi + xi, z: corners.reduce((sum, p) => sum + p.z, 0) / 4, xi, yi });
    }
  }
  for (let yi = 0; yi < yGrid.length; yi++) {
    for (let xi = 0; xi < xGrid.length; xi++) {
      if (zMatrix[yi][xi] > peak.z) peak = { x: xGrid[xi], y: yGrid[yi], z: zMatrix[yi][xi], xi, yi };
    }
  }
  cells.sort((a, b) => a.depth - b.depth);
  for (const cell of cells) {
    const pts = cell.corners.map((p) => project(p.x, p.y, p.z));
    const ratio = (cell.z - zMin) / zRange;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    pts.slice(1).forEach((p) => ctx.lineTo(p.x, p.y));
    ctx.closePath();
    ctx.fillStyle = terrainColor(ratio, shadeFor(cell.xi, cell.yi, cell.z));
    ctx.fill();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.lineWidth = 0.08;
    ctx.stroke();
  }
  drawLine(axisOrigin, xEnd, "#4e5969", 1.4);
  drawLine(axisOrigin, yEnd, "#4e5969", 1.4);
  drawLine(axisOrigin, zEnd, "#4e5969", 1.4);
  const tickValues = (min, max) => [min, (min + max) / 2, max];
  for (const value of tickValues(xMin, xMax)) {
    const p = project(value, yMin, zMin);
    drawLine({ x: p.x, y: p.y - 4 }, { x: p.x, y: p.y + 4 }, "#86909c", 1);
    drawText(value.toFixed(4), p.x, p.y + 18, { color: "#4e5969", font: "10px sans-serif", align: "center" });
  }
  for (const value of tickValues(yMin, yMax)) {
    const p = project(xMin, value, zMin);
    drawLine({ x: p.x - 4, y: p.y }, { x: p.x + 4, y: p.y }, "#86909c", 1);
    drawText(value.toFixed(1), p.x - 8, p.y + 2, { color: "#4e5969", font: "10px sans-serif", align: "right" });
  }
  for (const value of tickValues(zMin, zMax)) {
    const p = project(xMin, yMin, value);
    drawLine({ x: p.x - 4, y: p.y }, { x: p.x + 4, y: p.y }, "#86909c", 1);
    drawText(value.toFixed(2), p.x - 8, p.y + 3, { color: "#4e5969", font: "10px sans-serif", align: "right" });
  }
  drawText(text.oxygenShort, xEnd.x + 8, xEnd.y + 26, { color: "#1d2129", font: "700 12px sans-serif" });
  drawText(text.particleProjection, yEnd.x - 10, yEnd.y - 10, { color: "#1d2129", font: "700 12px sans-serif", align: "right" });
  drawText("Z", zEnd.x + 6, Math.max(18, zEnd.y - 12), { color: "#1d2129", font: "700 12px sans-serif", background: "rgba(247, 251, 255, 0.86)" });
  const bestPoint = project(peak.x, peak.y, peak.z);
  if (Number.isFinite(bestPoint.x) && Number.isFinite(bestPoint.y)) {
    const floorPoint = project(peak.x, peak.y, zMin);
    drawLine(floorPoint, bestPoint, "rgba(245, 63, 63, 0.48)", 1.2);
    ctx.beginPath();
    ctx.arc(bestPoint.x, bestPoint.y, 5.5, 0, Math.PI * 2);
    ctx.fillStyle = "#f53f3f";
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.stroke();
    const badgeText = `${text.bestPoint}  O ${peak.x.toFixed(4)}   P ${peak.y.toFixed(1)}   Z ${peak.z.toFixed(3)}`;
    drawText(badgeText, 12, 20, { color: "#1d2129", font: "700 11px sans-serif", background: "rgba(255, 255, 255, 0.9)", padding: 6 });
  }
};
const renderMultiSurfaceCharts = (scored) => {
  multiSurfaceChartInstances.forEach((chart) => chart.dispose());
  multiSurfaceChartInstances.clear();
  const allX = scored.map((point) => point.oxygen);
  const allY = scored.map((point) => particleProjectionScore(point.profile));
  const xMin = Math.min(...allX);
  const xMax = Math.max(...allX);
  const yMin = Math.min(...allY);
  const yMax = Math.max(...allY);
  const xSteps = 42;
  const ySteps = 32;
  const xGrid = Array.from({ length: xSteps }, (_, index) => xMin + ((xMax - xMin) * index) / Math.max(1, xSteps - 1));
  const yGrid = Array.from({ length: ySteps }, (_, index) => yMin + ((yMax - yMin) * index) / Math.max(1, ySteps - 1));
  for (const card of multiSurfaceCards.value) {
    const el = multiSurfaceChartRefs.get(card.key);
    if (!el) continue;
    const surfaceData = [];
    let best = { x: xGrid[0], y: yGrid[0], z: interpolatePredictions(scored, xGrid[0], yGrid[0], card.metricKey) };
    for (const y of yGrid) {
      for (const x of xGrid) {
        const z = interpolatePredictions(scored, x, y, card.metricKey);
        surfaceData.push([Number(x.toFixed(6)), Number(y.toFixed(3)), Number(z.toFixed(6))]);
        if (z > best.z) best = { x, y, z };
      }
    }
    const zValues = surfaceData.map((point) => point[2]);
    const zMin = Math.min(...zValues);
    const zMax = Math.max(...zValues);
    const chart = echarts.init(el);
    chart.setOption({
      tooltip: {
        formatter: (params) => {
          const value = params.value || [];
          return `${text.oxygenShort}: ${Number(value[0]).toFixed(4)}<br/>${text.particleProjection}: ${Number(value[1]).toFixed(1)}<br/>${card.title}: ${Number(value[2]).toFixed(4)}`;
        },
      },
      visualMap: {
        show: false,
        min: zMin,
        max: zMax,
        dimension: 2,
        inRange: { color: ["#2b6cb0", "#39a0ca", "#4fbe82", "#d9d45b", "#f4a340", "#d94d32"] },
      },
      xAxis3D: {
        type: "value",
        name: text.oxygenShort,
        min: xMin,
        max: xMax,
        nameTextStyle: { color: "#1d2129", fontWeight: 700 },
        axisLabel: { color: "#4e5969", formatter: (value) => Number(value).toFixed(4) },
        axisLine: { lineStyle: { color: "#64748b" } },
        splitLine: { lineStyle: { color: "rgba(100, 116, 139, 0.16)" } },
      },
      yAxis3D: {
        type: "value",
        name: text.particleProjection,
        min: yMin,
        max: yMax,
        nameTextStyle: { color: "#1d2129", fontWeight: 700 },
        axisLabel: { color: "#4e5969", formatter: (value) => Number(value).toFixed(1) },
        axisLine: { lineStyle: { color: "#64748b" } },
        splitLine: { lineStyle: { color: "rgba(100, 116, 139, 0.16)" } },
      },
      zAxis3D: {
        type: "value",
        name: card.title,
        min: zMin,
        max: zMax,
        nameTextStyle: { color: "#1d2129", fontWeight: 700 },
        axisLabel: { color: "#4e5969", formatter: (value) => Number(value).toFixed(card.metricKey === "ti" ? 3 : 2) },
        axisLine: { lineStyle: { color: "#64748b" } },
        splitLine: { lineStyle: { color: "rgba(100, 116, 139, 0.16)" } },
      },
      grid3D: {
        boxWidth: card.key === "score" ? 180 : 120,
        boxDepth: card.key === "score" ? 78 : 64,
        boxHeight: 58,
        top: -8,
        bottom: 4,
        left: 0,
        right: 0,
        environment: "#ffffff",
        axisPointer: { show: true },
        viewControl: {
          projection: "perspective",
          alpha: 34,
          beta: -38,
          distance: card.key === "score" ? 190 : 150,
          rotateSensitivity: 1,
          zoomSensitivity: 1,
          panSensitivity: 0,
        },
        light: {
          main: { intensity: 1.35, shadow: true, alpha: 45, beta: 25 },
          ambient: { intensity: 0.45 },
        },
        postEffect: {
          enable: true,
          SSAO: { enable: true, radius: 3, intensity: 0.55 },
        },
      },
      series: [
        {
          type: "surface",
          data: surfaceData,
          shading: "realistic",
          wireframe: { show: false },
          realisticMaterial: { roughness: 0.55, metalness: 0 },
          itemStyle: { opacity: 1 },
        },
        {
          type: "scatter3D",
          data: [[Number(best.x.toFixed(6)), Number(best.y.toFixed(3)), Number(best.z.toFixed(6))]],
          symbolSize: 12,
          itemStyle: { color: "#f53f3f", borderColor: "#fff", borderWidth: 2 },
          label: {
            show: true,
            position: "top",
            distance: 18,
            formatter: `${text.bestPoint}\nO ${best.x.toFixed(4)} / P ${best.y.toFixed(1)} / Z ${best.z.toFixed(3)}`,
            color: "#1d2129",
            fontSize: 11,
            fontWeight: 700,
            backgroundColor: "rgba(255,255,255,0.95)",
            borderColor: "rgba(245, 63, 63, 0.25)",
            borderWidth: 1,
            borderRadius: 4,
            padding: [5, 7],
          },
        },
      ],
    });
    multiSurfaceChartInstances.set(card.key, chart);
  }
};
const runImpactAnalysis = async () => {
  loadingImpact.value = true;
  loadingProgress.value = 0;
  try {
    resetImpactAnalysis();
    loadingProgress.value = 5;
    if (!featureRanges.value) await loadFeatureRanges();
    if (!featureRanges.value?.features || !Object.keys(featureRanges.value.features).length) {
      message.error(text.noDataRange);
      return;
    }
    loadingProgress.value = 10;
    
    const oxygenBase = Number(formX.oxygen || 0);
    const xValues = scanValuesFor("oxygen_real", oxygenBase);
    const profiles = particleProfiles.value.slice(0, 4);
    const baselineProfile = currentParticleProfile();
    const ratioValues = scanValuesFor("flux_percent", Number(formX.flux_percent || 0))
      .map((value) => Math.max(0, Math.min(100, value)));

    // 构建所有预测任务以实现并行加速
    const tasks = [];
    tasks.push({ id: "base", overrides: {} });
    
    xValues.forEach(oxygen => {
      tasks.push({ id: "oxygen", label: `${text.oxygen} ${oxygen.toFixed(4)}`, oxygen, profile: baselineProfile, overrides: { oxygen_real: oxygen, ...baselineProfile.values } });
    });
    
    ratioValues.forEach(fluxPercent => {
      const currentAlloyContent = Math.max(0, Number((100 - fluxPercent).toFixed(4)));
      tasks.push({ id: "ratio", label: `${fluxPercent.toFixed(2)} / ${currentAlloyContent.toFixed(2)}`, oxygen: oxygenBase, flux_percent: fluxPercent, alloy_content: currentAlloyContent, profile: baselineProfile, overrides: { flux_percent: fluxPercent, alloy_content: currentAlloyContent, oxygen_real: oxygenBase, ...baselineProfile.values } });
    });
    
    profiles.forEach(profile => {
      tasks.push({ id: "particle", label: profile.label, oxygen: oxygenBase, profile, overrides: { oxygen_real: oxygenBase, ...profile.values } });
    });
    
    profiles.forEach((profile, pIndex) => {
      xValues.forEach((oxygen, xIndex) => {
        tasks.push({ id: "grid", x: xIndex, y: pIndex, oxygen, profile, overrides: { oxygen_real: oxygen, ...profile.values } });
      });
    });

    let completed = 0;
    const taskResults = await Promise.all(tasks.map(async (task) => {
      const res = await probePrediction(task.overrides);
      completed++;
      loadingProgress.value = Math.floor(10 + (completed / tasks.length) * 85);
      return { ...task, result: res };
    }));

    const base = taskResults.find(r => r.id === "base").result;
    const oxygenOnlyResults = taskResults.filter(r => r.id === "oxygen");
    const ratioOnlyResults = taskResults.filter(r => r.id === "ratio");
    const particleOnlyResults = taskResults.filter(r => r.id === "particle");
    const gridResults = taskResults.filter(r => r.id === "grid");

    const scoredGrid = normalizeScores(gridResults);
    const best = scoredGrid.reduce((acc, point) => (!acc || point.score > acc.score ? point : acc), null);
    const bestPred = best?.result?.predictions || {};
    bestTuningResult.value = best ? {
      score: best.score.toFixed(4),
      xText: `${text.oxygen} ${Number(best.oxygen).toFixed(4)} / ${text.particleProfile} ${best.profile.label}`,
      particleDetail: particleDetailText(best.profile),
      distribution: distributionSegmentsFor(best.profile),
      note: text.bestTuningNote,
      recommendedParams: {
        flux_percent: Number(best.flux_percent != null ? best.flux_percent : formX.flux_percent).toFixed(2),
        alloy_content: Number(best.alloy_content != null ? best.alloy_content : alloyContent.value).toFixed(2),
        oxygen_real: Number(best.oxygen != null ? best.oxygen : formX.oxygen).toFixed(4),
        particle_profile: best.profile ? best.profile.label : "",
        particle_distribution: best.profile ? distributionSegmentsFor(best.profile) : [],
      },
      outputs: [
        { label: text.viscosity, value: Number(bestPred.viscosity || 0).toFixed(4), extra: text.predictedValue },
        { label: "Ti", value: Number(bestPred.ti || 0).toFixed(4), extra: text.predictedValue },
        { label: text.powderSpec, value: cleanPowderSpec(bestPred.powder_spec), extra: `${text.highestConfidence} ${topClassProb(bestPred, "powder_spec").toFixed(4)}` },
        { label: text.wettingClass, value: String(bestPred.wetting_level || "-"), extra: `${text.highestConfidence} ${topClassProb(bestPred, "wetting_level").toFixed(4)}` },
        { label: "坍塌类别", value: String(bestPred.collapse_category || "-"), extra: `${text.highestConfidence} ${topClassProb(bestPred, "collapse_category").toFixed(4)}` },
        { label: "锡珠等级", value: String(bestPred.solderball_level || "-"), extra: `${text.highestConfidence} ${topClassProb(bestPred, "solderball_level").toFixed(4)}` },
      ],
    } : null;
    const groups = [
      {
        key: "oxygen",
        name: text.oxygenFactor,
        range: `${Math.min(...xValues).toFixed(4)} ~ ${Math.max(...xValues).toFixed(4)}`,
        points: oxygenOnlyResults,
      },
      {
        key: "particle",
        name: text.particleFactor,
        range: `${text.currentRecipe} / ${profiles.map((profile) => profile.label).join(" / ")}`,
        points: particleOnlyResults,
      },
      {
        key: "ratio",
        name: "助焊剂/合金比例",
        range: `${Math.min(...ratioValues).toFixed(2)} / ${Math.max(...ratioValues.map((value) => 100 - value)).toFixed(2)} ~ ${Math.max(...ratioValues).toFixed(2)} / ${Math.min(...ratioValues.map((value) => 100 - value)).toFixed(2)}`,
        points: ratioOnlyResults,
      },
    ];
    singleParamCards.value = buildSingleParamCards(groups, base);
    lastImpactGroups.value = groups;
    multiXMultiYRows.value = buildComboRows(scoredGrid);
    multiSurfaceCards.value = buildMultiSurfaceCards(scoredGrid);
    impactReady.value = true;
    await nextTick();
    renderSingleImpactCharts();
    renderMultiSurfaceCharts(scoredGrid);
    loadingProgress.value = 100;
  } catch {
    message.error(text.modelUnavailable);
  } finally {
    loadingImpact.value = false;
  }
};

watch(showAccuracyModal, (v) => v && nextTick(renderAccuracyChart));
watch(expandedResultSections, () => nextTick(renderResultCharts));
watch(currentLeadType, () => {
  const nextTemplate = particleTemplateOptions.value[0]?.value || null;
  selectedParticleTemplateId.value = nextTemplate;
  if (nextTemplate) applyParticleTemplateById(nextTemplate);
});
watch(showImpactModal, (v) => {
  if (v) nextTick(resizeImpactCharts);
});
onMounted(() => {
  fetchModelInfo();
  loadAlloys();
  loadFeatureRanges();
  applyParticlePercentages([25, 25, 25, 25]);
  window.addEventListener("resize", resizeImpactCharts);
});
onUnmounted(() => {
  window.removeEventListener("resize", resizeImpactCharts);
  singleImpactChartInstances.forEach((chart) => chart.dispose());
  multiSurfaceChartInstances.forEach((chart) => chart.dispose());
});
</script>

<style scoped>
.reasoning-container {
  height: calc(100vh - 96px);
  max-height: calc(100vh - 96px);
  overflow: hidden;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.model-status-bar,
.panel-card {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.04);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
}

.model-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 14px;
  border-radius: 8px;
  margin-bottom: 8px;
}

.status-left,
.status-right,
.title-group,
.collapse-header,
.result-actions,
.modal-header-actions,
.ratio-mini-top,
.toggle-box,
.tags-row,
.hero-score-text,
.hero-kv,
.modal-title-row,
.impact-toolbar {
  display: flex;
  align-items: center;
}

.status-left,
.status-right,
.title-group,
.collapse-header,
.result-actions,
.modal-header-actions,
.ratio-mini-top,
.tags-row,
.hero-score-text {
  gap: 8px;
}

.modal-title-row,
.panel-header {
  justify-content: space-between;
}

.status-label,
.status-detail,
.status-warning,
.impact-hint,
.fine-hint,
.empty-hint,
.fixed-label,
.m-label,
.kv-k,
.hero-score-sub,
.modal-hint,
.empty-text {
  color: #86909c;
}

.status-warning {
  color: #f53f3f;
  font-size: 12px;
}

.main-grid {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  grid-template-rows: 1fr;
  align-items: stretch;
  align-content: stretch;
}

:deep(.n-grid) {
  height: 100%;
  min-height: 0;
}

:deep(.n-grid-item) > .panel-card {
  height: 100%;
  min-height: 0;
}

.panel-card {
  border-radius: 10px;
  height: 100%;
  min-height: 0;
}

.panel-card :deep(.n-card-header) {
  padding: 8px 12px !important;
}

:deep(.n-grid-item) {
  height: 100%;
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

.panel-card :deep(.n-card__content) {
  padding: 8px 10px !important;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  padding-bottom: 4px;
  border-bottom: 1px solid #f0f0f0;
}

.panel-title {
  font-size: 15px;
  font-weight: 700;
  color: #1d2129;
}

.icon-box {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-box.blue {
  background: rgba(22, 93, 255, 0.1);
  color: #165dff;
}
.icon-box.green {
  background: rgba(0, 180, 42, 0.1);
  color: #00b42a;
}

.scroll-container {
  flex: 1 1 0;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  padding: 0 0 8px;
  position: relative;
}

.compact-form {
  padding: 0 0 46px;
  display: flex;
  flex-direction: column;
}

.compact-form :deep(.n-collapse-item__header) {
  padding: 6px 0 !important;
}

.compact-form :deep(.n-collapse-item__content-inner) {
  padding-top: 0 !important;
  padding-bottom: 4px !important;
}

.compact-form :deep(.n-form-item-label) {
  min-height: 18px;
  padding-bottom: 2px;
  font-size: 12px;
}

.section-dot {
  width: 4px;
  height: 14px;
  border-radius: 2px;
}
.bg-primary { background: #165dff; }
.bg-warning { background: #ff7d00; }
.bg-purple { background: #722ed1; }
.bg-cyan { background: #00b42a; }

.section-name {
  font-size: 13px;
  font-weight: 700;
  color: #4e5969;
}

.section-body {
  padding: 3px 1px 1px;
}

.row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.alloy-top-row,
.particle-top-row {
  display: grid;
  gap: 8px;
  align-items: start;
}

.alloy-top-row {
  grid-template-columns: minmax(0, 1fr) auto;
}

.particle-top-row {
  grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
}

.compact-row {
  margin-top: 6px;
}

.compact-row-tight {
  margin-top: 3px;
}

.flux-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.no-mb {
  margin-bottom: 0 !important;
}

.ratio-mini,
.empty-hint,
.fixed-elements,
.chart-tile,
.metric-mini,
.result-hero,
.impact-summary-item,
.analysis-empty {
  background: #f7f8fa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}

.ratio-mini {
  padding: 6px 8px;
}

.ratio-compact-card,
.inline-tip-card,
.boundary-card,
.accuracy-kpi,
.accuracy-metric-card {
  background: #f7f8fa;
  border: 1px solid #eef0f3;
  border-radius: 8px;
}

.ratio-compact-card {
  padding: 5px 10px 5px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ratio-full-width {
  width: 100%;
  overflow: hidden;
}

.ratio-inline-head,
.ratio-inline-body,
.boundary-head,
.boundary-row,
.accuracy-kpi-grid,
.accuracy-metric-grid {
  display: flex;
  align-items: center;
}

.ratio-inline-head,
.boundary-head {
  justify-content: space-between;
}

.ratio-inline-head {
  min-height: 28px;
  gap: 8px;
}

.boundary-head strong {
  font-size: 10px;
  line-height: 1.1;
}

.ratio-inline-head > div {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1px;
  min-width: 0;
  min-height: 28px;
}

.ratio-inline-head span,
.inline-tip-card span,
.accuracy-kpi span,
.accuracy-metric-card span,
.accuracy-metric-card small {
  color: #86909c;
  font-size: 12px;
}

.ratio-inline-head span {
  font-size: 11px;
  line-height: 1.1;
}

.ratio-inline-body,
.boundary-row {
  gap: 4px;
}

.ratio-floating-input {
  width: 86px;
  flex-shrink: 0;
}

.ratio-compact-card :deep(.n-slider) {
  margin: 0;
}

.ratio-compact-card :deep(.n-slider-rail) {
  margin: 0;
}

.ratio-split-chip,
.boundary-sep {
  color: #4e5969;
  font-weight: 700;
}

.boundary-sep {
  font-size: 10px;
}

.boundary-card :deep(.n-input-number) {
  --n-height: 24px !important;
}

.boundary-card :deep(.n-input-number .n-input__input-el),
.boundary-card :deep(.n-input-number .n-input__suffix) {
  font-size: 11px !important;
}

.inline-tip-card {
  padding: 7px 10px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
}

.inline-tip-card strong,
.ratio-inline-head strong,
.boundary-head strong,
.accuracy-kpi strong,
.accuracy-metric-card strong {
  color: #1d2129;
  font-weight: 800;
}

.ratio-inline-head strong {
  font-size: 12px;
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.r-label,
.toggle-text,
.fixed-label,
.tile-title,
.impact-summary-item span {
  font-size: 12px;
  color: #4e5969;
  font-weight: 700;
}

.r-val,
.m-value,
.kv-v,
.hero-score-num,
.impact-summary-item strong {
  font-weight: 800;
  color: #1d2129;
}

.alloy-table {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 5px;
}

.alloy-cell {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 7px;
  padding: 5px 6px;
}

.oxygen-cell {
  grid-column: span 2;
}

.alloy-label {
  font-size: 12px;
  font-weight: 700;
  color: #4e5969;
  margin-bottom: 3px;
}

.compact-fixed,
.fine-hint,
.chart-card-gap,
.metric-grid,
.result-collapse {
  margin-top: 5px;
}

.alloy-grade-item,
.particle-template-item {
  min-width: 0;
}

.alloy-toggle-box {
  min-height: 28px;
  margin-top: 24px;
  padding: 0 10px;
  border: 1px solid #eef0f3;
  border-radius: 8px;
  background: #f7f8fa;
  white-space: nowrap;
}

.sticky-footer {
  position: sticky;
  bottom: 0;
  padding-top: 6px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0) 0%, #fff 55%);
  z-index: 2;
}

.main-btn {
  height: 34px;
  font-weight: 700;
  border-radius: 8px;
}

.gate-hint {
  margin-top: 6px;
  text-align: center;
  font-size: 12px;
  color: #f53f3f;
  line-height: 1.4;
}

.export-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 6px;
}

.particle-boundary-panel {
  background: #f7f8fa;
  border: 1px solid #eef0f3;
  border-radius: 8px;
  padding: 5px;
  margin-top: -2px;
}

.particle-distribution-editor {
  background: #f7f8fa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 4px 6px;
}

.particle-boundary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 5px;
  margin-bottom: 0;
}

.boundary-card {
  padding: 4px 5px;
  background: #fff;
}

.particle-editor-top,
.particle-legend {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.particle-editor-top span,
.particle-editor-top strong {
  color: #4e5969;
  font-size: 10px;
  font-weight: 800;
}

.particle-track {
  position: relative;
  display: flex;
  height: 28px;
  margin-top: 3px;
  overflow: hidden;
  border-radius: 6px;
  border: 1px solid #e5e6eb;
  cursor: ew-resize;
  user-select: none;
}

.particle-segment {
  min-width: 0;
  display: grid;
  place-items: center;
  align-content: center;
  color: #fff;
  font-size: 8px;
  font-weight: 800;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.particle-segment span,
.particle-segment strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.particle-segment span {
  display: none;
}

.particle-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 10px;
  transform: translateX(-50%);
  border: 0;
  border-left: 2px solid #fff;
  border-right: 2px solid #fff;
  background: rgba(29, 33, 41, 0.24);
  cursor: ew-resize;
}

.particle-legend {
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 4px;
  color: #4e5969;
  font-size: 10px;
  font-weight: 700;
}

.particle-legend i {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 2px;
  margin-right: 4px;
}

.particle-manual-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 3px;
  margin-top: 3px;
}

.particle-manual-cell {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 3px 4px;
}

.particle-manual-cell > span {
  display: block;
  color: #4e5969;
  font-size: 9px;
  font-weight: 800;
  margin-bottom: 1px;
}

@media (max-width: 1280px) {
  .particle-top-row {
    grid-template-columns: 1fr;
  }

  .alloy-top-row {
    grid-template-columns: 1fr;
  }

  .alloy-toggle-box {
    width: fit-content;
    margin-top: 0;
  }
}

.empty-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.result-content {
  padding-top: 6px;
}

.result-hero {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 9px 10px;
}

.hero-left {
  flex: 1;
}

.hero-right {
  display: grid;
  gap: 6px;
  justify-items: end;
}

.metric-mini,
.chart-tile {
  padding: 8px 10px;
}

.class-tag {
  background: linear-gradient(135deg, #f0f5ff 0%, #e8f0fe 100%);
  border: 1px solid #c0d3ff;
  border-radius: 8px;
  padding: 8px 10px;
  text-align: center;
}

.class-tag-label {
  font-size: 11px;
  font-weight: 600;
  color: #4a6cf7;
  margin-bottom: 3px;
  letter-spacing: 0.3px;
}

.class-tag-value {
  font-size: 15px;
  font-weight: 800;
  color: #1d2129;
}

.chart-card {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 8px;
  padding: 8px;
}

.detail-header {
  font-size: 13px;
  font-weight: 700;
  color: #4e5969;
  margin-bottom: 6px;
}

.chart-lg {
  width: 100%;
  height: 320px;
}
.chart-gauge {
  width: 100%;
  height: 122px;
}
.chart-donut {
  width: 100%;
  height: 148px;
}

.accuracy-modal {
  width: 720px;
  max-width: 90vw;
}

.accuracy-kpi-grid {
  gap: 10px;
  margin-bottom: 10px;
}

.accuracy-kpi {
  flex: 1;
  padding: 10px 12px;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.accuracy-metric-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.accuracy-metric-card {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.impact-modal {
  width: min(1560px, 98vw);
  height: 94vh;
  max-height: 94vh;
  overflow: auto;
  position: relative;
  background: #fdfdfd;
  border-radius: 12px;
}

.impact-modal :deep(.n-card__content) {
  padding: 16px 20px 20px !important;
}

.impact-modal :deep(.n-card-header) {
  padding: 16px 20px 10px !important;
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid #f0f0f0;
}

.draggable-title {
  cursor: move;
  user-select: none;
}

.impact-close-btn {
  position: sticky;
  top: 8px;
  right: 8px;
  z-index: 12;
}

.impact-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.modal-header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.best-tuning-card {
  background: linear-gradient(135deg, #f0f5ff 0%, #f7f8fa 100%);
  border: 1px solid #d9e7ff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.best-tuning-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.recommend-title {
  color: #1d2129;
  font-size: 14px;
  font-weight: 800;
}

.best-tuning-grid {
  display: grid;
  grid-template-columns: 1.45fr repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.best-tuning-grid > div {
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid #e5e6eb;
  border-radius: 7px;
  padding: 7px 9px;
  min-width: 0;
}

.best-tuning-grid span,
.best-tuning-grid small {
  display: block;
  color: #4e5969;
  font-size: 12px;
  font-weight: 700;
}

.best-tuning-grid small {
  margin-top: 3px;
  color: #86909c;
  font-weight: 500;
  line-height: 1.35;
}

.best-tuning-grid strong {
  display: block;
  color: #1d2129;
  font-size: 14px;
  font-weight: 800;
  margin-top: 3px;
  word-break: break-word;
}

.score-pill {
  display: grid;
  justify-items: end;
  gap: 2px;
  color: #4e5969;
  font-size: 12px;
  font-weight: 700;
}

.score-pill strong {
  color: #165dff;
  font-size: 20px;
  font-weight: 900;
}

.impact-note {
  margin-top: 8px;
  color: #4e5969;
  font-size: 12px;
  line-height: 1.45;
}

.mini-dist {
  display: flex;
  width: 100%;
  height: 24px;
  overflow: hidden;
  border: 1px solid #e5e6eb;
  border-radius: 6px;
  margin-top: 6px;
  background: #fff;
}

.mini-dist span {
  display: grid;
  place-items: center;
  min-width: 0;
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  white-space: nowrap;
  overflow: hidden;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.22);
}

.impact-table-stack {
  display: grid;
  gap: 8px;
}

.impact-table-section {
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  padding: 8px;
  background: #fff;
}

.table-title {
  color: #1d2129;
  font-size: 13px;
  font-weight: 800;
  margin-bottom: 6px;
}

.single-card-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.variable-impact-row {
  margin-bottom: 16px;
  border-bottom: 1px dashed #e5e6eb;
  padding-bottom: 12px;
}
.variable-impact-row:last-child {
  border-bottom: none;
  margin-bottom: 0;
}
.variable-row-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.var-dot {
  width: 4px;
  height: 14px;
  background: #165dff;
  border-radius: 2px;
}
.var-name {
  font-size: 14px;
  font-weight: 700;
  color: #1d2129;
}
.variable-row-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.single-param-card,
.combo-top-card {
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  background: #fafafa;
  padding: 8px;
  min-width: 0;
}

.single-param-card {
  background: #f7f8fa;
  display: flex;
  flex-direction: column;
}

.y-name {
  font-size: 12px;
  font-weight: 700;
  color: #4e5969;
}

.single-card-mini-meta {
  margin-top: 6px;
  font-size: 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.meta-item {
  display: flex;
  justify-content: space-between;
}
.m-label {
  color: #4a6cf7;
  font-weight: 600;
}
.m-val {
  color: #1d2129;
  font-weight: 700;
}

.impact-loading-box {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: 20px;
}
.impact-progress {
  width: 300px;
}
.loading-text {
  font-size: 12px;
  color: #165dff;
  font-weight: 700;
  animation: pulse 1.5s infinite;
}
@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.single-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #1d2129;
  font-size: 13px;
  font-weight: 800;
}

.single-card-head span {
  color: #165dff;
  font-size: 12px;
}

.single-card-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 5px;
  margin-top: 7px;
}

.single-card-meta div {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 5px 6px;
}

.single-card-meta span,
.single-card-meta strong {
  display: block;
  font-size: 11px;
}

.single-card-meta span {
  color: #86909c;
  font-weight: 700;
}

.single-card-meta strong {
  color: #1d2129;
  font-weight: 800;
  margin-top: 2px;
  word-break: break-word;
}

.single-impact-chart {
  width: 100%;
  height: 110px;
  margin-top: 4px;
}

.score-formula {
  color: #4e5969;
  font-size: 12px;
  line-height: 1.45;
  background: #f7f8fa;
  border: 1px solid #e5e6eb;
  border-radius: 7px;
  padding: 7px 9px;
  margin-bottom: 8px;
}

.combo-top-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.combo-rank {
  color: #165dff;
  font-size: 12px;
  font-weight: 900;
}

.combo-main {
  margin-top: 3px;
  color: #1d2129;
  font-size: 13px;
  font-weight: 800;
}

.combo-dist {
  height: 26px;
}

.combo-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  margin-top: 7px;
  color: #4e5969;
  font-size: 11px;
  font-weight: 700;
}

.particle-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  margin-top: 6px;
  color: #4e5969;
  font-size: 11px;
  font-weight: 700;
}

.particle-detail-grid span {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 5px;
  padding: 3px 5px;
}

.particle-detail-grid i {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 2px;
  margin-right: 4px;
}

.combo-score {
  margin-top: 7px;
  color: #165dff;
  font-size: 13px;
  font-weight: 900;
}

.surface-chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 8px;
}

.surface-chart-card {
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  background: #fafafa;
  padding: 8px;
}

.surface-chart-card:last-child {
  grid-column: 1 / span 2;
}

.surface-title {
  color: #1d2129;
  font-size: 13px;
  font-weight: 800;
  margin-bottom: 4px;
}

.surface-chart {
  width: 100%;
  height: 340px;
}

.recommend-copy {
  color: #4e5969;
  font-size: 12px;
  margin-top: 8px;
}

.impact-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-bottom: 8px;
}

.impact-summary-item {
  padding: 7px 9px;
}

.impact-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
}

.analysis-empty {
  padding: 22px;
  color: #86909c;
  font-size: 13px;
}

.empty-state {
  min-height: 330px;
  color: #c9cdd4;
}

.impact-action-btn {
  min-width: 142px;
  font-weight: 800;
  box-shadow: 0 4px 12px rgba(22, 93, 255, 0.12);
}

.empty-img {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: #f0f5ff;
  color: #165dff;
  font-weight: 800;
  margin-bottom: 12px;
}

.animate-fade-in {
  animation: fadeIn 0.3s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
