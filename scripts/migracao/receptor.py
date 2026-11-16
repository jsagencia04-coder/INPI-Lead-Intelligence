"""Receptor temporário da migração (roda no DESTINO, na imagem da api do INPI Agent).

Recebe por HTTPS (atrás do proxy do Painel ICP, em /_migracao/) os arquivos enviados pela origem e restaura o banco e
os arquivos persistentes. Protegido por token (cabeçalho X-Token). Não guarda nada fora de /migracao e do volume de
dados. Deve ser removido depois do corte.

    PUT  /_migracao/arquivo/<nome>   corpo = arquivo (aceita chunked)  → {bytes, sha256}
    GET  /_migracao/status                                             → arquivos recebidos
    POST /_migracao/restaurar-banco                                    → restaura e compara com o manifesto
    POST /_migracao/restaurar-banco-evo                                → idem para o banco da Evolution
                                                                         (evo_manifesto.json, DATABASE_URL_EVO)
    POST /_migracao/restaurar-arquivos                                 → extrai dados.tar.gz no volume de dados
"""

import hashlib
import hmac
import json
import os
import re
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg

TOKEN = os.environ["MIGRACAO_TOKEN"]
DIR = os.environ.get("MIGRACAO_DIR", "/migracao")
DADOS = os.environ.get("DADOS_DIR", "/srv/backend/data")
DB = os.environ["DATABASE_URL"]
LOCK = threading.Lock()
NOME_OK = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


def restaurar_banco(manifesto: str = "manifesto.json", db: str = DB) -> dict:
    man = json.load(open(f"{DIR}/{manifesto}"))
    sc = man.get("schema", "public")
    with psycopg.connect(db) as conn:
        with conn.transaction():
            conn.execute("set session_replication_role = replica")  # sem gatilhos nem checagem de FK durante a carga
            tabelas = [t["tabela"] for t in man["tabelas"]]
            existentes = {r[0] for r in conn.execute("select tablename from pg_tables where schemaname = %s", (sc,))}
            faltando = sorted(set(tabelas) - existentes)
            if faltando:
                raise RuntimeError(f"tabelas da origem ausentes no destino: {faltando}")
            conn.execute("truncate " + ", ".join(f'"{sc}"."{t}"' for t in tabelas) + " restart identity cascade")
            for t in man["tabelas"]:
                cols = ", ".join(f'"{c}"' for c in t["colunas"])
                with open(f"{DIR}/{t['arquivo']}", "rb") as f, conn.cursor().copy(
                    f'copy "{sc}"."{t["tabela"]}" ({cols}) from stdin (format binary)'
                ) as cp:
                    while chunk := f.read(1 << 20):
                        cp.write(chunk)
            for s in man["sequencias"]:  # sequências exatamente como na origem
                conn.execute("select setval(%s, %s, %s)", (s["nome"], s["valor"], s["chamada"]))
            conn.execute("set session_replication_role = origin")
        cont = {}
        for t in man["tabelas"]:
            cont[t["tabela"]] = conn.execute(f'select count(*) from "{sc}"."{t["tabela"]}"').fetchone()[0]
    diverg = {t["tabela"]: [t["linhas"], cont[t["tabela"]]] for t in man["tabelas"] if t["linhas"] != cont[t["tabela"]]}
    return {"tabelas": len(cont), "linhas": sum(cont.values()), "divergencias": diverg, "ok": not diverg}


def restaurar_arquivos() -> dict:
    n = 0
    with tarfile.open(f"{DIR}/dados.tar.gz", "r|gz") as tar:
        for m in tar:
            if m.name.startswith("/") or ".." in m.name.split("/"):
                continue
            tar.extract(m, DADOS, filter="data")
            n += 1
    return {"itens": n}


class H(BaseHTTPRequestHandler):
    def _ok(self):
        return hmac.compare_digest(self.headers.get("X-Token", ""), TOKEN)

    def _json(self, code, obj):
        b = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _corpo(self):
        if self.headers.get("transfer-encoding", "").lower() == "chunked":
            while True:
                tam = int(self.rfile.readline().split(b";")[0].strip(), 16)
                if tam == 0:
                    self.rfile.readline()
                    return
                yield self.rfile.read(tam)
                self.rfile.readline()
        rest = int(self.headers.get("content-length", 0))
        while rest > 0:
            b = self.rfile.read(min(rest, 1 << 20))
            if not b:
                return
            rest -= len(b)
            yield b

    def do_PUT(self):
        if not self._ok():
            return self._json(403, {"erro": "token"})
        nome = self.path.removeprefix("/_migracao/arquivo/")
        if not NOME_OK.match(nome):
            return self._json(400, {"erro": "nome"})
        h, n = hashlib.sha256(), 0
        with open(f"{DIR}/{nome}.parcial", "wb") as f:
            for b in self._corpo():
                f.write(b)
                h.update(b)
                n += len(b)
        os.replace(f"{DIR}/{nome}.parcial", f"{DIR}/{nome}")
        self._json(200, {"arquivo": nome, "bytes": n, "sha256": h.hexdigest()})

    def do_GET(self):
        if not self._ok():
            return self._json(403, {"erro": "token"})
        self._json(200, {"arquivos": {f: os.path.getsize(f"{DIR}/{f}") for f in sorted(os.listdir(DIR))}})

    def do_POST(self):
        if not self._ok():
            return self._json(403, {"erro": "token"})
        acoes = {"/_migracao/restaurar-banco": restaurar_banco, "/_migracao/restaurar-arquivos": restaurar_arquivos,
                 "/_migracao/restaurar-banco-evo": lambda: restaurar_banco("evo_manifesto.json", os.environ["DATABASE_URL_EVO"])}
        if self.path not in acoes:
            return self._json(404, {"erro": "rota"})
        with LOCK:
            try:
                self._json(200, acoes[self.path]())
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"erro": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):  # sem corpo nem token nos logs
        print(self.command, self.path.split("?")[0], flush=True)


if __name__ == "__main__":
    os.makedirs(DIR, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", 8199), H).serve_forever()
