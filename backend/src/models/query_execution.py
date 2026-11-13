"""QueryExecution — 一次查询执行的计费流水（模板账本的最小记账单元）。

与 ``QueryLog``（一条被解析的查询日志 + 算法 1 结果）的关系
-----------------------------------------------------------
* ``QueryLog`` 是「这条 SQL 长什么样、扫多少」的静态画像；
* ``QueryExecution`` 是「它在哪个时间窗、第几次跑、是否计费成功」的动态流水。
  同一个模板（fingerprint）在一个小时窗内可以有多条执行。

记账口径
--------
* ``window_start`` 按小时分桶，模板账严格在窗口内聚合 —— 跨窗口不串账。
* 重复投递：同窗口 + 同模板 + 同参数值（param_fingerprint）的执行，
  只有第一条成功执行 ``is_billed=True``，其余 ``is_billed=False`` 且不重复计费。
* 失败执行（run_status=failed）单列，``is_billed=False``、扫描量计 0，
  但仍计入模板的执行总数与覆盖率分母。
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class QueryExecution(Base, TimestampMixin):
    __tablename__ = "query_execution"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_query_execution_external_id"),
        Index("ix_qe_window_fingerprint", "window_start", "fingerprint"),
        Index("ix_qe_query_log_id", "query_log_id"),
        Index("ix_qe_run_status", "run_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(40), nullable=False)

    # --- 时间窗（小时桶）与模板身份 ---
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_start: Mapped[str] = mapped_column(String(16), nullable=False)  # 'YYYY-MM-DD HH:00'
    fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_sql: Mapped[str] = mapped_column(Text, nullable=False)
    param_fingerprint: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    param_values: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sql_normalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- 执行画像（冗余自 QueryLog，保证账本查询不回表也能出账） ---
    query_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("query_log.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(48), nullable=False, default="adhoc")
    submitted_by: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    target_table: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    is_scheduled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- 运行状态：success / failed（失败单列、计入覆盖率） ---
    run_status: Mapped[str] = mapped_column(String(16), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- 计费口径 ---
    is_billed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    scan_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    scan_cost_cny: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    parse_status: Mapped[str] = mapped_column(String(24), nullable=False, default="parsed")
    prunable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocked_reason: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    hit_partition_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_partition_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    query = relationship("QueryLog", back_populates="executions")
