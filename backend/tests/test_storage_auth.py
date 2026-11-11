import time

import jwt
import pytest

from app.auth import decode_token
from app.config import Settings
from app.storage import LocalStorage, StorageConflict


def test_storage_local_imutavel(tmp_path):
    s = LocalStorage(str(tmp_path))
    h = s.put_immutable("rpi/2900/RM2900.zip", b"abc")
    assert s.put_immutable("rpi/2900/RM2900.zip", b"abc") == h  # idempotente
    with pytest.raises(StorageConflict):
        s.put_immutable("rpi/2900/RM2900.zip", b"outro conteudo")
    assert s.get("rpi/2900/RM2900.zip") == b"abc"
    with pytest.raises(ValueError):
        s.put_immutable("../fora.txt", b"x")


def test_jwt_hs256_supabase():
    secret = "segredo-de-teste-com-pelo-menos-32-bytes!!"
    s = Settings(auth_mode="supabase", supabase_jwt_secret=secret)
    tok = jwt.encode(
        {"sub": "u1", "email": "a@b.com", "aud": "authenticated", "exp": time.time() + 60},
        secret,
        algorithm="HS256",
    )
    assert decode_token(tok, s)["email"] == "a@b.com"
    with pytest.raises(jwt.PyJWTError):
        decode_token(jwt.encode({"sub": "u1", "aud": "authenticated"}, "x" * 40, algorithm="HS256"), s)


def test_variavel_vazia_no_env_vale_como_nao_definida(monkeypatch):
    monkeypatch.setenv("RPI_START_EDITION", "")
    assert Settings().rpi_start_edition is None


def test_comentario_do_docker_no_valor_e_ignorado(monkeypatch):
    # docker compose (env_file) entrega o comentário como valor quando o campo está vazio
    monkeypatch.setenv("CNPJ_MES", "# vazio = mais recente (ex.: 2026-10)")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "# sem chave, nada é gasto")
    monkeypatch.setenv("PEPI_INTERVALO_SEGUNDOS", "3        # pausa entre consultas")
    s = Settings()
    assert s.cnpj_mes is None and s.anthropic_api_key is None and s.pepi_intervalo_segundos == 3
