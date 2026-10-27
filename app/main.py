import base64
import os
import secrets
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine, get_session
from .importer import import_workbook
from .routers import catalog, reports, scenarios, transactions
from .services import seed_categories

ROOT = Path(__file__).resolve().parent.parent
# Arquivos estáticos ficam em public/: no Vercel a CDN os serve direto em /static/...;
# rodando localmente, o próprio app serve a pasta.
STATIC = ROOT / "public" / "static"
INDEX = Path(__file__).parent / "index.html"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_categories(db)
    yield


app = FastAPI(title="Financi", description="Controle financeiro pessoal, planejamento e fluxo de caixa",
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
    }


app.include_router(scenarios.router)
app.include_router(catalog.router)
app.include_router(transactions.router)
app.include_router(reports.router)


@app.post("/api/import/xlsx", tags=["importação"])
async def import_xlsx(file: UploadFile = File(...), db: Session = Depends(get_session)):
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
        tmp.write(await file.read())
        tmp.flush()
        return {"report": import_workbook(db, tmp.name)}


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(INDEX)
