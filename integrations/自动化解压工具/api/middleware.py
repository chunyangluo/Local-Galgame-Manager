from __future__ import annotations

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from api.models import ApiResponse, ErrorCode


class ExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            logger.error(f"请求异常: {request.method} {request.url} | {e}")
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=500,
                content=ApiResponse(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"服务内部错误: {str(e)}",
                ).model_dump(),
            )


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str = ""):
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not self._api_key:
            return await call_next(request)

        if request.url.path == "/api/health" or request.url.path == "/docs" or request.url.path == "/openapi.json":
            return await call_next(request)

        key = request.headers.get("X-API-Key", "")
        if key != self._api_key:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content=ApiResponse(
                    code=ErrorCode.API_KEY_INVALID,
                    message="API Key 无效",
                ).model_dump(),
            )

        return await call_next(request)
