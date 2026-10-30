import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.deps import current_user
from app.core.security import CSRF_COOKIE, CSRF_HEADER


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {"ts": self.formatTime(record), "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        for key in ("action", "actor", "target", "path", "status", "ms", "method"):
            if hasattr(record, key):
                base[key] = getattr(record, key)
        return json.dumps(base)


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("earnscore")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False


_setup_logging()
log = logging.getLogger("earnscore.http")
settings = get_settings()


async def _purge_loop() -> None:
    from app.services.consent import purge_due

    while True:
        try:
            with SessionLocal() as db:
                purge_due(db)
        except Exception:  # keep the loop alive; failure is logged
            logging.getLogger("earnscore").exception("purge failed")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_purge_loop())
    yield
    task.cancel()


app = FastAPI(title="EarnScore API", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", CSRF_HEADER],
)

CSRF_EXEMPT = {"/api/auth/login", "/api/auth/register", "/api/auth/csrf"}


@app.middleware("http")
async def csrf_and_logging(request: Request, call_next):
    start = time.perf_counter()
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/") \
            and request.url.path not in CSRF_EXEMPT:
        cookie = request.cookies.get(CSRF_COOKIE)
        header = request.headers.get(CSRF_HEADER)
        if not cookie or not header or cookie != header:
            return JSONResponse({"detail": "Your session security token is missing or expired. Refresh the page and try again."}, status_code=403)
    if settings.is_production and request.url.path == "/api/openapi.json":
        from app.core.db import get_db
        try:
            gen = get_db()
            db = next(gen)
            user = current_user(request, db)
            if user.role != "admin":
                return JSONResponse({"detail": "Admins only."}, status_code=403)
        except HTTPException as e:
            return JSONResponse({"detail": e.detail}, status_code=e.status_code)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        log.info("request", extra={"method": request.method, "path": request.url.path, "status": response.status_code,
                                   "ms": round((time.perf_counter() - start) * 1000, 1)})
    return response


@app.get("/healthz")
def healthz():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/docs", include_in_schema=False)
def docs(request: Request):
    if settings.is_production:
        with SessionLocal() as db:
            user = current_user(request, db)
            if user.role != "admin":
                raise HTTPException(403, "Admins only.")
    return get_swagger_ui_html(openapi_url="/api/openapi.json", title="EarnScore API")


from app.api import router as api_router  # noqa: E402

app.include_router(api_router, prefix="/api")

dist = settings.frontend_dist
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
