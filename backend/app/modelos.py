"""V2.7 · Três modelos de primeira mensagem, guardados no banco (wa_modelos) e editáveis pelo administrador.

Substituição segura de variáveis: só dados verdadeiros do lead/processo. Valor ausente nunca vira "None" nem texto
inventado: vira uma lacuna entre colchetes ("[marca]"), que gera alerta e impede a aprovação até alguém preencher.
O modelo original nunca é alterado pela personalização: o texto personalizado é uma versão independente (rascunho).

Os modelos servem para adequar a comunicação à oportunidade. Não há rotação, sorteio nem variação artificial.
"""

import re

from app.config import get_settings

VARIAVEIS = {
    "nome_titular": "Nome do titular, como publicado na RPI",
    "marca": "Nome da marca",
    "numero_processo": "Número do processo no INPI",
    "tipo_despacho": "Tipo de despacho (ex.: indeferimento)",
    "edicao_rpi": "Número da edição da RPI",
    "estado": "Estado (UF) do titular",
    "empresa": "Nome da sua empresa (configurado nesta tela)",
    "nome_atendente": "Seu nome (configurado nesta tela)",
}
IMPORTANTES = {"nome_titular", "numero_processo", "edicao_rpi", "nome_atendente", "empresa"}
VAR_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
SUGERIDO = {"manifestacao_oposicao": "MODELO_01", "recurso_indeferimento": "MODELO_02"}
TIPO_DO_MODELO = {"MODELO_01": "oposicao", "MODELO_02": "indeferimento", "MODELO_03": "institucional"}
UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
    "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina",
    "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}  # fmt: skip
TIPO_DESPACHO = {"oposicao": "notificação de oposição", "indeferimento": "indeferimento", "deferimento_parcial": "deferimento parcial"}


class ModeloInvalido(Exception):
    pass


def listar(conn) -> list[dict]:
    return conn.execute("select * from wa_modelos order by codigo").fetchall()


def obter(conn, codigo: str) -> dict:
    m = conn.execute("select * from wa_modelos where codigo = %s", (codigo,)).fetchone()
    if m is None:
        raise ModeloInvalido("Modelo não encontrado")
    return m


def remetente(conn) -> dict:
    cfg = {r["chave"]: r["valor"] for r in conn.execute(
        "select chave, valor from app_config where chave in ('primeiro_contato_atendente','primeiro_contato_empresa')")}  # fmt: skip
    return {
        "nome_atendente": (cfg.get("primeiro_contato_atendente") or get_settings().primeiro_contato_remetente or "").strip(),
        "empresa": (cfg.get("primeiro_contato_empresa") or "").strip(),
    }


def valores(conn, lead: dict | None, op: dict | None) -> dict:
    """Valores verdadeiros disponíveis; ausência = None (nunca inventado)."""
    r = remetente(conn)
    return {
        "nome_titular": (lead or {}).get("titular"),
        "marca": (op or {}).get("marca_nome"),
        "numero_processo": (op or {}).get("numero_processo"),
        "tipo_despacho": TIPO_DESPACHO.get((op or {}).get("tipo_decisao") or ""),
        "edicao_rpi": str(op["rpi_numero"]) if op and op.get("rpi_numero") else None,
        "estado": UF_NOME.get((lead or {}).get("geo_uf") or ""),
        "empresa": r["empresa"] or None,
        "nome_atendente": r["nome_atendente"] or None,
    }


def renderizar(texto: str, vals: dict) -> tuple[str, list[str], dict]:
    """Substitui {{variavel}}. Retorna (texto, alertas, variáveis usadas). Desconhecida ou ausente vira lacuna."""
    alertas: list[str] = []
    usadas: dict = {}

    def troca(m: re.Match) -> str:
        nome = m[1]
        if nome not in VARIAVEIS:
            alertas.append(f"Variável desconhecida {{{{{nome}}}}}: corrija o modelo")
            return f"[{nome}]"
        v = vals.get(nome)
        v = str(v).strip() if v is not None else ""
        usadas[nome] = v or None
        if not v:
            alertas.append(f"Falta {VARIAVEIS[nome].lower()} ({{{{{nome}}}}})" + (" — importante" if nome in IMPORTANTES else ""))
            return f"[{nome.replace('_', ' ')}]"
        return v

    return VAR_RE.sub(troca, texto), alertas, usadas


def sugerido(op: dict | None) -> str:
    return SUGERIDO.get((op or {}).get("servico") or "", "MODELO_03")


def compativel(codigo: str, op: dict | None) -> bool:
    """O institucional serve para qualquer oportunidade; oposição e indeferimento só para a própria finalidade."""
    tipo = TIPO_DO_MODELO.get(codigo)
    if tipo == "institucional":
        return True
    return sugerido(op) == codigo


def salvar(conn, codigo: str, *, nome: str, descricao: str, texto: str, ativo: bool, versao: int, ator: str) -> dict:
    m = conn.execute("select * from wa_modelos where codigo = %s for update", (codigo,)).fetchone()
    if m is None:
        raise ModeloInvalido("Modelo não encontrado")
    if m["versao"] != versao:
        raise ModeloInvalido("Outra pessoa alterou este modelo. Recarregue antes de salvar.")
    desconhecidas = sorted({v for v in VAR_RE.findall(texto) if v not in VARIAVEIS})
    if desconhecidas:
        raise ModeloInvalido("Variáveis desconhecidas: " + ", ".join("{{" + v + "}}" for v in desconhecidas))
    if "SAIR" not in texto.upper():
        raise ModeloInvalido("O modelo precisa manter a opção de descadastro (responder SAIR)")
    m = conn.execute(
        """update wa_modelos set nome = %s, descricao = %s, texto = %s, ativo = %s, versao = versao + 1,
                  atualizado_em = now(), atualizado_por = %s where id = %s returning *""",
        (nome.strip(), descricao.strip(), texto.strip(), ativo, ator, m["id"]),
    ).fetchone()
    conn.execute(
        "insert into wa_modelos_historico (modelo_id, versao, nome, texto, ativo, alterado_por) values (%s,%s,%s,%s,%s,%s)",
        (m["id"], m["versao"], m["nome"], m["texto"], m["ativo"], ator),
    )
    return m


def salvar_remetente(conn, nome_atendente: str, empresa: str) -> dict:
    for chave, valor in (("primeiro_contato_atendente", nome_atendente), ("primeiro_contato_empresa", empresa)):
        conn.execute(
            """insert into app_config (chave, valor) values (%s, %s)
               on conflict (chave) do update set valor = excluded.valor, atualizado_em = now()""",
            (chave, valor.strip()),
        )
    return remetente(conn)
