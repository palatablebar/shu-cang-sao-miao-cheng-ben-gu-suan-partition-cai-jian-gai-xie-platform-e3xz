<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useTemplateStore } from '../stores/templateStore'
import BlueprintSheet from '../components/common/BlueprintSheet.vue'
import BlueprintPanel from '../components/common/BlueprintPanel.vue'
import EmptyState from '../components/common/EmptyState.vue'
import ErrorNotice from '../components/common/ErrorNotice.vue'
import MonoMetric from '../components/common/MonoMetric.vue'
import StatusStamp from '../components/common/StatusStamp.vue'
import { BLOCKED_REASON_SHORT, EXECUTION_STATUS_LABEL } from '../constants/enums'
import { MSG_EMPTY_QUERY } from '../constants/messages'
import { cny, dateLabel, durationLabel, gibLabel, intLabel, pct } from '../utils/format'
import type { TemplateFilters, TemplateLedgerItem } from '../types/template'

const router = useRouter()
const ledger = useTemplateStore()
const keyword = ref('')

const stats = computed(() => ledger.stats)
const maxScan = computed(() => Math.max(1, ...ledger.items.map((item) => item.billed_scan_bytes)))

function barWidth(bytes: number) {
  return `${Math.max(2, (bytes / maxScan.value) * 100)}%`
}

function rowKey(item: TemplateLedgerItem) {
  return `${item.window_start}::${item.fingerprint}`
}

function isOpen(item: TemplateLedgerItem) {
  return ledger.expandedKey === rowKey(item)
}

async function toggle(item: TemplateLedgerItem) {
  await ledger.openDetail(item)
}

function search() {
  ledger.setFilter('keyword', keyword.value.trim() || undefined)
  ledger.load()
}

function pickWindow(value: string) {
  ledger.setFilter('window', value || undefined)
  ledger.load()
}

function pickStatus(value: string) {
  ledger.setFilter('status', (value || undefined) as TemplateFilters['status'])
  ledger.load()
}

function pickSort(value: string) {
  ledger.setFilter('sort', (value || 'billed_scan_bytes') as TemplateFilters['sort'])
  ledger.load()
}

function goPage(next: number) {
  ledger.setFilter('page', next)
  ledger.load()
}

onMounted(() => ledger.load())
</script>

<template>
  <div class="page">
    <BlueprintSheet
      title="查询模板成本账（时间窗）"
      code="S-01B / TEMPLATE LEDGER"
      note="按小时窗口把结构与参数值相同的执行归并为一个查询模板；重复投递不重复计费，跨窗口不串账，失败执行单列并计入覆盖率。"
    >
      <!-- 窗口级汇总指标 -->
      <div class="metrics">
        <MonoMetric :value="intLabel(stats?.template_count ?? 0)" unit="个" caption="查询模板 / TEMPLATES" />
        <MonoMetric :value="intLabel(stats?.execution_count ?? 0)" unit="次" caption="执行总数 / EXECUTIONS" />
        <MonoMetric :value="intLabel(stats?.billed_count ?? 0)" unit="次" caption="计入计费 / BILLED" />
        <MonoMetric :value="gibLabel(stats?.billed_scan_bytes ?? 0, 1)" caption="累计扫描量 / BILLED SCAN" />
      </div>

      <!-- 覆盖率与三计数核对条 -->
      <div class="reconcile">
        <div class="reconcile-item">
          <span class="reconcile-label">覆盖率 COVERAGE</span>
          <span class="mono reconcile-value">{{ pct(stats?.coverage_pct ?? 0) }}</span>
          <span class="hint">（执行 {{ stats?.execution_count ?? 0 }} − 异常 {{ stats?.failed_count ?? 0 }}）/ 执行</span>
        </div>
        <div class="reconcile-item">
          <span class="reconcile-label">执行数 = 计入 + 重复 + 异常</span>
          <span class="mono reconcile-value">
            {{ stats?.execution_count ?? 0 }} = {{ stats?.billed_count ?? 0 }} +
            {{ stats?.duplicate_count ?? 0 }} + {{ stats?.failed_count ?? 0 }}
          </span>
        </div>
        <div class="reconcile-item">
          <span class="reconcile-label">窗口累计费用</span>
          <span class="mono reconcile-value">{{ cny(stats?.billed_cost_cny ?? 0, 3) }}</span>
          <span class="hint">重复投递已剔除</span>
        </div>
      </div>

      <div class="grid">
        <div class="left">
          <div class="toolbar">
            <select class="mini-select" :value="ledger.filters.window || ''" @change="pickWindow(($event.target as HTMLSelectElement).value)">
              <option value="">全部时间窗</option>
              <option v-for="w in ledger.windows" :key="w" :value="w">{{ w }}</option>
            </select>
            <select class="mini-select" :value="ledger.filters.status || ''" @change="pickStatus(($event.target as HTMLSelectElement).value)">
              <option value="">全部状态</option>
              <option value="blocked">裁剪失效</option>
              <option value="prunable">可裁剪</option>
              <option value="failed">失败执行</option>
            </select>
            <select class="mini-select" :value="ledger.filters.sort" @change="pickSort(($event.target as HTMLSelectElement).value)">
              <option value="billed_scan_bytes">按累计扫描量</option>
              <option value="execution_count">按执行次数</option>
              <option value="billed_cost_cny">按累计费用</option>
              <option value="failed_count">按异常数</option>
              <option value="last_executed_at">按最近执行</option>
            </select>
            <input
              v-model="keyword"
              class="mini-input"
              type="search"
              placeholder="搜索业务标题…"
              @keyup.enter="search"
            />
          </div>

          <ErrorNotice v-if="ledger.error" :message="ledger.error" @retry="ledger.load()" />

          <div v-else-if="!ledger.items.length && !ledger.loading">
            <EmptyState
              :title="MSG_EMPTY_QUERY"
              hint="当前时间窗没有执行流水。可切换时间窗，或在「查询成本排行」页重新导入演示数据。"
              action="重新加载"
              @action="ledger.load()"
            />
          </div>

          <table v-else class="grid-table">
            <thead>
              <tr>
                <th />
                <th>查询模板 / 时间窗</th>
                <th class="num">执行数</th>
                <th class="num">计入/重复/异常</th>
                <th class="num">累计扫描量</th>
                <th class="num">累计费用</th>
                <th class="num">单次费用</th>
                <th class="num">覆盖率</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="item in ledger.items" :key="rowKey(item)">
                <tr class="tpl-row" @click="toggle(item)">
                  <td class="caret">{{ isOpen(item) ? '▾' : '▸' }}</td>
                  <td>
                    <p class="title">
                      <span class="mono tpl-code">{{ item.template_code }}</span>
                      {{ item.title }}
                    </p>
                    <p class="meta">
                      <span class="mono">{{ item.target_table || '—' }}</span>
                      · 窗 <span class="mono">{{ item.window_start }}</span>
                      · {{ item.source }}<span v-if="item.is_scheduled"> · 调度</span>
                    </p>
                  </td>
                  <td class="num mono strong">{{ item.execution_count }}</td>
                  <td class="num mono">
                    <span class="cnt-billed">{{ item.billed_count }}</span> /
                    <span class="cnt-dup">{{ item.duplicate_count }}</span> /
                    <span class="cnt-fail" :class="{ active: item.failed_count > 0 }">{{ item.failed_count }}</span>
                  </td>
                  <td class="num">
                    <span class="mono scan">{{ gibLabel(item.billed_scan_bytes) }}</span>
                    <span class="bar"><i :style="{ width: barWidth(item.billed_scan_bytes) }" /></span>
                  </td>
                  <td class="num mono strong">{{ cny(item.billed_cost_cny, 3) }}</td>
                  <td class="num mono dim">{{ cny(item.single_cost_cny, 3) }}</td>
                  <td class="num">
                    <span class="mono" :class="{ 'cov-warn': item.coverage_pct < 100 }">{{ pct(item.coverage_pct, 0) }}</span>
                  </td>
                </tr>

                <!-- 展开区：模板信息 + 每次执行 -->
                <tr v-if="isOpen(item)" class="detail-row">
                  <td />
                  <td colspan="7" class="detail-cell">
                    <div v-if="ledger.detailLoading" class="hint">正在载入执行明细…</div>
                    <div v-else-if="ledger.detail && ledger.expandedKey === rowKey(item)">
                      <div class="detail-head">
                        <StatusStamp
                          :label="BLOCKED_REASON_SHORT[item.blocked_reason] || item.blocked_reason"
                          :level="item.prunable ? 'prunable' : 'blocked'"
                        />
                        <span class="tag">结构指纹 <span class="mono">{{ item.fingerprint }}</span></span>
                        <span class="tag">首跑 {{ dateLabel(item.first_executed_at) }}</span>
                        <span class="tag">末跑 {{ dateLabel(item.last_executed_at) }}</span>
                        <span class="tag">总耗时 {{ durationLabel(item.total_duration_ms) }}</span>
                      </div>

                      <pre class="canonical">{{ item.canonical_sql }}</pre>

                      <div v-if="item.sample_param_values.length" class="params">
                        <span class="hint">采样参数值：</span>
                        <code v-for="(p, i) in item.sample_param_values" :key="i" class="param-chip">{{ p }}</code>
                      </div>

                      <table class="exec-table">
                        <thead>
                          <tr>
                            <th>执行编号</th>
                            <th>执行时间</th>
                            <th>状态</th>
                            <th>计费</th>
                            <th class="num">扫描量</th>
                            <th class="num">单次费用</th>
                            <th class="num">命中分区</th>
                            <th>参数 / 异常</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="ex in ledger.detail.executions" :key="ex.id" :class="{ 'is-failed': ex.run_status === 'failed', 'is-dup': !ex.is_billed && ex.run_status !== 'failed' }">
                            <td class="mono">{{ ex.external_id }}</td>
                            <td class="mono">{{ dateLabel(ex.executed_at) }}</td>
                            <td>
                              <StatusStamp
                                :label="EXECUTION_STATUS_LABEL[ex.run_status] || ex.run_status"
                                :level="ex.run_status"
                              />
                            </td>
                            <td>
                              <span v-if="ex.is_billed" class="bill-ok">计入</span>
                              <span v-else-if="ex.run_status === 'failed'" class="bill-fail">不计（失败）</span>
                              <span v-else class="bill-dup">不计（重复投递）</span>
                            </td>
                            <td class="num mono">{{ gibLabel(ex.scan_bytes) }}</td>
                            <td class="num mono">{{ cny(ex.scan_cost_cny, 3) }}</td>
                            <td class="num mono">{{ ex.hit_partition_count }}/{{ ex.total_partition_count }}</td>
                            <td class="param-cell">
                              <code v-if="ex.param_values.length" class="param-chip">{{ ex.param_values.join(' · ') }}</code>
                              <span v-if="ex.error_message" class="err-text" :title="ex.error_message">{{ ex.error_message }}</span>
                            </td>
                            <td>
                              <button
                                v-if="ex.query_log_id"
                                class="btn btn--ghost btn--mini"
                                type="button"
                                @click.stop="router.push({ name: 'query-detail', params: { id: ex.query_log_id } })"
                              >
                                解析详情
                              </button>
                            </td>
                          </tr>
                        </tbody>
                        <tfoot>
                          <tr>
                            <td colspan="4">累计（仅计入执行）</td>
                            <td class="num mono strong">{{ gibLabel(ledger.detail.billed_scan_bytes) }}</td>
                            <td class="num mono strong">{{ cny(ledger.detail.billed_cost_cny, 3) }}</td>
                            <td colspan="3" />
                          </tr>
                        </tfoot>
                      </table>

                      <p class="hint reconcile-note">
                        核对：执行 {{ ledger.detail.execution_count }} = 计入 {{ ledger.detail.billed_count }}
                        + 重复 {{ ledger.detail.duplicate_count }} + 异常 {{ ledger.detail.failed_count }}
                        ；单次费用代表最近一次计入执行，累计费用为全部计入执行之和。
                      </p>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>

          <div v-if="ledger.total > (ledger.filters.page_size || 20)" class="pager">
            <button
              class="btn btn--ghost"
              type="button"
              :disabled="(ledger.filters.page || 1) <= 1"
              @click="goPage((ledger.filters.page || 1) - 1)"
            >
              上一页
            </button>
            <span class="mono hint">
              第 {{ ledger.filters.page }} 页 / 共 {{ Math.ceil(ledger.total / (ledger.filters.page_size || 20)) }} 页 ·
              {{ ledger.total }} 个模板窗
            </span>
            <button
              class="btn btn--ghost"
              type="button"
              :disabled="(ledger.filters.page || 1) * (ledger.filters.page_size || 20) >= ledger.total"
              @click="goPage((ledger.filters.page || 1) + 1)"
            >
              下一页
            </button>
          </div>
        </div>

        <aside class="right">
          <BlueprintPanel label="记账口径 / LEDGER RULES">
            <ul class="rules">
              <li>模板 = SQL 结构指纹，日期等字面量归一为占位符，调参不再拆成新查询。</li>
              <li>账本按小时窗聚合，同一模板跨窗口各自独立出账，不串账。</li>
              <li>同窗口同模板同参数的重复投递，仅首条计入，其余不重复计费。</li>
              <li>失败执行单列（异常数），扫描量计 0 但纳入覆盖率分母。</li>
            </ul>
          </BlueprintPanel>

          <BlueprintPanel label="三计数核对 / RECONCILE">
            <dl class="check-grid">
              <div><dt>执行数</dt><dd class="mono">{{ stats?.execution_count ?? 0 }}</dd></div>
              <div><dt>计入数</dt><dd class="mono cnt-billed">{{ stats?.billed_count ?? 0 }}</dd></div>
              <div><dt>重复投递</dt><dd class="mono cnt-dup">{{ stats?.duplicate_count ?? 0 }}</dd></div>
              <div><dt>异常数</dt><dd class="mono cnt-fail">{{ stats?.failed_count ?? 0 }}</dd></div>
              <div><dt>覆盖（非异常）</dt><dd class="mono">{{ stats?.covered_count ?? 0 }}</dd></div>
              <div><dt>覆盖率</dt><dd class="mono">{{ pct(stats?.coverage_pct ?? 0) }}</dd></div>
            </dl>
          </BlueprintPanel>

          <BlueprintPanel label="时间窗 / WINDOWS">
            <div class="window-list">
              <button class="btn btn--ghost btn--mini" :class="{ 'btn--primary': !ledger.filters.window }" type="button" @click="pickWindow('')">
                全部窗口
              </button>
              <button
                v-for="w in ledger.windows"
                :key="w"
                class="btn btn--ghost btn--mini window-btn"
                :class="{ 'btn--primary': ledger.filters.window === w }"
                type="button"
                @click="pickWindow(w)"
              >
                {{ w }}
              </button>
            </div>
            <div class="divider" />
            <button class="btn btn--ghost" type="button" @click="router.push({ name: 'queries' })">
              切回单条日志排行 →
            </button>
          </BlueprintPanel>
        </aside>
      </div>
    </BlueprintSheet>
  </div>
</template>

<style scoped>
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-5);
  padding: var(--space-3) 0 var(--space-4);
  border-bottom: 1px solid var(--rule);
  margin-bottom: var(--space-3);
}
.reconcile {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px dashed var(--rule);
  margin-bottom: var(--space-4);
  background: oklch(0.24 0.045 254 / 0.55);
}
.reconcile-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.reconcile-label {
  font-family: var(--font-mono);
  font-size: 0.64rem;
  letter-spacing: 0.08em;
  color: var(--cream-mute);
}
.reconcile-value {
  font-size: var(--step-0);
  color: var(--cream);
}
.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(280px, 1fr);
  gap: var(--space-5);
}
.left {
  min-width: 0;
}
.toolbar {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}
.mini-select,
.mini-input {
  background: oklch(0.225 0.045 254 / 0.9);
  border: 1px solid var(--rule);
  padding: 6px 9px;
  font-family: var(--font-mono);
  font-size: var(--step--1);
}
.mini-input {
  width: 170px;
}
.caret {
  color: var(--rust);
  font-family: var(--font-mono);
  width: 20px;
}
.tpl-row {
  cursor: pointer;
}
.tpl-code {
  color: var(--rust);
  font-size: 0.7rem;
  margin-right: 6px;
}
.title {
  margin: 0;
  font-size: var(--step-0);
}
.meta {
  margin: 3px 0 0;
  font-size: 0.68rem;
  color: var(--cream-mute);
}
.scan {
  display: block;
}
.bar {
  display: block;
  height: 4px;
  background: oklch(0.42 0.04 250 / 0.45);
  margin-top: 4px;
  width: 92px;
  margin-left: auto;
}
.bar i {
  display: block;
  height: 100%;
  background: var(--sand);
}
.strong {
  color: var(--cream);
}
.dim {
  color: var(--cream-mute);
}
.cnt-billed {
  color: var(--cream);
}
.cnt-dup {
  color: var(--sand);
}
.cnt-fail {
  color: var(--cream-mute);
}
.cnt-fail.active {
  color: oklch(0.68 0.16 28);
}
.cov-warn {
  color: oklch(0.72 0.14 60);
}
.detail-row {
  cursor: default;
}
.detail-cell {
  background: oklch(0.2 0.045 254 / 0.85);
  padding: var(--space-4) !important;
}
.detail-head {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: var(--space-3);
}
.canonical {
  margin: 0 0 var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--rule);
  background: oklch(0.18 0.04 255 / 0.9);
  font-family: var(--font-mono);
  font-size: 0.72rem;
  line-height: 1.6;
  color: var(--cream-dim);
  overflow-x: auto;
  white-space: pre-wrap;
}
.params {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: var(--space-3);
}
.param-chip {
  font-family: var(--font-mono);
  font-size: 0.66rem;
  padding: 2px 7px;
  border: 1px solid var(--rule);
  background: oklch(0.26 0.05 253 / 0.8);
  color: var(--cream-dim);
}
.exec-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.72rem;
}
.exec-table th,
.exec-table td {
  border-bottom: 1px solid var(--rule);
  padding: 7px 8px;
  text-align: left;
  vertical-align: top;
}
.exec-table tfoot td {
  border-top: 2px solid var(--rule);
  border-bottom: none;
  color: var(--cream-mute);
}
.exec-table tr.is-dup {
  opacity: 0.72;
}
.exec-table tr.is-failed {
  background: oklch(0.3 0.08 28 / 0.28);
}
.bill-ok {
  color: oklch(0.72 0.13 150);
  font-family: var(--font-mono);
  font-size: 0.68rem;
}
.bill-dup {
  color: var(--sand);
  font-family: var(--font-mono);
  font-size: 0.68rem;
}
.bill-fail {
  color: oklch(0.68 0.16 28);
  font-family: var(--font-mono);
  font-size: 0.68rem;
}
.param-cell {
  max-width: 260px;
}
.err-text {
  display: block;
  margin-top: 4px;
  color: oklch(0.7 0.15 28);
  font-size: 0.66rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.reconcile-note {
  margin: var(--space-3) 0 0;
}
.btn--mini {
  padding: 3px 9px;
  font-size: 0.66rem;
}
.pager {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  justify-content: space-between;
  margin-top: var(--space-3);
}
.rules {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 0.72rem;
  line-height: 1.55;
  color: var(--cream-dim);
}
.check-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 12px;
  margin: 0;
}
.check-grid div {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  border-bottom: 1px dashed var(--rule);
  padding-bottom: 3px;
}
.check-grid dt {
  font-size: 0.66rem;
  color: var(--cream-mute);
}
.check-grid dd {
  margin: 0;
  font-size: 0.72rem;
}
.window-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: stretch;
}
.window-btn {
  text-align: left;
  justify-content: flex-start;
}
@media (max-width: 1180px) {
  .grid {
    grid-template-columns: 1fr;
  }
  .metrics,
  .reconcile {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
