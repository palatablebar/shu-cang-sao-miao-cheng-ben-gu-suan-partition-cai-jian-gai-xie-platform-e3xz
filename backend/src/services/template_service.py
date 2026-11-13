"""模板账本服务：按时间窗把结构相同的执行归并为查询模板并出账。

聚合口径（与需求逐条对齐）
==========================
1. 模板身份 = ``fingerprint``（SQL 归一化后的结构指纹，参数值变化不改变指纹）。
2. 账本严格在单个时间窗（小时桶 ``window_start``）内聚合，**跨窗口不串账**；
   不传窗口时汇总全部窗口，每行仍标注其所属窗口。
3. 排序按「执行次数」与「累计扫描量」两个维度，默认累计扫描量倒序。
4. 重复投递：``is_billed=False`` 的执行计入 execution_count、计入 duplicate_count，
   但不进 billed_scan_bytes / billed_cost —— **不重复计费**。
5. 失败执行：``run_status='failed'`` 单列（failed_count），扫描量与费用为 0，
   仍计入 execution_count —— **纳入覆盖率**。

计数恒等式::

    execution_count = billed_count + duplicate_count + failed_count
    coverage_pct    = (execution_count - failed_count) / execution_count * 100
"""
from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from src.analysis.template import template_code
from src.constants.error_codes import AppError, ErrorCode
from src.models import QueryExecution
from src.schemas.template import (
    TemplateDetail,
    TemplateExecutionItem,
    TemplateLedgerItem,
    TemplateLedgerPage,
    TemplateLedgerStats,
)
from src.utils.pagination import PageParams

SORT_FIELDS = {
    "billed_scan_bytes": "billed_scan_bytes",
    "execution_count": "execution_count",
    "billed_cost_cny": "billed_cost_cny",
    "failed_count": "failed_count",
    "last_executed_at": "last_executed_at",
}

# 聚合表达式（只对 is_billed=True 的执行求和 → 重复投递不重复计费）
_BILLED = func.coalesce(
    func.sum(case((QueryExecution.is_billed.is_(True), QueryExecution.scan_bytes), else_=0)), 0
)
_BILLED_COST = func.coalesce(
    func.sum(case((QueryExecution.is_billed.is_(True), QueryExecution.scan_cost_cny), else_=0)), 0.0
)
# 异常 / 计入 / 重复 三个计数（重复 = 不计费且非失败）
_FAILURE = func.sum(case((QueryExecution.run_status == "failed", 1), else_=0))
_BILLED_CNT = func.sum(case((QueryExecution.is_billed.is_(True), 1), else_=0))
_DUP_CNT = func.sum(
    case(
        (QueryExecution.is_billed.is_(False) & (QueryExecution.run_status != "failed"), 1),
        else_=0,
    )
)


def _filter_conditions(*, window: str | None, table: str | None, status: str | None,
                       keyword: str | None, fingerprint: str | None) -> list:
    """所有过滤都作用在 query_execution 基表列上，主查询与计数查询共用，保证口径一致。"""
    conditions = []
    if window:
        conditions.append(QueryExecution.window_start == window)
    if fingerprint:
        conditions.append(QueryExecution.fingerprint == fingerprint)
    if table:
        conditions.append(QueryExecution.target_table == table)
    if keyword:
        conditions.append(QueryExecution.title.ilike(f"%{keyword}%"))
    if status == "failed":
        conditions.append(QueryExecution.run_status == "failed")
    elif status == "blocked":
        conditions.append(QueryExecution.prunable.is_(False))
        conditions.append(QueryExecution.run_status != "failed")
    elif status == "prunable":
        conditions.append(QueryExecution.prunable.is_(True))
    return conditions


def _apply_conditions(stmt, conditions):
    for cond in conditions:
        stmt = stmt.where(cond)
    return stmt


def _group_columns():
    return [
        QueryExecution.fingerprint,
        QueryExecution.window_start,
        func.max(QueryExecution.canonical_sql).label("canonical_sql"),
        func.max(QueryExecution.title).label("title"),
        func.max(QueryExecution.target_table).label("target_table"),
        func.max(QueryExecution.source).label("source"),
        func.max(QueryExecution.submitted_by).label("submitted_by"),
        func.max(QueryExecution.is_scheduled).label("is_scheduled"),
        func.count(QueryExecution.id).label("execution_count"),
        _BILLED_CNT.label("billed_count"),
        _DUP_CNT.label("duplicate_count"),
        _FAILURE.label("failed_count"),
        _BILLED.label("billed_scan_bytes"),
        _BILLED_COST.label("billed_cost_cny"),
        func.coalesce(func.sum(QueryExecution.duration_ms), 0).label("total_duration_ms"),
        func.min(QueryExecution.executed_at).label("first_executed_at"),
        func.max(QueryExecution.executed_at).label("last_executed_at"),
    ]


def list_windows(db: Session) -> list[str]:
    rows = db.scalars(
        select(QueryExecution.window_start)
        .distinct()
        .order_by(QueryExecution.window_start.desc())
    )
    return list(rows)


def _coverage(exec_count: int, failed: int) -> float:
    if exec_count <= 0:
        return 0.0
    return round((exec_count - failed) / exec_count * 100.0, 2)


def ledger(
    db: Session,
    params: PageParams,
    sort: str = "billed_scan_bytes",
    order: str = "desc",
    window: str | None = None,
    table: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
) -> TemplateLedgerPage:
    conditions = _filter_conditions(
        window=window, table=table, status=status, keyword=keyword, fingerprint=None
    )
    group = _group_columns()
    stmt = select(*group).group_by(QueryExecution.fingerprint, QueryExecution.window_start)
    stmt = _apply_conditions(stmt, conditions)

    # 计数：先在基表上过滤，再对 (fingerprint, window_start) 去重计数，口径与主查询完全一致
    filtered = _apply_conditions(select(QueryExecution), conditions).subquery()
    count_stmt = select(func.count()).select_from(
        select(filtered.c.fingerprint, filtered.c.window_start)
        .group_by(filtered.c.fingerprint, filtered.c.window_start)
        .subquery()
    )

    sort_key = SORT_FIELDS.get(sort, "billed_scan_bytes")
    direction = "asc" if order == "asc" else "desc"
    # 聚合查询中可直接用 .label() 产生的列名做排序（PostgreSQL 支持 ORDER BY 输出别名）
    stmt = stmt.order_by(_order_clause(sort_key, direction), QueryExecution.fingerprint.asc())

    total = int(db.scalar(count_stmt) or 0)
    rows = db.execute(stmt.offset(params.offset).limit(params.limit)).mappings().all()

    # 每个模板取代表执行（最近一次计入；若无计入则最近一次执行）作为单次费用/判据来源，并采样参数值
    items: list[TemplateLedgerItem] = []
    for row in rows:
        rep = _representative(db, row.fingerprint, row.window_start)
        sample_params = _sample_params(db, row.fingerprint, row.window_start)
        items.append(
            TemplateLedgerItem(
                template_code=template_code(row.fingerprint),
                fingerprint=row.fingerprint,
                window_start=row.window_start,
                title=row.title or "(未命名模板)",
                target_table=row.target_table,
                canonical_sql=row.canonical_sql,
                source=row.source,
                submitted_by=row.submitted_by,
                is_scheduled=bool(row.is_scheduled),
                prunable=bool(rep.prunable) if rep else False,
                blocked_reason=(rep.blocked_reason if rep else "none") or "none",
                execution_count=int(row.execution_count),
                billed_count=int(row.billed_count),
                duplicate_count=int(row.duplicate_count),
                failed_count=int(row.failed_count),
                billed_scan_bytes=int(row.billed_scan_bytes),
                billed_cost_cny=round(float(row.billed_cost_cny), 6),
                single_scan_bytes=int(rep.scan_bytes if rep and rep.is_billed else 0),
                single_cost_cny=float(rep.scan_cost_cny if rep and rep.is_billed else 0.0),
                total_duration_ms=int(row.total_duration_ms),
                coverage_pct=_coverage(int(row.execution_count), int(row.failed_count)),
                first_executed_at=row.first_executed_at.isoformat() if row.first_executed_at else "",
                last_executed_at=row.last_executed_at.isoformat() if row.last_executed_at else "",
                sample_param_values=sample_params,
            )
        )

    stats = ledger_stats(db, window)
    return TemplateLedgerPage(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        windows=list_windows(db),
        stats=stats,
    )


def _order_clause(sort_key: str, direction: str):
    """对聚合标签做排序（标签在 group_by 查询中可直接引用）。"""
    from sqlalchemy import text

    return text(f"{sort_key} {direction} NULLS LAST")


def _representative(db: Session, fingerprint: str, window: str) -> QueryExecution | None:
    """模板代表执行：优先最近一次计入执行（提供单次费用/判据）；该窗全为失败时退回最近一次执行。"""
    billed = db.scalar(
        select(QueryExecution)
        .where(
            QueryExecution.fingerprint == fingerprint,
            QueryExecution.window_start == window,
            QueryExecution.is_billed.is_(True),
        )
        .order_by(QueryExecution.executed_at.desc(), QueryExecution.id.desc())
        .limit(1)
    )
    if billed is not None:
        return billed
    return db.scalar(
        select(QueryExecution)
        .where(QueryExecution.fingerprint == fingerprint, QueryExecution.window_start == window)
        .order_by(QueryExecution.executed_at.desc(), QueryExecution.id.desc())
        .limit(1)
    )


def _sample_params(db: Session, fingerprint: str, window: str, limit: int = 6) -> list[str]:
    rows = db.scalars(
        select(QueryExecution.param_values)
        .where(QueryExecution.fingerprint == fingerprint, QueryExecution.window_start == window)
        .order_by(QueryExecution.executed_at.desc())
        .limit(limit)
    )
    seen: set[str] = set()
    out: list[str] = []
    for vals in rows:
        for value in vals or []:
            if value not in seen:
                seen.add(value)
                out.append(value)
    return out[:limit]


def ledger_stats(db: Session, window: str | None) -> TemplateLedgerStats:
    stmt = select(
        func.count(func.distinct(QueryExecution.fingerprint, QueryExecution.window_start)),
        func.count(QueryExecution.id),
        _BILLED_CNT,
        _DUP_CNT,
        _FAILURE,
        _BILLED,
        _BILLED_COST,
    )
    if window:
        stmt = stmt.where(QueryExecution.window_start == window)
    row = db.execute(stmt).one()
    (template_count, exec_count, billed, dup, failed, scan, cost) = row
    exec_count = int(exec_count or 0)
    failed = int(failed or 0)
    return TemplateLedgerStats(
        window_start=window,
        template_count=int(template_count or 0),
        execution_count=exec_count,
        billed_count=int(billed or 0),
        duplicate_count=int(dup or 0),
        failed_count=failed,
        covered_count=exec_count - failed,
        coverage_pct=_coverage(exec_count, failed),
        billed_scan_bytes=int(scan or 0),
        billed_cost_cny=round(float(cost or 0.0), 6),
    )


def _execution_item(row: QueryExecution) -> TemplateExecutionItem:
    return TemplateExecutionItem(
        id=row.id,
        external_id=row.external_id,
        executed_at=row.executed_at.isoformat() if row.executed_at else "",
        window_start=row.window_start,
        run_status=row.run_status,
        is_billed=row.is_billed,
        duration_ms=row.duration_ms,
        scan_bytes=row.scan_bytes,
        scan_cost_cny=row.scan_cost_cny,
        parse_status=row.parse_status,
        prunable=row.prunable,
        blocked_reason=row.blocked_reason,
        hit_partition_count=row.hit_partition_count,
        total_partition_count=row.total_partition_count,
        param_values=list(row.param_values or []),
        param_fingerprint=row.param_fingerprint,
        source=row.source,
        submitted_by=row.submitted_by,
        is_scheduled=row.is_scheduled,
        error_message=row.error_message,
        query_log_id=row.query_log_id,
    )


def template_detail(db: Session, fingerprint: str, window: str) -> TemplateDetail:
    rows = list(
        db.scalars(
            select(QueryExecution)
            .where(QueryExecution.fingerprint == fingerprint, QueryExecution.window_start == window)
            .order_by(QueryExecution.executed_at.asc(), QueryExecution.id.asc())
        )
    )
    if not rows:
        raise AppError(ErrorCode.NOT_FOUND, "该时间窗内没有匹配的查询模板")
    billed = [r for r in rows if r.is_billed]
    failed = [r for r in rows if r.run_status == "failed"]
    dup = [r for r in rows if not r.is_billed and r.run_status != "failed"]
    first = rows[0]
    return TemplateDetail(
        template_code=template_code(fingerprint),
        fingerprint=fingerprint,
        canonical_sql=first.canonical_sql,
        window_start=window,
        title=first.title or "(未命名模板)",
        target_table=first.target_table,
        execution_count=len(rows),
        billed_count=len(billed),
        duplicate_count=len(dup),
        failed_count=len(failed),
        billed_scan_bytes=int(sum(r.scan_bytes for r in billed)),
        billed_cost_cny=round(sum(r.scan_cost_cny for r in billed), 6),
        coverage_pct=_coverage(len(rows), len(failed)),
        executions=[_execution_item(r) for r in rows],
    )
