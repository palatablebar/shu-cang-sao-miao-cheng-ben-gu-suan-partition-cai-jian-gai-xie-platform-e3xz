"""QueryExecution 入库服务：把执行事件落成计费流水。

职责
====
1. 对每条执行 SQL 做模板归一化（``analysis.template.normalize_sql``），
   得到 fingerprint / canonical_sql / 参数值。
2. 对成功执行跑算法 1（analyze_query），写入扫描量与裁剪判据；
   失败执行（engine 报错 / 解析失败 / 缺表）扫描量强制为 0 且不计费。
3. 重复投递判定：同窗口 + 同模板 + 同参数值（dedupe_key）的第一条成功执行计费，
   后续执行 ``is_billed=False`` —— 不重复计费；跨窗口 dedupe_key 不同，天然不串账。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.analysis.sql_analyzer import analyze_query
from src.analysis.template import hour_window, normalize_sql
from src.config.settings import settings
from src.models import QueryExecution, QueryLog
from src.services import table_service


def _parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _dedupe_key(window: str, fingerprint: str, param_fingerprint: str) -> str:
    return f"{window}|{fingerprint}|{param_fingerprint}"


def sync_executions(db: Session, events: list[dict]) -> dict:
    """幂等同步执行事件（自然键 external_id=event_no），返回计数汇总。"""
    catalog = table_service.build_catalog(db)
    # 已计费键：保证重复运行 seed 时去重判定稳定（不依赖本次事件的顺序之外的状态）
    billed_keys = set(
        db.scalars(
            select(QueryExecution.dedupe_key).where(
                QueryExecution.is_billed.is_(True), QueryExecution.dedupe_key != ""
            )
        )
    )
    created = duplicate = failed = billed = 0

    for event in events:
        existing = db.scalar(
            select(QueryExecution).where(QueryExecution.external_id == event["event_no"])
        )
        if existing is not None:
            continue  # 幂等：已存在的执行不重算、不覆盖

        tpl = normalize_sql(event["sql_text"])
        ts = _parse_ts(event["executed_at"])
        window = hour_window(event["executed_at"])
        is_failed = event["run_status"] == "failed"
        dkey = _dedupe_key(window, tpl["fingerprint"], tpl["param_fingerprint"])

        execution = QueryExecution(
            external_id=event["event_no"],
            executed_at=ts,
            window_start=window,
            fingerprint=tpl["fingerprint"],
            canonical_sql=tpl["canonical_sql"],
            param_fingerprint=tpl["param_fingerprint"],
            param_values=tpl["param_values"],
            sql_normalized=tpl["normalized"],
            title=event.get("title", ""),
            source=event.get("source", "adhoc"),
            submitted_by=event.get("submitted_by", ""),
            is_scheduled=bool(event.get("is_scheduled", False)),
            run_status="failed" if is_failed else "success",
            error_message=event.get("error"),
            duration_ms=int(event.get("duration_ms", 0)),
            dedupe_key="" if is_failed else dkey,
        )

        # 关联到同 SQL 的 QueryLog（成功且能匹配时），失败样本允许为空
        matched_log = db.scalar(select(QueryLog).where(QueryLog.sql_text == event["sql_text"]).limit(1))
        if matched_log is not None:
            execution.query_log_id = matched_log.id
            execution.target_table = matched_log.target_table

        if is_failed:
            # 失败态：仍解析以保留结构判据与目标表，但扫描量/费用强制为 0、不计费。
            # 失败（run_status）与可裁剪性（SQL 结构）是两个正交维度，这里如实保留解析结果。
            analysis = analyze_query(event["sql_text"], catalog)
            execution.parse_status = analysis.parse_status
            execution.target_table = analysis.target_table or execution.target_table
            execution.prunable = analysis.prunable
            execution.blocked_reason = analysis.blocked_reason
            execution.hit_partition_count = 0
            execution.total_partition_count = analysis.total_partition_count
            execution.scan_bytes = 0
            execution.scan_cost_cny = 0.0
            execution.is_billed = False
            failed += 1
        else:
            analysis = analyze_query(event["sql_text"], catalog)
            execution.parse_status = analysis.parse_status
            execution.target_table = analysis.target_table or execution.target_table
            execution.prunable = analysis.prunable
            execution.blocked_reason = analysis.blocked_reason
            execution.hit_partition_count = analysis.hit_partition_count
            execution.total_partition_count = analysis.total_partition_count
            execution.scan_bytes = analysis.scan_bytes
            execution.scan_cost_cny = round(
                analysis.scan_bytes / (1024 ** 3) * settings.COST_PER_GIB_CNY, 6
            )
            # 重复投递：同窗口同模板同参数，首条成功执行计费；显式 duplicate 标记也强制不计费
            if event.get("duplicate") or dkey in billed_keys:
                execution.is_billed = False
                duplicate += 1
            else:
                execution.is_billed = True
                billed_keys.add(dkey)
                billed += 1

        db.add(execution)
        created += 1

    db.commit()
    total = int(db.scalar(select(func.count(QueryExecution.id))) or 0)
    return {
        "created": created,
        "billed": billed,
        "duplicate": duplicate,
        "failed": failed,
        "total": total,
    }
