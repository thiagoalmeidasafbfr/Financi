import base64
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import ai
from .db import engine
from .migrations import init_db
from .routers import core, planning, transactions

ROOT = Path(__file__).resolve().parent.parent
# Arquivos estáticos ficam em public/: no Vercel a CDN os serve direto em /static/...;
# rodando localmente, o próprio app serve a pasta.
STATIC = ROOT / "public" / "static"
INDEX = Path(__file__).parent / "index.html"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Financi", description="Finanças pessoais: extratos OFX, categorização, planejamento e dívidas",
              lifespan=lifespan)


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """Com FINANCI_PASSWORD definida (obrigatório ao publicar), todo acesso pede usuário e senha."""
    password = os.environ.get("FINANCI_PASSWORD")
    if not password or request.url.path == "/healthz":
        return await call_next(request)
    user = os.environ.get("FINANCI_USER", "financi")
    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            given_user, _, given_pw = base64.b64decode(header[6:]).decode().partition(":")
        except (ValueError, UnicodeDecodeError):
            given_user = given_pw = ""
        if secrets.compare_digest(given_user.encode(), user.encode()) and \
                secrets.compare_digest(given_pw.encode(), password.encode()):
            return await call_next(request)
    return Response("Autenticação necessária", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="Financi", charset="UTF-8"'})


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


app.include_router(core.router)
app.include_router(transactions.router)
app.include_router(planning.router)


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(INDEX)
