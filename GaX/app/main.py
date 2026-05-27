import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from app.api.routers import agents, api_keys, auth, checkout, cron, dashboard, payments
from app.config import settings, validate_production_settings
from app.core.exceptions import AppError, to_http_exception
from app.core.logging_config import setup_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware
from app.db.base import Base
from app.db.session import engine
from app.services.health_service import check_all_chains, check_blockchain, check_database, check_redis

setup_logging()
logger = logging.getLogger(__name__)


def _resolve_frontend_dir() -> str:
    """Repo layout: Gaxtron/frontend and Gaxtron/GaX/app/main.py."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "frontend",       # repo root (Vercel + local)
        here.parents[1] / "frontend",       # GaX/frontend fallback
        here.parents[3] / "frontend",         # extra depth fallback
    ]
    for path in candidates:
        if path.is_dir():
            return str(path)
    return str(candidates[0])


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        validate_production_settings()
    except RuntimeError as exc:
        logger.error("Production validation failed: %s", exc)
        if not os.getenv("VERCEL"):
            raise

    import app.db.models  # noqa: F401

    try:
        from app.db.migrate_schema import run_migrations

        Base.metadata.create_all(bind=engine)
        run_migrations()
    except Exception:
        logger.exception("Database init failed at startup (app will still serve /health/live)")

    logger.info(
        "Gaxtron API started [env=%s vercel=%s public_url=%s]",
        settings.env,
        bool(os.getenv("VERCEL")),
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

if settings.is_production or os.getenv("VERCEL"):
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
_cors = list(dict.fromkeys(_cors))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(payments.router)
app.include_router(checkout.router)
app.include_router(cron.router)
app.include_router(api_keys.router)
app.include_router(dashboard.router)

_frontend_dir = _resolve_frontend_dir()

_ERROR_PAGES = {
    400: "400.html",
    401: "401.html",
    403: "403.html",
    404: "404.html",
    429: "429.html",
    500: "500.html",
    503: "503.html",
}


def _accepts_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    if not accept:
        return False
    for part in accept.split(","):
        media = part.strip().split(";", 1)[0].lower()
        if media == "text/html":
            return True
        if media in ("application/json", "application/*"):
            return False
    return "text/html" in accept.lower()


def _error_page_response(request: Request, status_code: int, detail: str):
    if _accepts_html(request):
        page = _ERROR_PAGES.get(status_code, "500.html")
        path = os.path.join(_frontend_dir, page)
        if os.path.isfile(path):
            return FileResponse(path, status_code=status_code)
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.get("/favicon.ico")
@app.get("/favicon.svg")
def favicon():
    path = os.path.join(_frontend_dir, "favicon.svg")
    if os.path.isfile(path):
        return FileResponse(path, media_type="image/svg+xml")
    raise HTTPException(404)


@app.get("/site.webmanifest")
def webmanifest():
    path = os.path.join(_frontend_dir, "site.webmanifest")
    if os.path.isfile(path):
        return FileResponse(path, media_type="application/manifest+json")
    raise HTTPException(404)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return _error_page_response(request, exc.status_code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    if _accepts_html(request):
        return _error_page_response(request, 400, "Validation error")
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return _error_page_response(request, exc.status_code, detail)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return _error_page_response(request, 500, "Internal server error")


@app.get("/health")
def health():
    db_ok = check_database()
    redis_ok = check_redis()
    status_label = "ok" if db_ok else "degraded"
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


_UI_PAGES = ("index.html", "login.html", "register.html", "dashboard.html", "pay.html", "profile.html", "analytics.html")

if os.path.isdir(_frontend_dir):
    app.mount("/css", StaticFiles(directory=os.path.join(_frontend_dir, "css")), name="ui-css")
    app.mount("/js", StaticFiles(directory=os.path.join(_frontend_dir, "js")), name="ui-js")
    app.mount("/app", StaticFiles(directory=_frontend_dir, html=True), name="merchant-ui-app")

    @app.get("/")
    def ui_root():
        return RedirectResponse(url="/index.html")

    _registered_pages = set()

    def _register_page(page: str) -> None:
        if page in _registered_pages:
            return
        fp = os.path.join(_frontend_dir, page)
        if not os.path.isfile(fp):
            return

        def _page_handler(file_path=fp):
            return FileResponse(file_path)

        app.add_api_route(f"/{page}", _page_handler, methods=["GET"])
        _registered_pages.add(page)

    for page in _UI_PAGES:
        _register_page(page)

    for name in os.listdir(_frontend_dir):
        if name.endswith(".html"):
            _register_page(name)
else:
    logger.warning("Frontend directory not found: %s", _frontend_dir)
