from app.config import normalize_url


def test_neon_connection_string_uses_psycopg_driver():
    neon = "postgresql://owner:pw@ep-x-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert normalize_url(neon) == neon.replace("postgresql://", "postgresql+psycopg://", 1)
    assert normalize_url("postgres://a@b/c") == "postgresql+psycopg://a@b/c"


def test_other_urls_untouched():
    for url in ("postgresql+psycopg://a@b/c", "sqlite:///./financi.db"):
        assert normalize_url(url) == url
