import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchTemplateDetail, fetchTemplateLedger } from '../api/templates'
import type {
  TemplateDetail,
  TemplateFilters,
  TemplateLedgerItem,
  TemplateLedgerPage,
  TemplateLedgerStats,
} from '../types/template'

/**
 * 模板账本 store：按时间窗聚合的查询模板排行 + 展开后的执行明细。
 * 与单条日志排行（queryStore）相互独立，口径见 backend template_service。
 */
export const useTemplateStore = defineStore('query-templates', () => {
  const items = ref<TemplateLedgerItem[]>([])
  const total = ref(0)
  const windows = ref<string[]>([])
  const stats = ref<TemplateLedgerStats | null>(null)
  const detail = ref<TemplateDetail | null>(null)
  const loading = ref(false)
  const detailLoading = ref(false)
  const error = ref('')
  const filters = ref<TemplateFilters>({
    page: 1,
    page_size: 20,
    sort: 'billed_scan_bytes',
    order: 'desc',
  })
  // 当前展开的模板行 key = `${window_start}::${fingerprint}`
  const expandedKey = ref<string | null>(null)

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const page: TemplateLedgerPage = await fetchTemplateLedger(filters.value)
      items.value = page.items
      total.value = page.total
      windows.value = page.windows
      stats.value = page.stats
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function openDetail(item: TemplateLedgerItem) {
    const key = `${item.window_start}::${item.fingerprint}`
    if (expandedKey.value === key) {
      expandedKey.value = null
      detail.value = null
      return
    }
    expandedKey.value = key
    detailLoading.value = true
    error.value = ''
    try {
      detail.value = await fetchTemplateDetail(item.fingerprint, item.window_start)
    } catch (err) {
      error.value = (err as Error).message
      expandedKey.value = null
      detail.value = null
    } finally {
      detailLoading.value = false
    }
  }

  function setFilter<K extends keyof TemplateFilters>(key: K, value: TemplateFilters[K]) {
    filters.value = { ...filters.value, [key]: value, page: key === 'page' ? (value as number) : 1 }
  }

  return {
    items,
    total,
    windows,
    stats,
    detail,
    loading,
    detailLoading,
    error,
    filters,
    expandedKey,
    load,
    openDetail,
    setFilter,
  }
})
