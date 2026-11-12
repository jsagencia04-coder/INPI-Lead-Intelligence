"""Oportunidades de serviço (V2.4): quem SOFREU oposição e quem teve o pedido indeferido.

Pipeline 1 · manifestacao_oposicao   despacho IPAS423 "Notificação de oposição": um terceiro se opôs ao pedido;
                                     o lead é o TITULAR do pedido (quem sofreu a oposição). Quem se opôs é só
                                     informação complementar e nunca vira lead por causa disso.
Pipeline 2 · recurso_indeferimento   IPAS024/IPAS658 (indeferimento), IPAS774 (indeferimento de designação),
                                     IPAS781 e deferimentos com itens excluídos/indeferidos (deferimento parcial).

Fatos usados (nada é presumido):
  * RPI: data da publicação (início do prazo), protocolo e data da oposição (texto do IPAS423), despachos
    posteriores do mesmo processo (notificação de recurso IPAS360, recurso julgado, deferimento, arquivamento...).
  * pePI (Agente de Análise Processual): petições do processo com protocolo, data, serviço e cliente
    (339 = Manifestação; 3000/30001 = Recurso contra indeferimento; 332/3022 = Oposição, cujo cliente é o opositor).

Prazos (estimativa conservadora, sempre com a fonte):
  60 dias (LPI art. 158 §1º para manifestação; art. 212 para recurso), contados a partir do primeiro dia útil após
  a publicação na RPI; vencimento em dia sem expediente prorroga para o primeiro dia útil (LPI arts. 221, 224 e 226;
  orientação "Prazos" do pePI). Dia útil = segunda a sexta, fora da tabela `feriados` (considerar = true).
"""

import re
from datetime import date, timedelta

SERVICO = {
    "oposicao_apresentada": ("manifestacao_oposicao", "oposicao"),
    "indeferimento": ("recurso_indeferimento", "indeferimento"),
    "deferimento_parcial": ("recurso_indeferimento", "deferimento_parcial"),
}
CATEGORIAS = list(SERVICO)
ROTULO_SERVICO = {"manifestacao_oposicao": "Manifestação à oposição", "recurso_indeferimento": "Recurso contra indeferimento"}
PRAZO_DIAS = 60
PROXIMO_FIM_DIAS = 15
ORDEM_CLASSE = {"quente": 0, "morno": 1, "pendente": 2, "historico": 3}

# Despachos posteriores que encerram a oportunidade
ENCERRA_OPOSICAO = {
    "IPAS029": "deferimento do pedido",
    "IPAS024": "indeferimento do pedido",
    "IPAS658": "indeferimento do pedido",
    "IPAS158": "concessão do registro",
    "IPAS139": "arquivamento definitivo",
    "IPAS157": "arquivamento definitivo",
    "IPAS106": "arquivamento definitivo",
    "IPAS289": "arquivamento definitivo",
    "IPAS404": "arquivamento de ofício",
}
ENCERRA_RECURSO = {
    "IPAS235": "recurso julgado (não provido)",
    "IPAS237": "recurso julgado (provido)",
    "IPAS158": "concessão do registro",
    "IPAS139": "arquivamento definitivo",
    "IPAS157": "arquivamento definitivo",
    "IPAS404": "arquivamento de ofício",
}
VALIDAR_POSTERIOR = {"IPAS402": "anulação de despacho", "IPAS403": "anulação de despacho", "IPAS428": "petição não conhecida"}

_OPOSICAO_RE = re.compile(r"(\d{12})\s+de\s+(\d{2})/(\d{2})/(\d{4})")


def _data_br(s: str | None) -> date | None:
    if not s:
        return None
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s.strip())
    return date(int(m[3]), int(m[2]), int(m[1])) if m else None


def oposicao_do_texto(texto: str | None) -> tuple[str | None, date | None]:
    """IPAS423 traz no texto complementar o protocolo e a data da oposição: '850260447873 de 31/08/2026'."""
    m = _OPOSICAO_RE.search(texto or "")
    if not m:
        return None, None
    return m[1], date(int(m[4]), int(m[3]), int(m[2]))


# ------------------------------------------------------------------ prazos
def hoje() -> date:
    return date.today()


def feriados(conn) -> set[date]:
    return {r["data"] for r in conn.execute("select data from feriados where considerar")}


def dia_util(d: date, fer: set[date]) -> date:
    while d.weekday() >= 5 or d in fer:
        d += timedelta(days=1)
    return d


def calcular_prazo(publicacao: date | None, fer: set[date], ref: date, dias: int = PRAZO_DIAS) -> dict:
    if publicacao is None:
        return {"inicio": None, "fim": None, "status": "validar"}
    inicio = dia_util(publicacao + timedelta(days=1), fer)
    fim = dia_util(inicio + timedelta(days=dias - 1), fer)
    restantes = (fim - ref).days
    status = "encerrado" if restantes < 0 else "proximo_fim" if restantes <= PROXIMO_FIM_DIAS else "em_andamento"
    return {"inicio": inicio, "fim": fim, "status": status, "restantes": restantes}


def fonte_prazo(servico: str, rpi: int, publicacao: date | None) -> str:
    base = "LPI art. 158 §1º (manifestação: 60 dias)" if servico == "manifestacao_oposicao" else "LPI art. 212 (recurso: 60 dias)"
    pub = publicacao.strftime("%d/%m/%Y") if publicacao else "data não informada"
    return (
        f"{base}; publicação na RPI {rpi} ({pub}); início no 1º dia útil após a publicação e vencimento prorrogado "
        "para o 1º dia útil (LPI arts. 221, 224 e 226; orientação 'Prazos' do pePI/INPI). Estimativa conservadora: "
        "confirmar no processo antes de oferecer o serviço."
    )


# ------------------------------------------------------------------ sincronização com as oportunidades da RPI
def sincronizar(conn, edition_id: int | None = None, numeros: list[str] | None = None) -> int:
    """Cria/atualiza uma oportunidade de serviço para cada oportunidade da RPI dos pipelines (idempotente)."""
    rows = conn.execute(
        """select o.numero_processo, o.categoria, o.status, o.motivo_descarte, o.edition_id, o.despacho_codigo,
                  e.numero as rpi, e.data_publicacao, pub.texto_complementar
             from opportunities o
             join rpi_editions e on e.id = o.edition_id
             left join publications pub on pub.numero_processo = o.numero_processo and pub.edition_id = o.edition_id
                                       and pub.despacho_codigo = o.despacho_codigo
            where o.categoria = any(%s)
              and (%s::bigint is null or o.edition_id = %s)
              and (%s::text[] is null or o.numero_processo = any(%s))""",
        (CATEGORIAS, edition_id, edition_id, numeros, numeros),
    ).fetchall()
    for r in rows:
        servico, tipo = SERVICO[r["categoria"]]
        prot, data_op = oposicao_do_texto(r["texto_complementar"]) if tipo == "oposicao" else (None, None)
        conn.execute(
            """insert into oportunidades_servico (numero_processo, servico, tipo_decisao, edition_id, rpi_numero,
                         despacho_codigo, data_publicacao, elegivel, motivo_descarte, fundamentacao,
                         oposicao_protocolo, oposicao_data)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (numero_processo, servico, edition_id) do update set
                 elegivel = excluded.elegivel, motivo_descarte = excluded.motivo_descarte,
                 tipo_decisao = case when oportunidades_servico.tipo_decisao = 'indeferimento' then 'indeferimento'
                                     else excluded.tipo_decisao end,
                 fundamentacao = coalesce(excluded.fundamentacao, oportunidades_servico.fundamentacao),
                 oposicao_protocolo = coalesce(excluded.oposicao_protocolo, oportunidades_servico.oposicao_protocolo),
                 oposicao_data = coalesce(excluded.oposicao_data, oportunidades_servico.oposicao_data)""",
            (
                r["numero_processo"], servico, tipo, r["edition_id"], r["rpi"], r["despacho_codigo"], r["data_publicacao"],
                r["status"] == "elegivel", r["motivo_descarte"],
                None if tipo == "oposicao" else r["texto_complementar"], prot, data_op,
            ),
        )  # fmt: skip
    return len(rows)


# ------------------------------------------------------------------ análise processual
def _posteriores(conn, numero: str, rpi: int) -> list[dict]:
    return conn.execute(
        """select pub.despacho_codigo, pub.despacho_nome, pub.texto_complementar, pub.protocolos,
                  e.numero as rpi, e.data_publicacao
             from publications pub join rpi_editions e on e.id = pub.edition_id
            where pub.numero_processo = %s and e.numero > %s
            order by e.numero""",
        (numero, rpi),
    ).fetchall()


def _peticoes(conn, numero: str) -> list[dict]:
    return conn.execute(
        "select * from process_peticoes where numero_processo = %s order by data desc nulls last", (numero,)
    ).fetchall()


def _eh_manifestacao(p: dict) -> bool:
    return (p["servico"] or "").startswith("339") or (p["descricao"] or "").lower().startswith("manifesta")


def _eh_recurso(p: dict) -> bool:
    d = (p["descricao"] or "").lower()
    return (p["servico"] or "").startswith("3000") or (d.startswith("recurso") and "indeferimento" in d)


def _eh_oposicao(p: dict) -> bool:
    return (p["servico"] or "") in ("332", "3022") or (p["descricao"] or "").lower().startswith("oposição")


def analisar_um(conn, op: dict, fer: set[date], ref: date) -> dict:
    numero, servico = op["numero_processo"], op["servico"]
    prazo = calcular_prazo(op["data_publicacao"], fer, ref)
    upd: dict = {
        "prazo_inicio": prazo["inicio"],
        "prazo_fim": prazo["fim"],
        "prazo_status": prazo["status"],
        "prazo_fonte": fonte_prazo(servico, op["rpi_numero"], op["data_publicacao"]),
        "validacao_juridica": False,
        "validacao_motivo": None,
        "medida_status": "nao_verificada",
        "medida_protocolo": None,
        "medida_data": None,
        "medida_fonte": None,
        "decisao_posterior": None,
        "opositor_nome": op["opositor_nome"],
        "opositor_fonte": op["opositor_fonte"],
    }
    validar: list[str] = []
    if op["tipo_decisao"] == "deferimento_parcial":
        validar.append("deferimento parcial: verificar se a exclusão de itens é substantiva e recorrível")
    if prazo["status"] == "validar":
        validar.append("data de publicação ausente: prazo não calculado")

    # 1. Histórico da RPI (despachos posteriores do mesmo processo)
    encerra = ENCERRA_OPOSICAO if servico == "manifestacao_oposicao" else ENCERRA_RECURSO
    for pub in _posteriores(conn, numero, op["rpi_numero"]):
        cod, rpi = pub["despacho_codigo"], pub["rpi"]
        texto = (pub["texto_complementar"] or "").lower()
        if servico == "recurso_indeferimento":
            for pr in pub["protocolos"] or []:
                if (pr.get("servico") or "").startswith("3000") and upd["medida_status"] != "protocolada":
                    upd.update(
                        medida_status="protocolada",
                        medida_protocolo=pr.get("numero"),
                        medida_data=_data_br(pr.get("data")),
                        medida_fonte=f"RPI {rpi}, despacho {cod} ({pub['despacho_nome']}), protocolo {pr.get('numero')}",
                    )
        if cod in encerra and not upd["decisao_posterior"]:
            upd["decisao_posterior"] = f"{encerra[cod]} (RPI {rpi}, {cod})"
        if cod == "IPAS270" and "desistência total" in texto and not upd["decisao_posterior"]:
            upd["decisao_posterior"] = f"desistência total homologada (RPI {rpi})"
        if cod in VALIDAR_POSTERIOR:
            validar.append(f"{VALIDAR_POSTERIOR[cod]} na RPI {rpi}: conferir o andamento")

    # 2. Petições do processo no pePI
    pets = _peticoes(conn, numero)
    if servico == "manifestacao_oposicao":
        if op["oposicao_protocolo"] or pets:
            alvo = next((p for p in pets if _eh_oposicao(p) and p["protocolo"] == op["oposicao_protocolo"]), None)
            alvo = alvo or next(
                (
                    p
                    for p in pets
                    if _eh_oposicao(p) and p["data"] and op["data_publicacao"] and p["data"] <= op["data_publicacao"]
                ),
                None,
            )
            if alvo:
                upd["opositor_nome"] = alvo["cliente"]
                upd["opositor_fonte"] = f"pePI, petição {alvo['protocolo']} de {alvo['data']:%d/%m/%Y} ({alvo['descricao']})"
        desde = op["oposicao_data"] or op["data_publicacao"]
        medida = next((p for p in pets if _eh_manifestacao(p) and p["data"] and desde and p["data"] > desde), None)
    else:
        medida = next(
            (p for p in pets if _eh_recurso(p) and p["data"] and op["data_publicacao"] and p["data"] >= op["data_publicacao"]),
            None,
        )
    if medida and upd["medida_status"] != "protocolada":
        upd.update(
            medida_status="protocolada",
            medida_protocolo=medida["protocolo"],
            medida_data=medida["data"],
            medida_fonte=f"pePI, petição {medida['protocolo']} de {medida['data']:%d/%m/%Y} ({medida['servico']} {medida['descricao']})",
        )
    if upd["medida_status"] != "protocolada":
        ultima = max((p["visto_em"] for p in pets), default=None)
        if ultima and op["data_publicacao"] and ultima.date() >= op["data_publicacao"]:
            upd["medida_status"] = "nao_identificada"
            upd["medida_fonte"] = (
                f"pePI consultado em {ultima:%d/%m/%Y}: nenhuma petição de {'manifestação' if servico == 'manifestacao_oposicao' else 'recurso'} após a publicação"
            )

    # 3. Situação processual da oportunidade
    if upd["medida_status"] == "protocolada" or upd["decisao_posterior"] or prazo["status"] == "encerrado":
        situacao = "historico"
    elif prazo["status"] == "validar":
        situacao = "pendente"
    else:
        situacao = "aberta"
    upd["situacao_processual"] = situacao
    upd["validacao_juridica"] = bool(validar)
    upd["validacao_motivo"] = "; ".join(validar) or None
    return upd


def analisar(conn, numeros: list[str] | None = None, data_ref: date | None = None, so_abertas: bool = False) -> dict:
    """Recalcula prazo, medida, decisão posterior e situação das oportunidades de serviço."""
    ref = data_ref or hoje()
    fer = feriados(conn)
    ops = conn.execute(
        """select * from oportunidades_servico
            where (%s::text[] is null or numero_processo = any(%s))
              and (not %s or situacao_processual <> 'historico')""",
        (numeros, numeros, so_abertas),
    ).fetchall()
    cont: dict[str, int] = {}
    for op in ops:
        upd = analisar_um(conn, op, fer, ref)
        sets = ", ".join(f"{k} = %({k})s" for k in upd)
        conn.execute(f"update oportunidades_servico set {sets}, analisado_em = now() where id = %(id)s", upd | {"id": op["id"]})
        cont[upd["situacao_processual"]] = cont.get(upd["situacao_processual"], 0) + 1
    return {"analisadas": len(ops), "situacao": cont}


# ------------------------------------------------------------------ qualificação comercial (por titular)
def classificar(op: dict, *, contatos_total: int, contato_validado: bool, abordado: bool) -> tuple[str, list[str]]:
    """QUENTE / MORNO / HISTÓRICO / PENDENTE de uma oportunidade de serviço para um titular, com os motivos."""
    servico = ROTULO_SERVICO[op["servico"]]
    motivos = [
        f"{servico}: {'oposição publicada' if op['tipo_decisao'] == 'oposicao' else op['tipo_decisao'].replace('_', ' ')} na RPI {op['rpi_numero']}"
    ]
    if op["situacao_processual"] == "historico":
        if op["medida_status"] == "protocolada":
            motivos.append(
                f"{'Manifestação' if op['servico'] == 'manifestacao_oposicao' else 'Recurso'} já protocolado(a) ({op['medida_fonte']})"
            )
        elif op["decisao_posterior"]:
            motivos.append(f"Decisão posterior: {op['decisao_posterior']}")
        else:
            motivos.append(f"Prazo encerrado em {op['prazo_fim']:%d/%m/%Y}" if op["prazo_fim"] else "Prazo encerrado")
        return "historico", motivos
    if op["situacao_processual"] == "pendente":
        motivos.append("Dados processuais insuficientes para calcular o prazo")
        return "pendente", motivos
    motivos.append(
        f"Prazo estimado até {op['prazo_fim']:%d/%m/%Y}"
        + (" (próximo do encerramento)" if op["prazo_status"] == "proximo_fim" else "")
    )
    if contatos_total == 0:
        motivos.append("Nenhum contato comercial encontrado ainda")
        return "pendente", motivos
    faltas = []
    if op["medida_status"] == "nao_verificada":
        faltas.append("petições ainda não conferidas no INPI (pePI)")
    else:
        motivos.append(
            "Nenhuma "
            + ("manifestação" if op["servico"] == "manifestacao_oposicao" else "petição de recurso")
            + " identificada no pePI"
        )
    if contato_validado:
        motivos.append("Contato comercial validado")
    else:
        faltas.append("contato ainda não validado")
    if abordado:
        faltas.append("titular já abordado pela equipe")
    if op["validacao_juridica"]:
        faltas.append(op["validacao_motivo"] or "necessita validação jurídica")
    if faltas:
        motivos += [f"Falta: {f}" for f in faltas]
        return "morno", motivos
    return "quente", motivos


def melhor(classes: list[str | None]) -> str | None:
    cs = [c for c in classes if c]
    return min(cs, key=ORDEM_CLASSE.__getitem__) if cs else None
