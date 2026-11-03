"""Criação das tabelas e dados iniciais (idempotente; roda na subida do app).

As tabelas da plataforma usam o prefixo fin_. As do app anterior (cenários, planilha) ficam no
banco sem uso; podem ser apagadas à mão quando não forem mais necessárias."""
from . import models  # noqa: F401  (registra as tabelas no metadata)
from .db import Base, SessionLocal, engine
from .seed import seed


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
