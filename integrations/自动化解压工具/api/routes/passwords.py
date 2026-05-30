from __future__ import annotations

from fastapi import APIRouter

from api.models import ApiResponse, AddPasswordRequest, ErrorCode
from api.deps import get_password_manager

router = APIRouter(tags=["密码本"])


@router.get("/passwords", summary="查询密码本", response_model=ApiResponse)
async def get_passwords():
    pm = get_password_manager()
    passwords = pm.get_passwords()
    return ApiResponse(data=passwords)


@router.post("/passwords", summary="新增解压密码", response_model=ApiResponse)
async def add_password(req: AddPasswordRequest):
    if not req.password or not req.password.strip():
        return ApiResponse(
            code=ErrorCode.PARAM_ERROR,
            message="密码不能为空",
        )
    pm = get_password_manager()
    ok, msg = pm.add_password(req.password.strip())
    if not ok:
        return ApiResponse(
            code=ErrorCode.PASSWORD_DUPLICATE,
            message=msg,
        )
    return ApiResponse(message=msg)
