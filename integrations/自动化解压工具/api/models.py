from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None


class ExtractPathRequest(BaseModel):
    file_path: str
    password: Optional[str] = None
    target_dir: Optional[str] = None


class AddPasswordRequest(BaseModel):
    password: Optional[str] = None


class ExtractResultData(BaseModel):
    success: bool
    file_name: str = ""
    extract_dir: str = ""
    used_password: str = ""
    error: str = ""
    archive_type: str = ""
    is_split_sfx: bool = False
    split_sfx_files: list[str] = []
    nested_results: list["ExtractResultData"] = []
    depth: int = 0
    post_process: dict = {}


class HealthData(BaseModel):
    status: str = "running"
    uptime_seconds: float = 0.0
    watch_dir: str = ""


class ScanResultData(BaseModel):
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0


class ErrorCode:
    SUCCESS = 0
    FILE_NOT_FOUND = 1001
    FORMAT_NOT_SUPPORTED = 1002
    PASSWORD_ERROR = 1003
    FILE_DAMAGED = 1004
    SPLIT_VOLUME_MISSING = 1005
    PARAM_ERROR = 2001
    PASSWORD_DUPLICATE = 2002
    INTERNAL_ERROR = 3001
    API_KEY_INVALID = 4001


def result_to_data(result, post_process: dict = None) -> ExtractResultData:
    nested = [result_to_data(nr) for nr in result.nested_results] if result.nested_results else []
    return ExtractResultData(
        success=result.success,
        file_name=result.file_name,
        extract_dir=result.extract_dir,
        used_password=result.used_password,
        error=result.error,
        archive_type=result.archive_type,
        is_split_sfx=result.is_split_sfx,
        split_sfx_files=result.split_sfx_files,
        nested_results=nested,
        depth=result.depth,
        post_process=post_process or {},
    )
