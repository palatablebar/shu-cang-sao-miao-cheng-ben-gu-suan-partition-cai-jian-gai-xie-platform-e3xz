"""模板账本 router（只读）。"""
from fastapi import APIRouter

from src.controllers import template_controller

router = APIRouter(prefix="/query-templates", tags=["query-templates"])

router.add_api_route("", template_controller.ledger, methods=["GET"])
router.add_api_route("/{fingerprint}/detail", template_controller.detail, methods=["GET"])
