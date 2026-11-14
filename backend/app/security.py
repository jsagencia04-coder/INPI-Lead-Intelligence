"""Usuários, senhas, papéis, política de permissões, checagens de inicialização e limite de taxa."""

import base64
import hashlib
import hmac
import logging
import secrets
import time
from collections import defaultdict, deque

from app.config import Settings

log = logging.getLogger("security")

PAPEIS = ("leitor", "operador", "revisor", "admin")
NIVEL = {p: i for i, p in enumerate(PAPEIS)}
SENHA_MIN = 10
MAX_FALHAS = 5
BLOQUEIO_MINUTOS = 15
_N, _R, _P = 2**14, 8, 1


# ------------------------------------------------------------------ senhas (scrypt, biblioteca padrão)
def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(sal).decode()}${base64.b64encode(h).decode()}"


def confere_senha(senha: str, guardado: str | None) -> bool:
    try:
        alg, n, r, p, sal, h = (guardado or "").split("$")
        if alg != "scrypt":
            return False
        calc = hashlib.scrypt(senha.encode(), salt=base64.b64decode(sal), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


_HASH_FALSO = hash_senha("gasto-de-tempo-constante")  # usado quando o e-mail não existe


def senha_valida(senha: str) -> str | None:
    if len(senha) < SENHA_MIN:
        return f"A senha precisa ter pelo menos {SENHA_MIN} caracteres"
    if senha.isdigit() or senha.isalpha():
        return "A senha precisa misturar letras e números"
    return None


def criar_usuario(conn, email: str, papel: str, senha: str | None, nome: str | None = None) -> dict:
    return conn.execute(
        """insert into app_users (email, nome, papel, senha_hash) values (%s, %s, %s, %s)
           returning id, email, nome, papel, ativo, criado_em""",
        (email.strip().lower(), nome, papel, hash_senha(senha) if senha else None),
    ).fetchone()


def autenticar(conn, email: str, senha: str) -> dict | None:
    """Confere e-mail e senha. Cinco erros seguidos bloqueiam a conta por 15 minutos."""
    u = conn.execute("select * from app_users where email = %s for update", (email.strip().lower(),)).fetchone()
    if u is None or not u["ativo"] or not u["senha_hash"]:
        confere_senha(senha, _HASH_FALSO)  # mesmo tempo de resposta: não revela se o e-mail existe
        return None
    bloqueado = conn.execute("select %s > now() as b", (u["bloqueado_ate"],)).fetchone()["b"] if u["bloqueado_ate"] else False
    if bloqueado:
        return None
    if not confere_senha(senha, u["senha_hash"]):
        conn.execute(
            f"""update app_users set falhas = falhas + 1,
                       bloqueado_ate = case when falhas + 1 >= {MAX_FALHAS} then now() + interval '{BLOQUEIO_MINUTOS} minutes' end
                 where id = %s""",
            (u["id"],),
        )
        return None
    conn.execute("update app_users set falhas = 0, bloqueado_ate = null, ultimo_login = now() where id = %s", (u["id"],))
    return u


def bootstrap_admin(conn, s: Settings) -> bool:
    """Cria o primeiro administrador se não houver nenhum usuário. Nunca altera usuários existentes."""
    if not (s.bootstrap_admin_email and s.bootstrap_admin_password):
        return False
    if conn.execute("select 1 from app_users limit 1").fetchone():
        return False
    erro = senha_valida(s.bootstrap_admin_password)
    if erro:
        raise RuntimeError(f"BOOTSTRAP_ADMIN_PASSWORD: {erro}")
    criar_usuario(conn, s.bootstrap_admin_email, "admin", s.bootstrap_admin_password, "Administrador")
    log.info("primeiro administrador criado: %s", s.bootstrap_admin_email)
    return True


# ------------------------------------------------------------------ política de permissões
# (método, prefixo do caminho, trecho final opcional) -> papel mínimo. A primeira regra que casar vale.
# O que não casar: GET = leitor; qualquer alteração = admin (negar é o padrão).
REGRAS: list[tuple[str, str, str | None, str]] = [
    ("*", "/api/users", None, "admin"),
    ("PATCH", "/api/schedules", None, "admin"),
    ("PATCH", "/api/rpi/despachos", None, "admin"),
    ("POST", "/api/jobs", "/retry", "operador"),
    ("POST", "/api/jobs", None, "admin"),
    ("GET", "/api/audit", None, "revisor"),
    ("GET", "/api/leads-export", None, "operador"),
    ("GET", "/api/contact-central/export", None, "operador"),
    ("GET", "/api/servicos/export", None, "operador"),
    ("GET", "/api/rpi/files", None, "operador"),
    ("PATCH", "/api/leads", None, "revisor"),
    ("POST", "/api/contacts", "/verify", "revisor"),
    ("POST", "/api/contacts", "/consents", "revisor"),
    ("POST", "/api/contacts", "/consent-requests", "operador"),
    ("POST", "/api/consents", "/revoke", "operador"),
    ("POST", "/api/consent-requests", "/close", "operador"),
    ("POST", "/api/holders", "/cnpj", "revisor"),
    ("POST", "/api/holders", "/localizacao", "revisor"),
    ("PUT", "/api/uf-prioridade", None, "admin"),
    ("POST", "/api/rpi-semana", None, "operador"),
    ("POST", "/api/reviews", "/resolve", "revisor"),
    # V2.5 primeiro contato: gerar/editar = operador; aprovar/enviar/rejeitar/reconciliar = revisor
    ("POST", "/api/primeiro-contato", "/rascunho", "operador"),
    ("POST", "/api/primeiro-contato", "/enviar", "revisor"),  # V2.8: o clique aprova e envia
    ("PATCH", "/api/rascunhos", None, "operador"),
    ("POST", "/api/rascunhos", "/abrir-whatsapp", "operador"),
    ("POST", "/api/rascunhos", None, "revisor"),
    ("POST", "/api/wa-mensagens", "/reconciliar", "revisor"),
    # V2.7 modelos: editar textos e remetente = admin (PUT cai no padrão admin); prévia = operador
    ("POST", "/api/wa-modelos", "/previa", "operador"),
    ("POST", "/api/primeiro-contato-respostas", "/vistas", "operador"),
    ("POST", "/api/integracao-whatsapp", "/testar", "operador"),
    ("POST", "/api/integracao-whatsapp", "/desativar-envios", "operador"),  # qualquer operador pode parar tudo
    ("POST", "/api/integracao-whatsapp", "/reativar-envios", "admin"),
    ("POST", "/api/whatsapp/messages", "/cancel", "operador"),
    ("POST", "/api/whatsapp/messages", None, "revisor"),
    ("POST", "/api/whatsapp/template", None, "operador"),
    ("POST", "/api/optout", None, "operador"),
    ("POST", "/api/leads", None, "operador"),
    ("POST", "/api/pipeline", None, "operador"),  # V2.6: adicionar processo ao pipeline
    ("POST", "/api/reports", None, "operador"),
    ("POST", "/api/rpi", None, "operador"),
]


def papel_minimo(metodo: str, caminho: str) -> str:
    for m, prefixo, final, papel in REGRAS:
        if m in ("*", metodo) and (caminho == prefixo or caminho.startswith(prefixo + "/")):
            if final is None or caminho.endswith(final):
                return papel
    return "leitor" if metodo in ("GET", "HEAD", "OPTIONS") else "admin"


def pode(papel: str, metodo: str, caminho: str) -> bool:
    return NIVEL.get(papel, -1) >= NIVEL[papel_minimo(metodo, caminho)]


# ------------------------------------------------------------------ checagens ao iniciar
def problemas_de_configuracao(s: Settings) -> list[str]:
    """Motivos pelos quais a API NÃO deve iniciar neste ambiente."""
    p: list[str] = []
    if s.auth_mode == "local":
        if not s.app_secret_key or len(s.app_secret_key) < 32:
            p.append("AUTH_MODE=local exige APP_SECRET_KEY com pelo menos 32 caracteres")
    if s.app_env in ("homologacao", "producao"):
        if s.auth_mode == "dev":
            p.append(f"APP_ENV={s.app_env} exige login: defina AUTH_MODE=local (ou supabase)")
        if any(o == "*" for o in s.cors_origins):
            p.append("CORS_ORIGINS não pode ser '*' fora do ambiente demo")
    if s.app_env == "producao":
        if ":postgres@" in s.database_url:
            p.append("produção não pode usar a senha padrão do banco ('postgres')")
        if s.whatsapp_envio_ativo and not s.whatsapp_app_secret:
            p.append("envio de WhatsApp ativo exige WHATSAPP_APP_SECRET (webhooks assinados)")
    # V2.5: envio real pela Evolution exige login, webhook protegido e o número autorizado
    if s.mensageria_provedor == "evolution" and s.evolution_send_enabled and not s.evolution_simulation:
        if s.auth_mode == "dev" and s.app_env != "demo":
            p.append("envio real pela Evolution exige login (AUTH_MODE=local ou supabase)")
        if not s.evolution_numero_autorizado:
            p.append("envio real pela Evolution exige EVOLUTION_NUMERO_AUTORIZADO (o número do INPI Agent)")
    if s.evolution_webhook_token is not None and len(s.evolution_webhook_token) < 24:
        p.append("EVOLUTION_WEBHOOK_TOKEN precisa ter pelo menos 24 caracteres")
    return p


ORDEM_AMBIENTE = {"demo": 0, "homologacao": 1, "producao": 2}


def conferir_ambiente(conn, s: Settings) -> None:
    """O ambiente do banco só sobe. Recusa apontar um ambiente inferior para um banco superior."""
    banco = conn.execute("select valor from app_config where chave = 'ambiente'").fetchone()["valor"]
    if ORDEM_AMBIENTE[s.app_env] < ORDEM_AMBIENTE[banco]:
        raise RuntimeError(
            f"Este banco é de '{banco}', mas a aplicação está configurada como '{s.app_env}'. "
            "Não se aponta ambiente de teste para banco real. Ajuste APP_ENV ou DATABASE_URL."
        )
    if s.app_env != banco:
        conn.execute("update app_config set valor = %s, atualizado_em = now() where chave = 'ambiente'", (s.app_env,))


# ------------------------------------------------------------------ limite de taxa (em memória, por processo)
class Limite:
    def __init__(self, maximo: int, janela_segundos: int):
        self.maximo, self.janela = maximo, janela_segundos
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def permite(self, chave: str) -> bool:
        agora = time.monotonic()
        d = self._hits[chave]
        while d and agora - d[0] > self.janela:
            d.popleft()
        if len(d) >= self.maximo:
            return False
        d.append(agora)
        if len(self._hits) > 10_000:  # não cresce sem limite
            self._hits.clear()
        return True

    def limpar(self) -> None:
        self._hits.clear()


limite_login = Limite(10, 60)  # por IP
limite_webhook = Limite(300, 60)  # por IP
