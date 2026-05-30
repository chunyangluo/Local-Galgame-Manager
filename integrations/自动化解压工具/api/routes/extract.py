from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File

from api.models import (
    ApiResponse,
    ExtractPathRequest,
    ExtractResultData,
    ErrorCode,
    result_to_data,
)
from api.deps import get_extractor, get_file_manager

router = APIRouter(tags=["解压"])


@router.post("/extract/path", summary="指定路径解压", response_model=ApiResponse)
async def extract_by_path(req: ExtractPathRequest):
    file_path = Path(req.file_path).resolve()
    if not file_path.exists():
        return ApiResponse(
            code=ErrorCode.FILE_NOT_FOUND,
            message="文件不存在",
        )

    extractor = get_extractor()
    file_manager = get_file_manager()

    target_dir = req.target_dir if req.target_dir else None

    result = await extractor.extract(
        file_path=str(file_path),
        custom_password=req.password,
        output_dir=target_dir,
    )
    post_result, _ = file_manager.handle_extract_result(result)

    data = result_to_data(result, post_result)
    if result.success:
        return ApiResponse(data=data.model_dump())
    else:
        code = _error_code_from_result(result)
        return ApiResponse(code=code, message=result.error, data=data.model_dump())


@router.post("/extract/upload", summary="文件上传解压", response_model=ApiResponse)
async def extract_by_upload(file: UploadFile = File(...), target_dir: str = ""):
    settings = get_settings_from_deps()
    upload_dir = Path(settings.directories.upload)
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest = upload_dir / file.filename
    dest = _resolve_conflict(dest)

    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        return ApiResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=f"文件保存失败: {str(e)}",
        )

    extractor = get_extractor()
    file_manager = get_file_manager()

    output_dir = target_dir if target_dir else None

    result = await extractor.extract(str(dest), output_dir=output_dir)
    post_result, _ = file_manager.handle_extract_result(result)

    data = result_to_data(result, post_result)
    if result.success:
        return ApiResponse(data=data.model_dump())
    else:
        code = _error_code_from_result(result)
        return ApiResponse(code=code, message=result.error, data=data.model_dump())


def _error_code_from_result(result) -> int:
    error = result.error
    if result.is_split_sfx and "分卷" in error:
        return ErrorCode.SPLIT_VOLUME_MISSING
    if "格式" in error:
        return ErrorCode.FORMAT_NOT_SUPPORTED
    if "密码" in error:
        return ErrorCode.PASSWORD_ERROR
    if "损坏" in error:
        return ErrorCode.FILE_DAMAGED
    return ErrorCode.INTERNAL_ERROR


def _resolve_conflict(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        new_dest = parent / new_name
        if not new_dest.exists():
            return new_dest
        counter += 1


def get_settings_from_deps():
    from core.config import get_settings
    return get_settings()
