import os
import tempfile
from pathlib import Path

# banco isolado para os testes (precisa vir antes de importar o app).
# TEST_DATABASE_URL permite rodar contra PostgreSQL; o banco é recriado a cada teste.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ.pop("ANTHROPIC_API_KEY", None)  # a IA só roda nos testes com cliente falso

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:  # a subida cria as tabelas, categorias e regras padrão
        yield c


@pytest.fixture()
def db(client):
    with SessionLocal() as s:
        yield s


def ofx(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def upload(client, name: str, **form):
    return client.post("/api/imports", files={"file": (name, ofx(name), "application/x-ofx")},
                       data={k: str(v) for k, v in form.items()})


def cat_id(client, name: str) -> int:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)
