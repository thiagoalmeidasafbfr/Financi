"""Criação das tabelas e dados iniciais (idempotente; roda na subida do app).

As tabelas da plataforma usam o prefixo fin_. As do app anterior (cenários, planilha) ficam no
banco sem uso; podem ser apagadas à mão quando não forem mais necessárias.

No Vercel cada subida a frio passaria por aqui; conferir todas as tabelas custa uma ida ao banco por tabela.
Por isso a versão do esquema (tabelas, colunas e dados de partida) fica gravada em fin_meta e, se não mudou,
a subida faz uma única consulta."""
import hashlib
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

from . import models
from .db import Base, SessionLocal, engine
from .seed import seed


def schema_version() -> str:
    tables = sorted(Base.metadata.tables.values(), key=lambda t: t.name)
    parts = [f"{t.name}:{','.join(f'{c.name}/{c.type}' for c in t.columns)}" for t in tables]
    parts.append(Path(__file__).with_name("seed.py").read_text(encoding="utf-8"))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:32]


def add_missing_columns() -> list[str]:
    """Colunas novas do modelo em tabelas que já existem: ALTER TABLE ... ADD COLUMN (sempre aceitando vazio)."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    added = []
    with engine.begin() as conn:
        for t in Base.metadata.sorted_tables:
            if t.name not in tables:
                continue
            have = {c["name"] for c in insp.get_columns(t.name)}
            for col in t.columns:
                if col.name not in have:
                    kind = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {t.name} ADD COLUMN {col.name} {kind}'))
                    added.append(f"{t.name}.{col.name}")
    return added


def init_db() -> None:
    version = schema_version()
    try:
        with SessionLocal() as db:
            if db.scalar(select(models.Meta.value).where(models.Meta.key == "schema")) == version:
                return
    except SQLAlchemyError:
        pass  # banco novo: fin_meta ainda não existe
    Base.metadata.create_all(engine)
    add_missing_columns()
    with SessionLocal() as db:
        seed(db)
        row = db.get(models.Meta, "schema")
        if row:
            row.value = version
        else:
            db.add(models.Meta(key="schema", value=version))
        db.commit()
