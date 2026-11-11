"""Login próprio e administração de usuários."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app import db, security
from app.auth import User, current_user, emitir_token
from app.config import get_settings

public = APIRouter(prefix="/api/auth")
router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


def ip_de(request: Request) -> str:
    return request.client.host if request.client else "?"


@public.get("/config")
def config() -> dict:
    """O que a tela precisa saber antes do login. Nada sensível."""
    s = get_settings()
    return {"modo": s.auth_mode, "ambiente": s.app_env}


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    senha: str = Field(max_length=200)


@public.post("/login")
def login(body: LoginIn, request: Request) -> dict:
    s = get_settings()
    if s.auth_mode != "local":
        raise HTTPException(404, "Login próprio não está ativo")
    if not security.limite_login.permite(ip_de(request)):
        raise HTTPException(429, "Muitas tentativas. Aguarde um minuto")
    with db.transaction(f"login:{body.email.strip().lower()[:80]}") as conn:
        u = security.autenticar(conn, body.email, body.senha)
    if u is None:
        # mensagem única: não revela se o e-mail existe, se a senha está errada ou se a conta está bloqueada
        raise HTTPException(401, "E-mail ou senha incorretos, ou conta temporariamente bloqueada")
    return {
        "token": emitir_token(u["id"], u["email"], s),
        "usuario": {"email": u["email"], "nome": u["nome"], "papel": u["papel"]},
    }


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> dict:
    s = get_settings()
    return {"email": user.email, "papel": user.papel, "modo": s.auth_mode, "ambiente": s.app_env}


class SenhaIn(BaseModel):
    atual: str = Field(max_length=200)
    nova: str = Field(max_length=200)


@router.post("/auth/senha")
def trocar_senha(body: SenhaIn, user: User = Depends(current_user)) -> dict:
    if get_settings().auth_mode != "local":
        raise HTTPException(404, "Login próprio não está ativo")
    if erro := security.senha_valida(body.nova):
        raise HTTPException(422, erro)
    with db.transaction(user.actor) as conn:
        if security.autenticar(conn, user.email or "", body.atual) is None:
            raise HTTPException(401, "Senha atual incorreta")
        conn.execute("update app_users set senha_hash = %s where id = %s", (security.hash_senha(body.nova), int(user.id)))
    return {"ok": True}


# ------------------------------------------------------------------ usuários (somente admin; ver security.REGRAS)
COLS = "id, email, nome, papel, ativo, ultimo_login, criado_em, (senha_hash is not null) as tem_senha"
Papel = Literal["admin", "revisor", "operador", "leitor"]


@router.get("/users")
def list_users() -> list[dict]:
    with db.get_pool().connection() as conn:
        return conn.execute(f"select {COLS} from app_users order by email").fetchall()


class UserIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    nome: str | None = Field(default=None, max_length=120)
    papel: Papel
    senha: str | None = Field(default=None, max_length=200)


@router.post("/users", status_code=201)
def create_user(body: UserIn, user: User = Depends(current_user)) -> dict:
    if body.senha and (erro := security.senha_valida(body.senha)):
        raise HTTPException(422, erro)
    with db.transaction(user.actor) as conn:
        if conn.execute("select 1 from app_users where email = %s", (body.email.lower(),)).fetchone():
            raise HTTPException(409, "Já existe um usuário com este e-mail")
        return security.criar_usuario(conn, body.email, body.papel, body.senha, body.nome)


class UserPatch(BaseModel):
    papel: Papel | None = None
    ativo: bool | None = None
    nome: str | None = Field(default=None, max_length=120)
    senha: str | None = Field(default=None, max_length=200)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, user: User = Depends(current_user)) -> dict:
    if body.senha and (erro := security.senha_valida(body.senha)):
        raise HTTPException(422, erro)
    with db.transaction(user.actor) as conn:
        alvo = conn.execute("select * from app_users where id = %s for update", (user_id,)).fetchone()
        if alvo is None:
            raise HTTPException(404, "Usuário não encontrado")
        perde_admin = (
            alvo["papel"] == "admin" and alvo["ativo"] and (body.ativo is False or (body.papel and body.papel != "admin"))
        )
        if (
            perde_admin
            and not conn.execute(
                "select 1 from app_users where papel = 'admin' and ativo and id <> %s limit 1", (user_id,)
            ).fetchone()
        ):
            raise HTTPException(409, "Precisa existir pelo menos um administrador ativo")
        conn.execute(
            """update app_users set papel = coalesce(%s, papel), ativo = coalesce(%s, ativo), nome = coalesce(%s, nome),
                      senha_hash = coalesce(%s, senha_hash),
                      falhas = case when %s then 0 else falhas end,
                      bloqueado_ate = case when %s then null else bloqueado_ate end
                where id = %s""",
            (body.papel, body.ativo, body.nome, security.hash_senha(body.senha) if body.senha else None,
             bool(body.senha), bool(body.senha), user_id),
        )  # fmt: skip
        return conn.execute(f"select {COLS} from app_users where id = %s", (user_id,)).fetchone()
