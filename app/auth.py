"""Acesso: senha uma vez por aparelho (sessão em cookie) e Face ID / digital (passkeys WebAuthn).

Com FINANCI_PASSWORD definida, a API pede uma sessão. Entrando com a senha, ela fica salva no aparelho por um ano.
Com "Abrir com Face ID" ligado no aparelho, a sessão vale só enquanto o app está aberto (no máximo 12 h) e cada
abertura pede a biometria; a senha continua valendo como alternativa.

A sessão é um token assinado (HMAC) com chave derivada da senha (ou de FINANCI_SECRET): trocar a senha encerra
todas as sessões. Os desafios do WebAuthn também vão num cookie assinado, sem estado no servidor (serverless)."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import Passkey

COOKIE = "financi_session"
CHALLENGE = "financi_challenge"
REMEMBER_DAYS = 365
LOCKED_SECONDS = 12 * 3600       # sessão aberta pela biometria (ou sem "lembrar")
CHALLENGE_SECONDS = 300
# rotas que funcionam sem sessão (o resto da API pede login)
PUBLIC = {"/", "/sw.js", "/healthz", "/api/auth/state", "/api/auth/login", "/api/auth/logout",
          "/api/auth/passkey/login/options", "/api/auth/passkey/login"}


def password() -> str | None:
    return os.environ.get("FINANCI_PASSWORD") or None


def _key() -> bytes:
    secret = os.environ.get("FINANCI_SECRET") or password() or ""
    return hashlib.sha256(b"financi-session:" + secret.encode()).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    mac = hmac.new(_key(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(mac)}"


def unsign(token: str | None) -> dict | None:
    """Payload do token se a assinatura confere e ele não expirou."""
    if not token or "." not in token:
        return None
    body, _, mac = token.partition(".")
    try:
        good = hmac.compare_digest(_unb64(mac), hmac.new(_key(), body.encode(), hashlib.sha256).digest())
        payload = json.loads(_unb64(body)) if good else None
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload


def _basic_ok(header: str) -> bool:
    """Usuário e senha no cabeçalho (scripts, curl). O app usa o cookie."""
    if not header.startswith("Basic "):
        return False
    try:
        user, _, given = base64.b64decode(header[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    expected_user = os.environ.get("FINANCI_USER", "financi")
    return hmac.compare_digest(user.encode(), expected_user.encode()) and hmac.compare_digest(given.encode(), (password() or "").encode())


def is_authenticated(request: Request) -> bool:
    if not password():
        return True
    payload = unsign(request.cookies.get(COOKIE))
    return bool(payload and payload.get("t") == "s") or _basic_ok(request.headers.get("authorization", ""))


def needs_auth(path: str) -> bool:
    return bool(password()) and path not in PUBLIC and not path.startswith("/static/")


def _secure(request: Request) -> bool:
    return (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"


def start_session(request: Request, response: Response, remember: bool) -> None:
    """remember: fica salvo por um ano; senão vale até fechar o app (máx. 12 h)."""
    seconds = REMEMBER_DAYS * 86400 if remember else LOCKED_SECONDS
    token = sign({"t": "s", "exp": int(time.time()) + seconds, "r": remember})
    response.set_cookie(COOKIE, token, max_age=seconds if remember else None, httponly=True, samesite="lax",
                        secure=_secure(request), path="/")


def require_session(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(401, "Entre para continuar")


def _origin(request: Request) -> tuple[str, str]:
    """(rp_id, origin) deste endereço: o domínio onde o app está publicado."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return host.split(":")[0], os.environ.get("FINANCI_ORIGIN") or f"{proto}://{host}"


def _set_challenge(request: Request, response: Response, kind: str, challenge: bytes) -> None:
    token = sign({"t": kind, "c": _b64(challenge), "exp": int(time.time()) + CHALLENGE_SECONDS})
    response.set_cookie(CHALLENGE, token, max_age=CHALLENGE_SECONDS, httponly=True, samesite="strict",
                        secure=_secure(request), path="/api/auth")


def _take_challenge(request: Request, response: Response, kind: str) -> bytes:
    payload = unsign(request.cookies.get(CHALLENGE))
    response.delete_cookie(CHALLENGE, path="/api/auth")
    if not payload or payload.get("t") != kind:
        raise HTTPException(400, "Tempo esgotado. Tente de novo.")
    return _unb64(payload["c"])


router = APIRouter(prefix="/api/auth", tags=["acesso"])


class LoginIn(BaseModel):
    password: str
    remember: bool = True


class SessionIn(BaseModel):
    remember: bool


class PasskeyIn(BaseModel):
    credential: dict
    label: str | None = None


@router.get("/state")
def state(request: Request, db: Session = Depends(get_session)):
    """O que a tela de entrada precisa saber (sem dados financeiros)."""
    return {"required": bool(password()), "logged_in": is_authenticated(request),
            "passkeys": bool(password()) and db.scalar(select(Passkey.id).limit(1)) is not None}


@router.post("/login", status_code=204)
async def login(body: LoginIn, request: Request, response: Response):
    if not password():
        raise HTTPException(400, "Sem senha configurada")
    if not hmac.compare_digest(body.password.encode(), password().encode()):
        await asyncio.sleep(1)  # freia tentativas em sequência
        raise HTTPException(401, "Senha incorreta")
    start_session(request, response, body.remember)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")


@router.post("/session", status_code=204, dependencies=[Depends(require_session)])
def renew(body: SessionIn, request: Request, response: Response):
    """Troca o tipo da sessão atual: salva no aparelho ou só enquanto o app está aberto."""
    start_session(request, response, body.remember)


@router.get("/passkeys", dependencies=[Depends(require_session)])
def list_passkeys(db: Session = Depends(get_session)):
    return [{"id": p.id, "label": p.label, "created_at": p.created_at.isoformat(),
             "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None}
            for p in db.scalars(select(Passkey).order_by(Passkey.created_at))]


@router.delete("/passkeys/{pid}", status_code=204, dependencies=[Depends(require_session)])
def delete_passkey(pid: int, db: Session = Depends(get_session)):
    p = db.get(Passkey, pid)
    if not p:
        raise HTTPException(404, "Não encontrada")
    db.delete(p)
    db.commit()


@router.post("/passkey/register/options", dependencies=[Depends(require_session)])
def register_options(request: Request, response: Response, db: Session = Depends(get_session)):
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorAttachment,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )
    rp_id, _ = _origin(request)
    opts = generate_registration_options(
        rp_id=rp_id, rp_name="Financi", user_name="Financi", user_display_name="Financi", user_id=secrets.token_bytes(16),
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM, resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=_unb64(p.credential_id)) for p in db.scalars(select(Passkey))],
    )
    _set_challenge(request, response, "reg", opts.challenge)
    return json.loads(options_to_json(opts))


@router.post("/passkey/register", dependencies=[Depends(require_session)])
def register(body: PasskeyIn, request: Request, response: Response, db: Session = Depends(get_session)):
    """Cadastra a biometria deste aparelho. A partir daí ele abre com Face ID (a sessão deixa de ficar salva)."""
    from webauthn import verify_registration_response
    from webauthn.helpers.exceptions import InvalidRegistrationResponse
    challenge = _take_challenge(request, response, "reg")
    rp_id, origin = _origin(request)
    try:
        v = verify_registration_response(credential=body.credential, expected_challenge=challenge, expected_rp_id=rp_id,
                                         expected_origin=origin, require_user_verification=True)
    except (InvalidRegistrationResponse, ValueError, KeyError) as e:
        raise HTTPException(400, f"Não foi possível ativar: {e}") from e
    p = Passkey(credential_id=_b64(v.credential_id), public_key=v.credential_public_key, sign_count=v.sign_count,
                label=(body.label or "Aparelho").strip()[:80] or "Aparelho")
    db.add(p)
    db.commit()
    start_session(request, response, remember=False)
    return {"id": p.id, "label": p.label}


@router.post("/passkey/login/options")
def login_options(request: Request, response: Response):
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement
    if not password():
        raise HTTPException(400, "Sem senha configurada")
    rp_id, _ = _origin(request)
    # sem lista de credenciais: o aparelho oferece a passkey que tem para este endereço
    opts = generate_authentication_options(rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED)
    _set_challenge(request, response, "auth", opts.challenge)
    return json.loads(options_to_json(opts))


@router.post("/passkey/login", status_code=204)
def passkey_login(body: PasskeyIn, request: Request, response: Response, db: Session = Depends(get_session)):
    from webauthn import verify_authentication_response
    from webauthn.helpers.exceptions import InvalidAuthenticationResponse
    challenge = _take_challenge(request, response, "auth")
    cred_id = str(body.credential.get("id") or "")
    p = db.scalar(select(Passkey).where(Passkey.credential_id == cred_id.rstrip("=")))
    if not p:
        raise HTTPException(401, "Esta biometria não está mais ativa. Entre com a senha.")
    rp_id, origin = _origin(request)
    try:
        v = verify_authentication_response(credential=body.credential, expected_challenge=challenge, expected_rp_id=rp_id,
                                           expected_origin=origin, credential_public_key=p.public_key,
                                           credential_current_sign_count=p.sign_count, require_user_verification=True)
    except (InvalidAuthenticationResponse, ValueError, KeyError) as e:
        raise HTTPException(401, "Não foi possível confirmar a biometria") from e
    p.sign_count = v.new_sign_count
    p.last_used_at = datetime.now()  # noqa: DTZ005  (horário local, como o resto do app)
    db.commit()
    start_session(request, response, remember=False)
