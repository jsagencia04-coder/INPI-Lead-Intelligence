"""Autenticação e autorização da API.

- AUTH_MODE=dev:      sem login; usuário fixo 'dev@local' com papel admin. Só no ambiente demo.
- AUTH_MODE=local:    login próprio. Token assinado com APP_SECRET_KEY; usuário e papel vêm de app_users.
- AUTH_MODE=supabase: valida o JWT do Supabase Auth; o papel vem de app_users pelo e-mail
                      (e-mail fora da lista = acesso negado, mesmo com conta válida no Supabase).

Toda rota protegida passa por current_user, que também aplica a política de papéis (app.security.REGRAS).
"""

import time
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import db, security
from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)
EMISSOR = "inpi-lead-intelligence"


@dataclass(frozen=True)
class User:
    id: str
    email: str | None
    papel: str = "admin"

    @property
    def actor(self) -> str:
        return f"user:{self.email or self.id}"


@lru_cache
def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def emitir_token(user_id: int, email: str, settings: Settings) -> str:
    agora = int(time.time())
    return jwt.encode(
        {"sub": str(user_id), "email": email, "iss": EMISSOR, "iat": agora, "exp": agora + settings.token_horas * 3600},
        settings.app_secret_key,
        algorithm="HS256",
    )


def decode_token(token: str, settings: Settings) -> dict:
    if settings.auth_mode == "local":
        if not settings.app_secret_key:
            raise jwt.InvalidTokenError("APP_SECRET_KEY não configurado")
        return jwt.decode(
            token, settings.app_secret_key, algorithms=["HS256"], issuer=EMISSOR, options={"require": ["exp", "sub"]}
        )
    alg = jwt.get_unverified_header(token).get("alg")
    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise jwt.InvalidTokenError("HS256 sem SUPABASE_JWT_SECRET configurado")
        key = settings.supabase_jwt_secret
    else:
        if not settings.supabase_url:
            raise jwt.InvalidTokenError("SUPABASE_URL não configurado")
        key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=[alg], audience="authenticated")


def usuario_do_token(token: str | None, settings: Settings) -> User:
    """Identifica o usuário (sem checar permissão de rota). Levanta 401/403."""
    if settings.auth_mode == "dev":
        return User(id="dev", email="dev@local", papel="admin")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login para continuar")
    try:
        claims = decode_token(token, settings)
    except jwt.PyJWTError as exc:
        # sem detalhes da falha: não ajuda quem está tentando forjar um token
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida ou expirada. Faça login novamente") from exc
    email = (claims.get("email") or "").lower()
    with db.get_pool().connection() as conn:
        if settings.auth_mode == "local":
            u = conn.execute("select * from app_users where id = %s", (int(claims["sub"]),)).fetchone()
        else:
            u = conn.execute("select * from app_users where email = %s", (email,)).fetchone()
    if u is None or not u["ativo"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuário sem acesso a este sistema")
    return User(id=str(u["id"]), email=u["email"], papel=u["papel"])


def current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> User:
    user = usuario_do_token(creds.credentials if creds else None, settings)
    caminho = request.url.path
    if not security.pode(user.papel, request.method, caminho):
        minimo = security.papel_minimo(request.method, caminho)
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Seu perfil ({user.papel}) não permite esta ação. Exige: {minimo}")
    return user
