// 模板账本（时间窗内按查询模板聚合的成本账）—— 与 backend/src/schemas/template.py 对齐

export type RunStatusKind = 'success' | 'failed'

export interface TemplateExecutionItem {
  id: number
  external_id: string
  executed_at: string
  window_start: string
  run_status: RunStatusKind
  is_billed: boolean
  duration_ms: number
  scan_bytes: number
  scan_cost_cny: number
  parse_status: string
  prunable: boolean
  blocked_reason: string
  hit_partition_count: number
  total_partition_count: number
  param_values: string[]
  param_fingerprint: string
  source: string
  submitted_by: string
  is_scheduled: boolean
  error_message: string | null
  query_log_id: number | null
}

export interface TemplateLedgerItem {
  template_code: string
  fingerprint: string
  window_start: string
  title: string
  target_table: string | null
  canonical_sql: string
  source: string
  submitted_by: string
  is_scheduled: boolean
  prunable: boolean
  blocked_reason: string
  // 三计数核对：execution_count = billed_count + duplicate_count + failed_count
  execution_count: number
  billed_count: number
  duplicate_count: number
  failed_count: number
  // 累计口径（仅 is_billed）
  billed_scan_bytes: number
  billed_cost_cny: number
  // 单次代表值（最近一次计入执行）
  single_scan_bytes: number
  single_cost_cny: number
  total_duration_ms: number
  coverage_pct: number
  first_executed_at: string
  last_executed_at: string
  sample_param_values: string[]
}

export interface TemplateLedgerStats {
  window_start: string | null
  template_count: number
  execution_count: number
  billed_count: number
  duplicate_count: number
  failed_count: number
  covered_count: number
  coverage_pct: number
  billed_scan_bytes: number
  billed_cost_cny: number
}

export interface TemplateLedgerPage {
  items: TemplateLedgerItem[]
  total: number
  page: number
  page_size: number
  windows: string[]
  stats: TemplateLedgerStats
}

export interface TemplateDetail {
  template_code: string
  fingerprint: string
  canonical_sql: string
  window_start: string
  title: string
  target_table: string | null
  execution_count: number
  billed_count: number
  duplicate_count: number
  failed_count: number
  billed_scan_bytes: number
  billed_cost_cny: number
  coverage_pct: number
  executions: TemplateExecutionItem[]
}

export interface TemplateFilters {
  page?: number
  page_size?: number
  sort?: 'billed_scan_bytes' | 'execution_count' | 'billed_cost_cny' | 'failed_count' | 'last_executed_at'
  order?: 'asc' | 'desc'
  window?: string
  table?: string
  status?: 'failed' | 'blocked' | 'prunable'
  keyword?: string
}
