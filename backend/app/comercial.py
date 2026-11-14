"""Regras comerciais centralizadas (V2.6).

Uma única fonte para:
  * edição mínima operacional da RPI  (Settings.rpi_edicao_minima → app_config → SQL rpi_edicao_minima())
  * prioridade dos despachos           (1 = oposição apresentada, 2 = indeferimento)  ↔ SQL prioridade_servico()
  * prioridade geográfica              (SC = 1, RS = 2, PR = 3)                        ↔ tabela uf_prioridade
  * situação de representação         (4 estados; só SEM_PROCURADOR_CONFIRMADO prospecta) ↔ SQL procurador_situacao()

Prioridade comercial (o que oferecer) e elegibilidade de envio (se pode mandar WhatsApp) são conceitos independentes:
nada aqui autoriza contato.
"""

from app.config import Settings, get_settings

PRIORIDADE_SERVICO = {"manifestacao_oposicao": 1, "recurso_indeferimento": 2}
PRIORIDADE_CATEGORIA = {"oposicao_apresentada": 1, "indeferimento": 2, "deferimento_parcial": 2}
ROTULO_PRIORIDADE = {1: "Oposição apresentada", 2: "Indeferimento"}

UF_PRIORIDADE = {"SC": 1, "RS": 2, "PR": 3}
UFS_SUL = list(UF_PRIORIDADE)

SITUACAO_PROCURADOR = {
    "com_procurador": "COM_PROCURADOR",
    "sem_confirmado": "SEM_PROCURADOR_CONFIRMADO",
    "sem_na_rpi": "SEM_PROCURADOR_CONFIRMADO",  # ausência no XML oficial lido por inteiro (decisão do usuário, V2.6)
    "erro_identificacao": "ERRO_NA_IDENTIFICACAO",
    "desconhecido": "PROCURADOR_DESCONHECIDO",
}
PROSPECTAVEL = "SEM_PROCURADOR_CONFIRMADO"


def situacao_procurador(status: str | None) -> str:
    return SITUACAO_PROCURADOR.get(status or "", "PROCURADOR_DESCONHECIDO")


def motivo_procurador(status: str | None) -> str | None:
    """Motivo de descarte por representação (None = pode prospectar)."""
    sit = situacao_procurador(status)
    return {
        "COM_PROCURADOR": "possui procurador",
        "ERRO_NA_IDENTIFICACAO": "erro na identificação do procurador",
        "PROCURADOR_DESCONHECIDO": "representação desconhecida",
    }.get(sit)


def edicao_minima(s: Settings | None = None) -> int:
    return (s or get_settings()).rpi_edicao_minima


def dentro_do_corte(numero: int, s: Settings | None = None) -> bool:
    return numero >= edicao_minima(s)


def sincronizar_config(conn, s: Settings | None = None) -> dict | None:
    """Grava a edição mínima configurada no banco e reaplica o corte se ela mudou (idempotente)."""
    minimo = edicao_minima(s)
    atual = conn.execute("select valor from app_config where chave = 'rpi_edicao_minima'").fetchone()
    if atual and int(atual["valor"]) == minimo:
        return None
    conn.execute(
        """insert into app_config (chave, valor) values ('rpi_edicao_minima', %s)
           on conflict (chave) do update set valor = excluded.valor, atualizado_em = now()""",
        (str(minimo),),
    )
    return conn.execute("select aplicar_corte_rpi() r").fetchone()["r"]
