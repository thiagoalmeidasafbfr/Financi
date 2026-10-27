from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    # Bancos serverless (Neon) suspendem a compute por inatividade e derrubam as
    # conexões abertas: testa a conexão antes de usar e recicla as antigas.
    connect_args = {}
    if "-pooler." in url:
        # pooler do Neon (PgBouncer em modo transação): não depende de prepared statements no servidor
        connect_args["prepare_threshold"] = None
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, connect_args=connect_args)


engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

