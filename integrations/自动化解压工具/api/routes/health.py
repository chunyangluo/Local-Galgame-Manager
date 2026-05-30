from __future__ import annotations

from fastapi import APIRouter

from api.models import ApiResponse, HealthData
from api.uptime import get_uptime
from core.config import get_settings

router = APIRouter(tags=["健康检测"])


@router.get("/health", summary="服务健康检测", response_model=ApiResponse)
async def health_check():
    settings = get_settings()
    data = HealthData(
        status="running",
        uptime_seconds=round(get_uptime(), 1),
        watch_dir=settings.directories.watch,
    )
    return ApiResponse(data=data.model_dump())
