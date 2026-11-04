"""Acesso: senha salva no aparelho (cookie), Face ID por passkey (WebAuthn) e subida rápida do banco."""
import base64
import hashlib
import json
import os

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import event

from app import auth
from app.db import engine
from app.migrations import init_db

ORIGIN = "http://testserver"


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class SoftAuthenticator:
    """Faz o papel do Face ID: gera a chave, assina os desafios (formato "none", ES256)."""

    def __init__(self, rp_id="testserver"):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(16)
        self.rp_hash = hashlib.sha256(rp_id.encode()).digest()
        self.count = 0

    def _client_data(self, kind, challenge, origin):
        return json.dumps({"type": kind, "challenge": challenge, "origin": origin, "crossOrigin": False}).encode()

    def create(self, options, origin=ORIGIN):
        nums = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        auth_data = (self.rp_hash + bytes([0x01 | 0x04 | 0x40]) + (0).to_bytes(4, "big") + bytes(16)
                     + len(self.cred_id).to_bytes(2, "big") + self.cred_id + cose)
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {"id": b64u(self.cred_id), "rawId": b64u(self.cred_id), "type": "public-key", "clientExtensionResults": {},
                "response": {"clientDataJSON": b64u(self._client_data("webauthn.create", options["challenge"], origin)),
                             "attestationObject": b64u(att)}}

    def get(self, options, origin=ORIGIN, verified=True):
        self.count += 1
        cd = self._client_data("webauthn.get", options["challenge"], origin)
        auth_data = self.rp_hash + bytes([0x01 | (0x04 if verified else 0)]) + self.count.to_bytes(4, "big")
        sig = self.key.sign(auth_data + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64u(self.cred_id), "rawId": b64u(self.cred_id), "type": "public-key", "clientExtensionResults": {},
                "response": {"clientDataJSON": b64u(cd), "authenticatorData": b64u(auth_data), "signature": b64u(sig),
                             "userHandle": b64u(b"financi")}}


@pytest.fixture()
def locked(client, monkeypatch):
    monkeypatch.setenv("FINANCI_PASSWORD", "s3gredo")

    async def no_wait(_):
        return None
    monkeypatch.setattr(auth.asyncio, "sleep", no_wait)  # a espera após senha errada não atrasa os testes
    return client


def session_cookie(r):
    return next(h for h in r.headers.get_list("set-cookie") if h.startswith(auth.COOKIE + "="))


def test_open_without_password(client):
    assert client.get("/api/people").status_code == 200
    assert client.get("/api/auth/state").json() == {"required": False, "logged_in": True, "passkeys": False}


def test_password_once_stays_saved(locked):
    c = locked
    r = c.get("/api/people")
    assert r.status_code == 401 and "www-authenticate" not in r.headers  # sem a janela de senha do navegador
    assert c.get("/").status_code == 200 and c.get("/sw.js").status_code == 200 and c.get("/healthz").status_code == 200
    assert c.get("/api/auth/state").json()["logged_in"] is False
    assert c.post("/api/auth/login", json={"password": "errada"}).status_code == 401
    r = c.post("/api/auth/login", json={"password": "s3gredo"})
    assert r.status_code == 204
    cookie = session_cookie(r)
    assert "Max-Age=31536000" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert c.get("/api/people").status_code == 200
    # trocar a senha encerra as sessões
    os.environ["FINANCI_PASSWORD"] = "nova"
    assert c.get("/api/people").status_code == 401
    os.environ["FINANCI_PASSWORD"] = "s3gredo"
    assert c.get("/api/people").status_code == 200
    c.post("/api/auth/logout")
    assert c.get("/api/people").status_code == 401
    # sem "lembrar": cookie da sessão (some ao fechar o app)
    r = c.post("/api/auth/login", json={"password": "s3gredo", "remember": False})
    assert "Max-Age" not in session_cookie(r) and c.get("/api/people").status_code == 200
    # scripts seguem entrando com usuário e senha no cabeçalho
    c.cookies.clear()
    basic = {"Authorization": "Basic " + base64.b64encode(b"financi:s3gredo").decode()}
    assert c.get("/api/people", headers=basic).status_code == 200


def test_tampered_or_expired_token(locked, monkeypatch):
    good = auth.sign({"t": "s", "exp": 2**40})
    assert auth.unsign(good)["t"] == "s"
    body, _, mac = good.partition(".")
    assert auth.unsign(f"{b64u(json.dumps({'t': 's', 'exp': 2**41}).encode())}.{mac}") is None
    assert auth.unsign(auth.sign({"t": "s", "exp": 1})) is None
    assert auth.unsign("lixo") is None and auth.unsign(None) is None


def test_face_id_passkey(locked):
    c = locked
    phone = SoftAuthenticator()
    assert c.post("/api/auth/passkey/register/options").status_code == 401  # só com sessão
    c.post("/api/auth/login", json={"password": "s3gredo"})

    opts = c.post("/api/auth/passkey/register/options").json()
    assert opts["rp"]["id"] == "testserver" and opts["authenticatorSelection"]["userVerification"] == "required"
    r = c.post("/api/auth/passkey/register", json={"credential": phone.create(opts), "label": "iPhone"})
    assert r.status_code == 200, r.text
    assert "Max-Age" not in session_cookie(r)  # com Face ID a sessão deixa de ficar salva
    assert c.get("/api/auth/state").json()["passkeys"] is True
    keys = c.get("/api/auth/passkeys").json()
    assert [k["label"] for k in keys] == ["iPhone"] and keys[0]["last_used_at"] is None

    c.post("/api/auth/logout")
    assert c.get("/api/people").status_code == 401
    # abrir o app: Face ID
    opts = c.post("/api/auth/passkey/login/options").json()
    assert opts["userVerification"] == "required" and opts["allowCredentials"] == []
    r = c.post("/api/auth/passkey/login", json={"credential": phone.get(opts)})
    assert r.status_code == 204, r.text
    assert c.get("/api/people").status_code == 200
    assert c.get("/api/auth/passkeys").json()[0]["last_used_at"]

    c.post("/api/auth/logout")
    # o mesmo desafio não vale duas vezes
    assert c.post("/api/auth/passkey/login", json={"credential": phone.get(opts)}).status_code == 400
    # outro endereço (phishing), biometria não confirmada, aparelho desconhecido: recusados
    for cred in (phone.get(c.post("/api/auth/passkey/login/options").json(), origin="https://falso.example"),
                 phone.get(c.post("/api/auth/passkey/login/options").json(), verified=False),
                 SoftAuthenticator().get(c.post("/api/auth/passkey/login/options").json())):
        assert c.post("/api/auth/passkey/login", json={"credential": cred}).status_code == 401
    assert c.get("/api/people").status_code == 401

    # remover a biometria: o aparelho volta a precisar da senha
    c.post("/api/auth/login", json={"password": "s3gredo"})
    assert c.delete(f"/api/auth/passkeys/{keys[0]['id']}").status_code == 204
    c.post("/api/auth/logout")
    cred = phone.get(c.post("/api/auth/passkey/login/options").json())
    assert c.post("/api/auth/passkey/login", json={"credential": cred}).status_code == 401


def test_session_switch_back_to_saved(locked):
    c = locked
    c.post("/api/auth/login", json={"password": "s3gredo", "remember": False})
    r = c.post("/api/auth/session", json={"remember": True})
    assert r.status_code == 204 and "Max-Age=31536000" in session_cookie(r)


def test_warm_start_is_one_query(client):
    """Com o esquema já criado, a subida faz uma consulta só (no Vercel cada uma é uma ida ao Neon)."""
    n = []
    listener = lambda *a: n.append(1)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        init_db()
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len(n) == 1
