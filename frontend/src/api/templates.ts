import { apiGet } from './http'
import type { TemplateDetail, TemplateFilters, TemplateLedgerPage } from '../types/template'

export function fetchTemplateLedger(filters: TemplateFilters) {
  return apiGet<TemplateLedgerPage>('/query-templates', filters as Record<string, unknown>)
}

export function fetchTemplateDetail(fingerprint: string, window: string) {
  return apiGet<TemplateDetail>(`/query-templates/${fingerprint}/detail`, { window })
}
