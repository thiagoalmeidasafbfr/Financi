import os
from pathlib import Path


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            # aceita valores entre aspas, como no .env gerado pelo painel do Neon
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def normalize_url(url: str) -> str:
    """Aceita a connection string como o Neon/Supabase entregam (postgresql:// ou
    postgres://) e usa o driver psycopg 3."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


_load_dotenv()

DATABASE_URL = normalize_url(os.environ.get("DATABASE_URL", "sqlite:///./financi.db"))
