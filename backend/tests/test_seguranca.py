"""V2.0 Fase 12: SSRF, login próprio, papéis, ambientes e bloqueio de dados fictícios."""

import time

import httpx
import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import db, net_guard, security, validation
from app.config import Settings, get_settings
from app.main import app, create_app
from app.validation import normalize_contact
from tests.test_fases3a7 import importar_rpi, mundo  # noqa: F401

CHAVE = "chave-de-teste-com-mais-de-32-caracteres-ok"
SENHA = "senha-forte-123"


# ------------------------------------------------------------------ SSRF
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/", "http://localhost/", "http://10.0.0.5/", "http://192.168.1.1/admin", "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://0.0.0.0/", "http://100.64.0.1/",
        "ftp://empresa.com.br/", "file:///etc/passwd", "gopher://empresa.com.br/", "http://empresa.com.br:5432/",
        "http://empresa.com.br:8000/", "http://user:senha@empresa.com.br/", "http://db/", "http://api.internal/",
        "http://site.invalid/", "http://example.com/", "http://algo.test/", "http://2130706433/",
    ],
)  # fmt: skip
def test_urls_perigosas_sao_bloqueadas(url):
    with pytest.raises(net_guard.Bloqueado):
        net_guard.checar_url(url)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "192.168.0.10", "::1", "fd00::1", "::ffff:10.0.0.1"])
def test_dns_apontando_para_rede_interna_e_bloqueado(monkeypatch, ip):
    monkeypatch.setattr(net_guard, "resolver", lambda host: ["93.184.216.34", ip])  # um IP público não salva o interno
    with pytest.raises(net_guard.Bloqueado):
        net_guard.checar_url("https://empresa-legitima.com.br/")


def test_redirecionamento_para_endereco_interno_e_bloqueado(monkeypatch):
    chamadas = []

    def handler(req: httpx.Request) -> httpx.Response:
        chamadas.append(str(req.url))
        if req.url.host == "empresa.com.br":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        return httpx.Response(200, text="segredo interno")

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as c, pytest.raises(net_guard.Bloqueado):
        net_guard.get(c, "https://empresa.com.br/")
    assert chamadas == ["https://empresa.com.br/"]  # o endereço interno nunca foi acessado

    # a validação de contatos usa o mesmo guarda e não derruba o job: trata como "não deu para conferir"
    monkeypatch.setattr(validation, "http_transport", httpx.MockTransport(handler))
    contato = {"verificacao": "encontrado", "tipo": "telefone", "valor": "(11) 3333-4444", "valor_normalizado": "+551133334444",
               "fonte_tipo": "web"}  # fmt: skip
    nivel, chec = validation.check_contact(contato, {"url": "https://empresa.com.br/"}, None)
    assert nivel == "formato_ok" and chec["pagina_erro"] == "Bloqueado"


def test_redirecionamento_legitimo_funciona_e_ha_limites():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/":
            return httpx.Response(301, headers={"location": "/contato"})
        if req.url.path == "/loop":
            return httpx.Response(302, headers={"location": "/loop"})
        if req.url.path == "/grande":
            return httpx.Response(200, content=b"x" * 5000)
        return httpx.Response(200, text="Fale conosco")

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as c:
        assert net_guard.get(c, "https://empresa.com.br/").text == "Fale conosco"
        with pytest.raises(net_guard.Bloqueado, match="redirecionamentos"):
            net_guard.get(c, "https://empresa.com.br/loop")
        with pytest.raises(net_guard.Bloqueado, match="grande"):
            net_guard.get(c, "https://empresa.com.br/grande", max_bytes=1000)
    with httpx.Client(follow_redirects=True) as c, pytest.raises(RuntimeError):
        net_guard.get(c, "https://empresa.com.br/")


# ------------------------------------------------------------------ dados fictícios
def test_dominios_de_exemplo_nao_viram_contato():
    for v in ("contato@empresa.invalid", "a@example.com", "x@algo.test", "y@exemplo.com.br", "z@localhost.localdomain.local"):
        assert normalize_contact("email", v) is None, v
    for v in ("https://loja.example/", "site.invalid", "http://127.0.0.1/"):
        assert normalize_contact("site", v) is None, v
    assert normalize_contact("email", "vendas@gamaalimentos.com.br") == "vendas@gamaalimentos.com.br"
    assert normalize_contact("site", "https://www.gamaalimentos.com.br/") == "gamaalimentos.com.br"


def test_banco_recusa_dado_ficticio_fora_do_demo(conn, mundo):  # noqa: F811
    importar_rpi()
    h = conn.execute("select id from holders limit 1").fetchone()["id"]
    ev = conn.execute("insert into evidences (url) values ('https://empresa-real.com.br/') returning id").fetchone()["id"]
    sql = "insert into contacts (holder_id, tipo, valor, valor_normalizado, evidence_id) values (%s, %s, %s, %s, %s)"
    conn.execute(sql, (h, "email", "a@loja.invalid", "a@loja.invalid", ev))  # no demo, passa (é o ambiente de exemplos)
    conn.execute("update app_config set valor = 'homologacao' where chave = 'ambiente'")
    for tipo, valor in (("email", "b@loja.invalid"), ("email", "c@example.com"), ("site", "loja.test"), ("site", "10.0.0.1")):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(sql, (h, tipo, valor, valor, ev))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("insert into evidences (url) values ('https://pagina.example/contato')")
    conn.execute(sql, (h, "email", "ok@empresa-real.com.br", "ok@empresa-real.com.br", ev))  # dado real continua entrando


# ------------------------------------------------------------------ ambientes e inicialização
def test_configuracao_insegura_impede_iniciar():
    def prob(**k):
        return security.problemas_de_configuracao(Settings(_env_file=None, **k))

    assert prob(app_env="demo", auth_mode="dev") == []
    assert any("exige login" in p for p in prob(app_env="homologacao", auth_mode="dev"))
    assert any("exige login" in p for p in prob(app_env="producao", auth_mode="dev"))
    assert any("APP_SECRET_KEY" in p for p in prob(app_env="homologacao", auth_mode="local"))
    assert any("APP_SECRET_KEY" in p for p in prob(auth_mode="local", app_secret_key="curta"))
    assert prob(app_env="homologacao", auth_mode="local", app_secret_key=CHAVE) == []
    assert any("senha padrão" in p for p in prob(app_env="producao", auth_mode="local", app_secret_key=CHAVE))
    seguro = {
        "app_env": "producao",
        "auth_mode": "local",
        "app_secret_key": CHAVE,
        "database_url": "postgresql://u:S3nh4-forte@h/db",
    }
    assert prob(**seguro) == []
    assert any("CORS" in p for p in prob(**seguro, cors_origins=["*"]))
    assert any("WHATSAPP_APP_SECRET" in p for p in prob(**seguro, whatsapp_envio_ativo=True))


def test_api_nao_sobe_em_homologacao_sem_login(monkeypatch):
    monkeypatch.setenv("APP_ENV", "homologacao")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="exige login"), TestClient(create_app()):
            pass
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_ambiente_do_banco_so_sobe(conn):
    def conferir(env):
        with db.transaction("t") as c:
            security.conferir_ambiente(c, Settings(_env_file=None, app_env=env))
        return conn.execute("select valor from app_config where chave = 'ambiente'").fetchone()["valor"]

    assert conferir("demo") == "demo"
    assert conferir("homologacao") == "homologacao"
    with pytest.raises(RuntimeError, match="banco real"):
        conferir("demo")  # aplicação de demonstração não encosta em banco de homologação/produção
    assert conferir("producao") == "producao"
    with pytest.raises(RuntimeError):
        conferir("homologacao")


# ------------------------------------------------------------------ login próprio e papéis
@pytest.fixture
def local(monkeypatch, conn):
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("APP_SECRET_KEY", CHAVE)
    get_settings.cache_clear()
    security.limite_login.limpar()
    with db.transaction("teste") as c:
        for papel in security.PAPEIS:
            security.criar_usuario(c, f"{papel}@empresa-real.com.br", papel, SENHA)
    with TestClient(app) as cliente:
        yield cliente
    monkeypatch.undo()
    get_settings.cache_clear()


def entrar(c, papel, senha=SENHA):
    r = c.post("/api/auth/login", json={"email": f"{papel}@empresa-real.com.br", "senha": senha})
    return {"Authorization": f"Bearer {r.json()['token']}"} if r.status_code == 200 else r


def test_sem_login_nada_abre(local):
    for caminho in ("/api/leads", "/api/dashboard/summary", "/api/contact-central", "/api/whatsapp/status", "/api/office/state",
                    "/api/users", "/api/jobs", "/api/audit"):  # fmt: skip
        assert local.get(caminho).status_code == 401, caminho
    assert local.post("/api/whatsapp/messages", json={"lead_id": 1, "contact_id": 1}).status_code == 401
    assert local.get("/health").status_code == 200  # só a checagem de saúde é pública
    assert local.get("/api/auth/config").json() == {"modo": "local", "ambiente": "demo"}


def test_login_tokens_e_bloqueio(local, conn):
    h = entrar(local, "admin")
    assert local.get("/api/auth/me", headers=h).json()["papel"] == "admin"
    # senha errada e e-mail inexistente dão a MESMA resposta
    r1 = entrar(local, "admin", "errada-123456")
    r2 = local.post("/api/auth/login", json={"email": "ninguem@empresa-real.com.br", "senha": "errada-123456"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()
    # tokens forjados, de outro emissor/chave ou vencidos não entram, e o erro não dá detalhes
    agora = int(time.time())
    for tok in (
        "lixo",
        jwt.encode(
            {"sub": "1", "iss": "inpi-lead-intelligence", "exp": agora + 60}, "outra-chave-com-mais-de-32-caracteres!", "HS256"
        ),
        jwt.encode({"sub": "1", "iss": "inpi-lead-intelligence", "exp": agora - 10}, CHAVE, "HS256"),
        jwt.encode({"sub": "1", "iss": "outro", "exp": agora + 60}, CHAVE, "HS256"),
        jwt.encode({"sub": "1", "iss": "inpi-lead-intelligence"}, CHAVE, "HS256"),
    ):
        r = local.get("/api/leads", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401 and "Signature" not in r.text and "expired" not in r.text
    assert local.get("/api/leads", headers={"Authorization": "Bearer " + jwt.encode({"sub": "1"}, "", "none")}).status_code == 401
    # usuário desativado perde o acesso na hora, mesmo com token ainda válido
    hl = entrar(local, "leitor")
    conn.execute("update app_users set ativo = false where papel = 'leitor'")
    assert local.get("/api/leads", headers=hl).status_code == 403
    # 5 senhas erradas bloqueiam a conta; nem a senha certa entra durante o bloqueio
    for _ in range(5):
        entrar(local, "operador", "errada-123456")
    assert entrar(local, "operador").status_code == 401
    conn.execute("update app_users set bloqueado_ate = now() - interval '1 minute' where papel = 'operador'")
    security.limite_login.limpar()
    assert isinstance(entrar(local, "operador"), dict)
    # limite por IP
    security.limite_login.limpar()
    codigos = [local.post("/api/auth/login", json={"email": "x@y.com.br", "senha": "nada-123456"}).status_code for _ in range(12)]
    assert codigos[:10] == [401] * 10 and codigos[10:] == [429, 429]


def test_papeis_limitam_as_acoes(local, conn):
    h = {p: entrar(local, p) for p in security.PAPEIS}
    hid = conn.execute(
        "insert into holders (nome_original, nome_normalizado) values ('EMPRESA REAL LTDA', 'EMPRESA REAL LTDA') returning id"
    ).fetchone()["id"]
    lead = conn.execute("insert into leads (holder_id, status) values (%s, 'qualificado') returning id", (hid,)).fetchone()["id"]

    def codigos(metodo, caminho, corpo=None):
        return [local.request(metodo, caminho, json=corpo, headers=h[p]).status_code for p in security.PAPEIS]

    # leitura: todos; exportação: operador para cima; auditoria: revisor para cima
    assert codigos("GET", "/api/leads") == [200, 200, 200, 200]
    assert codigos("GET", "/api/contact-central/export?formato=csv") == [403, 200, 200, 200]
    assert codigos("GET", "/api/leads-export?formato=csv") == [403, 200, 200, 200]
    assert codigos("GET", "/api/audit?tabela=leads&registro_id=1") == [403, 403, 200, 200]
    # operar: operador para cima
    assert codigos("POST", f"/api/leads/{lead}/notes", {"texto": "anotação"})[:2] == [403, 201]
    # aprovar lead e preparar WhatsApp: revisor para cima (409/404 = passou da permissão e parou na regra de negócio)
    assert codigos("PATCH", f"/api/leads/{lead}", {"status": "aprovado"})[:3] == [403, 403, 200]
    assert codigos("POST", "/api/whatsapp/messages", {"lead_id": lead, "contact_id": 999999}) == [403, 403, 409, 409]
    # administrar: só admin
    assert codigos("GET", "/api/users") == [403, 403, 403, 200]
    assert codigos("PATCH", "/api/schedules/rpi-descoberta", {"ativo": False}) == [403, 403, 403, 200]
    assert codigos("POST", "/api/jobs", {"tipo": "leads.build", "payload": {}}) == [403, 403, 403, 201]
    novo = {"email": "novo@empresa-real.com.br", "papel": "admin", "senha": SENHA}
    assert codigos("POST", "/api/users", novo) == [403, 403, 403, 201]  # ninguém se promove sozinho
    # rota de alteração nova, sem regra cadastrada, nasce restrita a admin
    assert security.papel_minimo("POST", "/api/rota-que-ainda-nao-existe") == "admin"
    assert security.papel_minimo("DELETE", "/api/leads/1") == "admin"


def test_administracao_de_usuarios(local, conn):
    h = entrar(local, "admin")
    assert (
        local.post("/api/users", json={"email": "a@b.com.br", "papel": "leitor", "senha": "curta"}, headers=h).status_code == 422
    )
    assert local.post("/api/users", json={"email": "a@b.com.br", "papel": "dono"}, headers=h).status_code == 422
    u = local.post("/api/users", json={"email": "Ana@Empresa-Real.com.br", "papel": "leitor", "senha": SENHA}, headers=h).json()
    assert u["email"] == "ana@empresa-real.com.br" and "senha_hash" not in u
    assert local.post("/api/users", json={"email": "ana@empresa-real.com.br", "papel": "leitor"}, headers=h).status_code == 409
    assert all("senha_hash" not in x for x in local.get("/api/users", headers=h).json())
    # o último administrador não pode ser rebaixado nem desativado
    admin = conn.execute("select id from app_users where papel = 'admin'").fetchone()["id"]
    assert local.patch(f"/api/users/{admin}", json={"papel": "leitor"}, headers=h).status_code == 409
    assert local.patch(f"/api/users/{admin}", json={"ativo": False}, headers=h).status_code == 409
    assert local.patch(f"/api/users/{u['id']}", json={"papel": "revisor"}, headers=h).json()["papel"] == "revisor"
    # troca de senha exige a atual
    assert local.post("/api/auth/senha", json={"atual": "errada-123456", "nova": "outra-senha-456"}, headers=h).status_code == 401
    assert local.post("/api/auth/senha", json={"atual": SENHA, "nova": "outra-senha-456"}, headers=h).status_code == 200
    assert isinstance(entrar(local, "admin", "outra-senha-456"), dict)
    # auditoria registra quem fez, sem nunca guardar o hash da senha
    logs = conn.execute("select * from audit_log where tabela = 'app_users' order by id").fetchall()
    assert any(x["ator"] == "user:admin@empresa-real.com.br" for x in logs)
    assert any((x["depois"] or {}).get("senha_alterada") for x in logs)
    assert "scrypt$" not in str(logs)


def test_senhas_e_primeiro_administrador(conn):
    h = security.hash_senha(SENHA)
    assert h.startswith("scrypt$") and SENHA not in h and h != security.hash_senha(SENHA)
    assert (
        security.confere_senha(SENHA, h) and not security.confere_senha("outra", h) and not security.confere_senha(SENHA, "lixo")
    )
    s = Settings(_env_file=None, bootstrap_admin_email="Dono@Empresa-Real.com.br", bootstrap_admin_password=SENHA)
    with db.transaction("t") as c:
        assert security.bootstrap_admin(c, s) is True
        assert security.bootstrap_admin(c, s) is False  # só quando não há nenhum usuário
    u = conn.execute("select * from app_users").fetchall()
    assert len(u) == 1 and u[0]["papel"] == "admin" and u[0]["email"] == "dono@empresa-real.com.br"
    with pytest.raises(RuntimeError), db.transaction("t") as c:
        c.execute("delete from app_users")
        security.bootstrap_admin(
            c, Settings(_env_file=None, bootstrap_admin_email="a@b.com.br", bootstrap_admin_password="fraca")
        )


def test_websocket_do_escritorio_exige_login(local):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), local.websocket_connect("/ws/office"):
        pass
    with pytest.raises(WebSocketDisconnect), local.websocket_connect("/ws/office?token=forjado"):
        pass
    tok = entrar(local, "leitor")["Authorization"].split()[1]
    with local.websocket_connect(f"/ws/office?token={tok}") as ws:
        assert "estado" in ws.receive_json()
