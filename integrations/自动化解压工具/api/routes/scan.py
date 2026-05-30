from __future__ import annotations

from fastapi import APIRouter

from api.models import ApiResponse, ScanResultData
from api.deps import get_watcher_service

router = APIRouter(tags=["扫描"])


@router.post("/scan", summary="手动扫描目录", response_model=ApiResponse)
async def scan_directory():
    watcher = get_watcher_service()
    result = await watcher.scan_directory()
    data = ScanResultData(**result)
    return ApiResponse(data=data.model_dump())
