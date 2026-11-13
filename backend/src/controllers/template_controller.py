"""模板账本 endpoints：时间窗内按查询模板聚合的成本排行 + 执行明细展开。

全部为只读接口，任何角色（含 viewer）均可访问。
"""
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.middlewares.auth import get_current_user
from src.models import User
from src.schemas.template import TemplateDetail, TemplateLedgerPage
from src.services import template_service
from src.utils.pagination import page_params


def ledger(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = Query("billed_scan_bytes"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    window: str | None = Query(None, description="小时窗口 'YYYY-MM-DD HH:00'，不传则全窗口汇总"),
    table: str | None = Query(None),
    status: str | None = Query(None, pattern="^(failed|blocked|prunable)$"),
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TemplateLedgerPage:
    params = page_params(page, page_size)
    return template_service.ledger(db, params, sort, order, window, table, status, keyword)


def detail(
    fingerprint: str,
    window: str = Query(..., description="模板所属小时窗口"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TemplateDetail:
    return template_service.template_detail(db, fingerprint, window)
