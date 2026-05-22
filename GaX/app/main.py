import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from app.api.routers import api_keys, auth, checkout, cron, dashboard, payments
from app.config import settings, validate_production_settings
from app.core.exceptions import AppError, to_http_exception
from app.core.logging_config import setup_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware
from app.db.base import Base
from app.db.session import engine
from app.services.health_service import check_all_chains, check_blockchain, check_database, check_redis

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_production_settings()
    import app.db.models  # noqa: F401

    from app.db.migrate_schema import run_migrations

    Base.metadata.create_all(bind=engine)
    run_migrations()
    logger.info(
        "Gaxtron API started [env=%s debug=%s public_url=%s]",
        settings.env,
        settings.debug,
        settings.public_base_url,
    )
    yield
    logger.info("Gaxtron API shutting down")


app = FastAPI(
    title="Gaxtron Crypto Payment Gateway",
    description="Production crypto payment API",
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

if settings.is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_host_list,
    )

_cors = list(settings.cors_origin_list)
if settings.debug or settings.env == "development":
    _cors.extend([
        "http://localhost:8002",
        "http://127.0.0.1:8002",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ])
_cors = list(dict.fromkeys(_cors))  # dedupe

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(payments.router)
app.include_router(checkout.router)
app.include_router(cron.router)
app.include_router(api_keys.router)
app.include_router(dashboard.router)

import os

_frontend_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
)
if not os.path.isdir(_frontend_dir):
    _alt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend"))
    if os.path.isdir(_alt):
        _frontend_dir = _alt


@app.get("/favicon.ico")
@app.get("/favicon.svg")
def favicon():
    path = os.path.join(_frontend_dir, "favicon.svg")
    if os.path.isfile(path):
        return FileResponse(path, media_type="image/svg+xml")
    raise HTTPException(404)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health():
    db_ok = check_database()
    redis_ok = check_redis()
    status_label = "ok" if db_ok and redis_ok else "degraded"
    chains = check_all_chains()
    return {
        "status": status_label,
        "service": "gaxtron-api",
        "env": settings.env,
        "checks": {"database": db_ok, "redis": redis_ok, "chains": chains},
    }


@app.get("/health/ready")
def readiness():
    if not check_database():
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": False})
    return {"status": "ready", "database": True, "redis": check_redis(), "blockchain": check_blockchain()}


@app.get("/health/live")
def liveness():
    return {"status": "alive"}


# Merchant UI on same port as API (no CORS): http://127.0.0.1:8002/register.html
_UI_PAGES = ("index.html", "login.html", "register.html", "dashboard.html", "pay.html")

if os.path.isdir(_frontend_dir):
    app.mount("/css", StaticFiles(directory=os.path.join(_frontend_dir, "css")), name="ui-css")
    app.mount("/js", StaticFiles(directory=os.path.join(_frontend_dir, "js")), name="ui-js")
    app.mount("/app", StaticFiles(directory=_frontend_dir, html=True), name="merchant-ui-app")

    @app.get("/")
    def ui_root():
        return RedirectResponse(url="/index.html")

    for page in _UI_PAGES:
        _path = os.path.join(_frontend_dir, page)

        def _page_handler(p=page, fp=_path):
            if os.path.isfile(fp):
                return FileResponse(fp)
            raise HTTPException(404)

        app.add_api_route(f"/{page}", _page_handler, methods=["GET"])
