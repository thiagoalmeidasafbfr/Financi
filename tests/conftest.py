import os
import tempfile

# banco isolado para os testes (precisa vir antes de importar o app).
# TEST_DATABASE_URL permite rodar contra PostgreSQL; o banco é apagado a cada teste.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp()}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:  # startup cria tabelas e categorias padrão
        yield c
