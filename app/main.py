import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine, get_session
from .importer import import_workbook
from .routers import catalog, reports, scenarios, transactions
from .services import seed_categories

STATIC = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_categories(db)
    yield


app = FastAPI(title="Financi", description="Controle financeiro pessoal, planejamento e fluxo de caixa",
              lifespan=lifespan)


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


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")
