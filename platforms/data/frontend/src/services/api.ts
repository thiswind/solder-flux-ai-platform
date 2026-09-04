import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.BASE_URL + 'api/v1',
  timeout: 120000,
})

// SSO：后端 API 返回 401（未登录/令牌失效）时，跳回统一门户登录并携带回跳地址
const PORTAL_LOGIN = '/yunxi/'
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response && error.response.status === 401) {
      const redirect = encodeURIComponent(window.location.origin + window.location.pathname)
      window.location.href = PORTAL_LOGIN + '?redirect=' + redirect
    }
    return Promise.reject(error)
  }
)

export interface DashboardOverview {
  app_name: string
  latest_run: RunSummary | null
  dataset_counts: Array<{ dataset_name: string; row_count: number }>
  review_issue_count: number
  source_file_count: number
  metric_cards: Record<string, number>
  excel_breakdown: Record<string, Record<string, number>>
  image_breakdown: Record<string, number>
  image_match_breakdown: Record<string, number>
}

export interface RunSummary {
  id: number
  status: string
  include_images: boolean
  current_step?: string
  progress_percent: number
  started_at: string
  completed_at?: string | null
  message?: string | null
  summary: Record<string, any>
}

export interface PipelineRunPayload {
  include_images: boolean
  include_auto_grade: boolean
  trigger_source: string
}

export interface UploadedFileRecord {
  dataset_type: string
  file_name: string
  absolute_path: string
  relative_path: string
  file_size: number
  modified_time: string
}

export interface ArtifactInfo {
  artifact_name: string
  artifact_type: string
  artifact_path: string
  exists: boolean
}

export interface SourceFileRow {
  id: number
  source_type: string
  relative_path: string
  file_name: string
  file_size: number
  modified_time: string
  file_hash: string
}

export async function fetchDashboardOverview() {
  const { data } = await api.get<DashboardOverview>('/dashboard/overview')
  return data
}

export async function fetchRuns() {
  const { data } = await api.get<RunSummary[]>('/dashboard/runs')
  return data
}

export async function runPipeline(payload: PipelineRunPayload) {
  const { data } = await api.post('/pipeline/run', payload)
  return data
}

export async function fetchDatasets(runId?: number) {
  const { data } = await api.get('/pipeline/datasets', {
    params: runId ? { run_id: runId } : undefined,
  })
  return data
}

export interface DatasetRowsResponse<T = Record<string, any>> {
  run_id?: number
  dataset_name: string
  total: number
  page: number
  page_size: number
  rows: T[]
}

export async function fetchDatasetRows<T = Record<string, any>>(datasetName: string, params: Record<string, unknown>) {
  const { data } = await api.get<DatasetRowsResponse<T>>(`/pipeline/datasets/${datasetName}`, { params })
  return data
}

export async function fetchReviewIssues(runId?: number) {
  const { data } = await api.get('/pipeline/review-issues', {
    params: runId ? { run_id: runId } : undefined,
  })
  return data
}

export async function fetchSourceGraph(keyword = '') {
  const { data } = await api.get('/pipeline/source-graph', {
    params: keyword ? { keyword } : undefined,
  })
  return data
}

export async function fetchSourceFiles(page = 1, pageSize = 20) {
  const { data } = await api.get<{ total: number; page: number; page_size: number; rows: SourceFileRow[] }>('/pipeline/source-files', {
    params: { page, page_size: pageSize },
  })
  return data
}

export async function uploadSourceFiles(
  datasetType: 'overall' | 'specific' | 'image',
  files: File[],
  onProgress?: (done: number, total: number) => void,
) {
  // 顺序 + 小批次上传：图片平均 ~17MB、单批不宜过大；后端是单进程 uvicorn，
  // 并发多批会把整批数据同时压进服务端内存（3 批×300张×17MB≈15GB）拖垮事件循环、
  // 实测会让上传接口 status=000 无响应。故改为并发 1、小批次，保证单 worker 内存可控、
  // 上传能稳稳走完（157GB 数据本身仍需数分钟，这是物理下限，非代码瓶颈）。
  const BATCH_SIZE = 30
  const CONCURRENCY = 1 // 顺序上传，避免单进程后端内存被打爆
  const total = files.length
  let done = 0
  let nextIndex = 0
  const allSaved: any[] = []
  const allSkipped: any[] = []
  const errors: any[] = []

  const batches: File[][] = []
  for (let i = 0; i < files.length; i += BATCH_SIZE) {
    batches.push(files.slice(i, i + BATCH_SIZE))
  }

  async function uploadBatch(batch: File[]) {
    const formData = new FormData()
    batch.forEach((file) => {
      formData.append('files', file)
      formData.append('relative_paths', file.webkitRelativePath || file.name)
    })
    const { data } = await api.post('/pipeline/upload-files', formData, {
      params: { dataset_type: datasetType },
      timeout: 1200000, // 单批仍可能较大，给 20 分钟超时
    })
    if (data && Array.isArray(data.saved_files)) allSaved.push(...data.saved_files)
    if (data && Array.isArray(data.skipped)) allSkipped.push(...data.skipped)
    done += batch.length
    if (onProgress) onProgress(done, total)
  }

  // 并发池：每次最多 CONCURRENCY 个批次同时在传
  const worker = async () => {
    while (nextIndex < batches.length) {
      const cur = nextIndex++
      try {
        await uploadBatch(batches[cur])
      } catch (err) {
        errors.push(err)
      }
    }
  }
  const poolSize = Math.min(CONCURRENCY, batches.length)
  await Promise.all(Array.from({ length: poolSize }, () => worker()))

  if (errors.length) {
    // 已成功的批次文件已落盘，抛出首个错误让页面提示失败
    throw errors[0]
  }
  return { saved_files: allSaved, uploaded_count: allSaved.length, skipped: allSkipped }
}

export async function fetchUploadedFiles() {
  const { data } = await api.get<{ rows: UploadedFileRecord[] }>('/pipeline/uploaded-files')
  return data
}

export async function fetchRunReadiness() {
  const { data } = await api.get<{
    has_files: boolean
    file_count: number
    source_changed: boolean
    last_run_at: string | null
  }>('/pipeline/run-readiness')
  return data
}

export async function clearAllUploads() {
  const { data } = await api.delete<{
    success: boolean
    message: string
    deleted_files: number
    failed_files: number
    deleted_db_records: Record<string, number>
  }>('/pipeline/clear-uploads')
  return data
}

export async function fetchLatestDeliveryArtifact() {
  const { data } = await api.get<ArtifactInfo>('/pipeline/artifacts/latest-delivery')
  return data
}

export async function deleteRun(runId: number) {
  const { data } = await api.delete<{ success: boolean; message: string }>(`/pipeline/runs/${runId}`)
  return data
}

export async function exportRuns(): Promise<Blob> {
  const { data } = await api.get('/pipeline/runs/export', { responseType: 'blob' })
  return data
}

export async function clearAllRuns() {
  const { data } = await api.delete<{ success: boolean; message: string }>('/pipeline/runs')
  return data
}

export function getLatestDeliveryDownloadUrl() {
  return import.meta.env.BASE_URL + 'api/v1/pipeline/artifacts/latest-delivery/download'
}

export default api
