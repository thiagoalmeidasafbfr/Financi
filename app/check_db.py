"""Confere a conexão com o banco e cria as tabelas, se faltarem.

Uso:  python -m app.check_db
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from .config import DATABASE_URL
from .db import engine
from .migrations import init_db


def main() -> None:
    print("Banco:", make_url(DATABASE_URL).render_as_string(hide_password=True))
    query = "select 'SQLite ' || sqlite_version()" if engine.dialect.name == "sqlite" else "select version()"
    with engine.connect() as conn:
        print("Conectado:", conn.execute(text(query)).scalar())
    for line in init_db():
        print("Migração:", line)
    print("Tabelas:", ", ".join(sorted(inspect(engine).get_table_names())))


if __name__ == "__main__":
    main()
