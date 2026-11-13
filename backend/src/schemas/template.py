"""模板账本 schemas — 时间窗内按模板聚合的查询成本账。

计数恒等式（前端可逐项核对）::

    execution_count = billed_count + duplicate_count + failed_count
    coverage_pct   = (execution_count − failed_count) / execution_count × 100
    累计费用        = Σ 计入执行（is_billed=True）的单次费用，重复投递不重复计费
"""
from pydantic import BaseModel


class TemplateExecutionItem(BaseModel):
    """模板下的一次执行（可展开行）。"""

    id: int
    external_id: str
    executed_at: str
    window_start: str
    run_status: str                 # success / failed
    is_billed: bool
    duration_ms: int
    scan_bytes: int
    scan_cost_cny: float
    parse_status: str
    prunable: bool
    blocked_reason: str
    hit_partition_count: int
    total_partition_count: int
    param_values: list[str]
    param_fingerprint: str
    source: str
    submitted_by: str
    is_scheduled: bool
    error_message: str | None
    query_log_id: int | None


class TemplateLedgerItem(BaseModel):
    """一个时间窗内的一个查询模板（账本主行）。"""

    template_code: str              # TPL-<fingerprint>
    fingerprint: str
    window_start: str
    title: str
    target_table: str | None
    canonical_sql: str
    source: str
    submitted_by: str
    is_scheduled: bool
    prunable: bool
    blocked_reason: str

    # --- 三计数核对 ---
    execution_count: int            # 执行数（窗口内全部执行，含重复/失败）
    billed_count: int               # 计入数（实际计费的成功执行）
    duplicate_count: int            # 重复投递数（同参数、不重复计费）
    failed_count: int               # 异常数（失败执行，单列、计入覆盖率）

    # --- 费用与扫描量（累计口径，只统计 is_billed） ---
    billed_scan_bytes: int          # 累计扫描量（计入执行求和）
    billed_cost_cny: float          # 累计费用
    single_scan_bytes: int          # 单次扫描量（代表值：最近一次计入执行）
    single_cost_cny: float          # 单次费用
    total_duration_ms: int
    coverage_pct: float             # 覆盖率 = 非失败执行 / 全部执行

    first_executed_at: str
    last_executed_at: str
    sample_param_values: list[str]


class TemplateLedgerStats(BaseModel):
    window_start: str | None
    template_count: int             # 窗口内模板数
    execution_count: int            # 执行总数
    billed_count: int               # 计入总数
    duplicate_count: int            # 重复投递总数
    failed_count: int               # 失败总数
    covered_count: int              # 非失败执行数（覆盖率分子）
    coverage_pct: float
    billed_scan_bytes: int          # 窗口累计扫描量
    billed_cost_cny: float          # 窗口累计费用


class TemplateLedgerPage(BaseModel):
    items: list[TemplateLedgerItem]
    total: int
    page: int
    page_size: int
    windows: list[str]              # 可选时间窗（有数据的小时桶，倒序）
    stats: TemplateLedgerStats


class TemplateDetail(BaseModel):
    template_code: str
    fingerprint: str
    canonical_sql: str
    window_start: str
    title: str
    target_table: str | None
    execution_count: int
    billed_count: int
    duplicate_count: int
    failed_count: int
    billed_scan_bytes: int
    billed_cost_cny: float
    coverage_pct: float
    executions: list[TemplateExecutionItem]
