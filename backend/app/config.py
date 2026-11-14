"""Configuração central, lida de variáveis de ambiente (ou arquivo .env)."""

import re
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INLINE_COMMENT = re.compile(r"\s+#.*$")


class Settings(BaseSettings):
    # env_ignore_empty: linhas como "RPI_START_EDITION=" no .env valem como "não definido"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True, populate_by_name=True)

    # Banco: em produção, a connection string do Supabase (Settings > Database).
    database_url: str = "postgresql://postgres:postgres@localhost:5432/inpi"

    # Autenticação
    #   dev      -> sem login (apenas desenvolvimento local)
    #   supabase -> exige JWT do Supabase Auth no header Authorization
    #   local    -> login próprio: usuários e senhas no banco (tabela app_users), sem serviço externo
    auth_mode: Literal["dev", "local", "supabase"] = "dev"
    # Ambiente: demo (testes, aceita dados fictícios e uso sem login) | homologacao | producao.
    # Em homologacao e producao o login é obrigatório e dados fictícios são recusados.
    app_env: Literal["demo", "homologacao", "producao"] = "demo"
    # Assina os tokens do login próprio. Gere com: python -c "import secrets; print(secrets.token_urlsafe(48))"
    app_secret_key: str | None = None
    token_horas: int = 12
    # Primeiro administrador, criado ao iniciar se ainda não houver nenhum usuário.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    supabase_url: str | None = None
    supabase_jwt_secret: str | None = None  # projetos com chave legada HS256
    supabase_service_role_key: str | None = None  # usado pelo Storage (backend apenas)

    # Armazenamento dos arquivos originais da RPI e das evidências
    storage_backend: Literal["local", "supabase"] = "local"
    storage_local_dir: str = "./data/storage"
    storage_bucket: str = "rpi-originais"

    cors_origins: list[str] = ["http://localhost:3000"]

    # RPI (Agentes 01 e 02)
    rpi_index_url: str = "https://revistas.inpi.gov.br/rpi/"
    rpi_user_agent: str = "INPI-Lead-Intelligence/0.2 (coleta semanal da RPI)"
    http_timeout_seconds: float = 300
    # Primeira edição a importar. Vazio = só a edição mais recente quando o banco está vazio.
    rpi_start_edition: int | None = None
    # V2.6: edição mínima OPERACIONAL (coleta, leitura, mapa, indicadores e pipeline). Fonte única: esta variável,
    # gravada em app_config na subida e lida pelo SQL via rpi_edicao_minima(). Edições anteriores ficam só no histórico.
    rpi_edicao_minima: int = Field(2914, ge=1, validation_alias=AliasChoices("RPI_EDICAO_MINIMA", "MIN_RPI_EDITION"))
    rpi_max_editions_per_run: int = 10
    # Ao terminar a leitura da RPI, a SILVANE já monta os leads e distribui o trabalho por estado (SC primeiro).
    rpi_operacao_semanal_auto: bool = True
    # PDFs de marcas somam ~150 MB por semana; o XML oficial (~10 MB) é a fonte estruturada.
    rpi_download_pdf: bool = False
    # alvo  = grava apenas processos com despachos ativos para leads (economia de banco)
    # todos = grava todos os processos da edição
    rpi_import_scope: Literal["alvo", "todos"] = "alvo"

    # Fase 3 — verificação no INPI (pePI). Consulta anônima, com pausa entre requisições.
    pepi_base_url: str = "https://busca.inpi.gov.br/pePI"
    pepi_intervalo_segundos: float = 3.0
    pepi_lote_por_execucao: int = 100
    pepi_reverificar_dias: int = 30

    # Fase 4 — base CNPJ da Receita (dados abertos, WebDAV público)
    cnpj_webdav_url: str = "https://arquivos.receitafederal.gov.br/public.php/webdav"
    cnpj_webdav_token: str = "YggdBLfdninEJX9"  # token público de compartilhamento da Receita
    cnpj_cache_dir: str = "./data/cnpj"  # zips do mês ficam aqui (~8 GB)
    cnpj_mes: str | None = None  # ex.: 2026-10. Vazio = mais recente

    # Fase 4 — pesquisa web com Claude
    anthropic_api_key: str | None = None
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_version: str = "2023-06-01"
    modelo_pesquisa: str = "claude-sonnet-5-5"
    modelo_resumo: str = "claude-haiku-5-5"
    web_search_tool: str = "web_search_20250305"
    pesquisa_max_buscas: int = 4
    pesquisa_lote_por_execucao: int = 20
    pesquisa_refazer_dias: int = 60
    # Teto de gasto semanal com IA (US$). A pesquisa para quando atinge.
    ia_orcamento_semanal_usd: float = 20.0
    # Preços por milhão de tokens (US$) — confira em https://www.anthropic.com/pricing
    preco_pesquisa_in: float = 3.0
    preco_pesquisa_out: float = 15.0
    preco_resumo_in: float = 1.0
    preco_resumo_out: float = 5.0
    preco_busca_web: float = 0.01

    # Fase 4 (gratuito) — leitura dos sites oficiais, sem IA
    site_intervalo_segundos: float = 1.0
    site_lote_por_execucao: int = 200

    # Fase 5 — validação de contatos
    validar_buscar_pagina: bool = True  # confere se o contato aparece na página citada
    validar_dns_mx: bool = True

    # V2.0 — WhatsApp Business Platform (Cloud API oficial). Credenciais ficam SÓ no backend.
    whatsapp_phone_number_id: str | None = None
    whatsapp_business_account_id: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_verify_token: str | None = None  # você inventa; a Meta devolve na verificação do webhook
    whatsapp_app_secret: str | None = None  # assina os webhooks (X-Hub-Signature-256); obrigatório para recebê-los
    whatsapp_template_name: str | None = None
    whatsapp_template_language: str = "pt_BR"
    whatsapp_api_url: str = "https://graph.facebook.com/v23.0"  # confira a versão vigente no painel da Meta
    # Chave geral. false = SIMULAÇÃO: nada sai do sistema, mesmo com credenciais.
    whatsapp_envio_ativo: bool = False
    # Enquanto a regra de consentimento não estiver implantada, só estes números recebem (homologação).
    # Separados por vírgula, formato +5511999998888.
    whatsapp_numeros_teste: str = ""
    whatsapp_limite_por_minuto: int = 10
    whatsapp_limite_por_dia: int = 50

    # V2.5 — provedor do primeiro contato. Só UM provedor envia: manual (padrão), evolution ou meta.
    mensageria_provedor: Literal["manual", "evolution", "meta"] = "manual"
    # Evolution API (instância exclusiva do INPI Agent). A chave é o token DA INSTÂNCIA, nunca a chave global.
    evolution_base_url: str | None = None  # ex.: https://evo-evolution-api.xxxx.easypanel.host
    evolution_instance_name: str = "inpi-agent"
    evolution_api_key: str | None = None
    evolution_webhook_token: str | None = None  # segredo que vai na URL do webhook (?token=...)
    evolution_numero_autorizado: str | None = None  # +55... do número do INPI Agent: envio bloqueado se for outro
    # Duas travas: simulação ligada OU envio desligado = nada sai do sistema.
    evolution_send_enabled: bool = False
    evolution_simulation: bool = True
    # Durante o teste real controlado, só estes números (E.164, separados por vírgula) podem receber.
    evolution_numeros_teste: str = ""
    evolution_timeout_segundos: float = 20.0
    # Como você se apresenta na primeira mensagem (ex.: "Julio, consultor em registro de marcas").
    # Vazio = o rascunho sai com a lacuna [seu nome], que precisa ser preenchida antes de aprovar.
    primeiro_contato_remetente: str | None = None

    # Worker
    worker_id: str = "worker-local"
    worker_poll_seconds: float = 2.0
    job_lock_timeout_minutes: int = 30

    @model_validator(mode="before")
    @classmethod
    def _ignora_comentarios(cls, data):
        """Remove comentários que o Docker (env_file) entrega junto com o valor.

        Ex.: 'CNPJ_MES=   # vazio = mais recente' chega como '# vazio = mais recente'.
        """
        if isinstance(data, dict):
            limpo = {}
            for k, v in data.items():
                if isinstance(v, str):
                    v = v.strip()
                    if v.startswith("#"):
                        continue  # só comentário: vale o padrão
                    v = _INLINE_COMMENT.sub("", v)
                    if v == "":
                        continue
                limpo[k] = v
            return limpo
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()
