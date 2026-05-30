from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter

from api.models import ApiResponse, ErrorCode
from core.config import get_settings

router = APIRouter(tags=["日志"])


@router.get("/logs/today", summary="查询当日日志", response_model=ApiResponse)
async def get_today_logs():
    settings = get_settings()
    log_dir = Path(settings.directories.logs)
    today = datetime.date.today().strftime("%Y-%m-%d")

    log_file = log_dir / f"extract_{today}.log"
    if not log_file.exists():
        return ApiResponse(data="")

    try:
        content = log_file.read_text(encoding="utf-8")
        return ApiResponse(data=content)
    except Exception as e:
        return ApiResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=f"读取日志失败: {str(e)}",
        )
