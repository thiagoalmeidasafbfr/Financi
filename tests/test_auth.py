import base64


def basic(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


def test_open_without_password(client, monkeypatch):
    monkeypatch.delenv("FINANCI_PASSWORD", raising=False)
    assert client.get("/api/scenarios").status_code == 200


def test_password_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("FINANCI_PASSWORD", "s3gredo")
    assert client.get("/api/scenarios").status_code == 401
    assert client.get("/").headers["www-authenticate"].startswith("Basic")
    assert client.get("/api/scenarios", headers=basic("financi", "errada")).status_code == 401
    assert client.get("/api/scenarios", headers=basic("financi", "s3gredo")).status_code == 200
    assert client.get("/healthz").status_code == 200  # health check do Render fica aberto
