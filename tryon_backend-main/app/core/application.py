from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.common.exceptions import AppException
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Backend API for AI-powered virtual clothing and footwear try-on.",
        version=settings.APP_VERSION,
        debug=settings.APP_DEBUG,
    )

    storage_path = Path(settings.LOCAL_STORAGE_DIR)
    storage_path.mkdir(parents=True, exist_ok=True)

    app.mount(
        "/local-files",
        StaticFiles(directory=settings.LOCAL_STORAGE_DIR),
        name="local-files",
    )

    @app.exception_handler(AppException)
    def app_exception_handler(
        request: Request,
        exc: AppException,
    ):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error_code": exc.error_code,
                "message": exc.message,
            },
        )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app