"""Armazenamento imutável de arquivos originais (RPI, snapshots de evidências).

Regra 6: os originais nunca são sobrescritos. `put_immutable` falha se o caminho
já existir com conteúdo diferente e é idempotente se o conteúdo for o mesmo.
"""

import hashlib
from pathlib import Path
from typing import Protocol

import httpx

from app.config import Settings, get_settings


class StorageConflict(Exception):
    pass


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Storage(Protocol):
    def put_immutable(self, path: str, data: bytes, content_type: str) -> str: ...
    def get(self, path: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _full(self, path: str) -> Path:
        full = (self.root / path).resolve()
        if self.root not in full.parents:
            raise ValueError("caminho fora do diretório de armazenamento")
        return full

    def put_immutable(self, path: str, data: bytes, content_type: str = "") -> str:
        digest = sha256_of(data)
        full = self._full(path)
        if full.exists():
            if sha256_of(full.read_bytes()) != digest:
                raise StorageConflict(f"{path} já existe com conteúdo diferente")
            return digest
        full.parent.mkdir(parents=True, exist_ok=True)
        tmp = full.with_suffix(full.suffix + ".part")
        tmp.write_bytes(data)
        tmp.rename(full)
        full.chmod(0o444)
        return digest

    def get(self, path: str) -> bytes:
        return self._full(path).read_bytes()


class SupabaseStorage:
    """Supabase Storage via REST. Usa a service role key (somente no backend)."""

    def __init__(self, url: str, service_key: str, bucket: str):
        self.base = f"{url.rstrip('/')}/storage/v1/object"
        self.bucket = bucket
        self.headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def put_immutable(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        digest = sha256_of(data)
        r = httpx.post(
            f"{self.base}/{self.bucket}/{path}",
            content=data,
            headers={**self.headers, "Content-Type": content_type, "x-upsert": "false"},
            timeout=120,
        )
        if r.status_code in (400, 409) and "exists" in r.text.lower():
            if sha256_of(self.get(path)) != digest:
                raise StorageConflict(f"{path} já existe com conteúdo diferente")
            return digest
        r.raise_for_status()
        return digest

    def get(self, path: str) -> bytes:
        r = httpx.get(f"{self.base}/authenticated/{self.bucket}/{path}", headers=self.headers, timeout=120)
        r.raise_for_status()
        return r.content


def get_storage(settings: Settings | None = None) -> Storage:
    s = settings or get_settings()
    if s.storage_backend == "supabase":
        if not (s.supabase_url and s.supabase_service_role_key):
            raise RuntimeError("SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY são obrigatórios")
        return SupabaseStorage(s.supabase_url, s.supabase_service_role_key, s.storage_bucket)
    return LocalStorage(s.storage_local_dir)
