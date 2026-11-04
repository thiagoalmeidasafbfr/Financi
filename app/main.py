import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import ai, auth
from .db import engine
from .migrations import init_db
from .routers import cockpit, core, groupings, planned, planning, quick, transactions

ROOT = Path(__file__).resolve().parent.parent
# Arquivos estáticos ficam em public/: no Vercel a CDN os serve direto em /static/...;
# rodando localmente, o próprio app serve a pasta.
STATIC = ROOT / "public" / "static"
INDEX = Path(__file__).parent / "index.html"
SW = Path(__file__).parent / "sw.js"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Financi", description="Finanças pessoais: extratos OFX, categorização, planejamento e dívidas",
              lifespan=lifespan)


app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Com FINANCI_PASSWORD definida (obrigatório ao publicar), a API pede login (ver auth.py).

    A página e os arquivos estáticos não têm dados e abrem direto: a tela de entrada é do próprio app."""
    if auth.needs_auth(request.url.path) and not auth.is_authenticated(request):
        return JSONResponse({"detail": "Entre para continuar"}, status_code=401)
    return await call_next(request)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


@app.get("/api/status", tags=["status"])
def status():
    """Usado pela interface para avisar sobre configuração insegura ao publicar."""
    return {
        "database": engine.dialect.name,
        "auth": bool(os.environ.get("FINANCI_PASSWORD")),
        "hosted": bool(os.environ.get("VERCEL")),
        "ai": ai.available(),
    }


app.include_router(auth.router)
app.include_router(core.router)
app.include_router(transactions.router)
app.include_router(planning.router)
app.include_router(planned.router)
app.include_router(groupings.router)
app.include_router(quick.router)
app.include_router(cockpit.router)


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(INDEX, headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """Fica na raiz para controlar o app inteiro (guarda a casca do app no aparelho: abre sem esperar o servidor)."""
    return FileResponse(SW, media_type="text/javascript", headers={"Cache-Control": "no-cache"})
