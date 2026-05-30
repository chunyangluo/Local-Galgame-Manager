from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import ExceptionMiddleware, ApiKeyMiddleware
from api.routes import health, extract, passwords, logs, scan
from api.uptime import set_start_time
from core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_start_time()
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="自动解压工具 API",
        description="全自动文件解压管理工具 - RESTful 接口服务",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ExceptionMiddleware)
    if settings.app.api_key:
        app.add_middleware(ApiKeyMiddleware, api_key=settings.app.api_key)

    app.include_router(health.router, prefix="/api")
    app.include_router(extract.router, prefix="/api")
    app.include_router(passwords.router, prefix="/api")
    app.include_router(logs.router, prefix="/api")
    app.include_router(scan.router, prefix="/api")

    return app
