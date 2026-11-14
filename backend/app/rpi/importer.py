"""Gravação de uma edição da RPI no banco (Agente 02, parte de persistência).

Tudo roda numa única transação (a do job): ou a edição entra inteira, ou nada.
As escritas são feitas em lote (executemany em pipeline), o que mantém o tempo
baixo mesmo com o banco remoto do Supabase.

Regras de procurador (regra do projeto: ausência só é confirmada no INPI):
  * <procurador> presente na publicação  -> com_procurador (presença sempre vence)
  * ausente e status atual 'desconhecido' -> sem_na_rpi (não confirmado)
  * ausente e status já conhecido        -> mantém (uma publicação sem procurador
                                            não prova que ele deixou de existir)
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from psycopg import Connection
from psycopg.types.json import Jsonb

from app import comercial
from app.rpi.normalize import guess_tipo, normalize_name
from app.rpi.xml_parser import ProcessoRPI

BATCH = 2000


@dataclass
class ImportStats:
    processos_no_xml: int = 0
    processos_importados: int = 0
    publicacoes_novas: int = 0
    oportunidades_elegiveis: int = 0
    oportunidades_descartadas: int = 0
    titulares_unicos: int = 0
    despachos_novos: list[str] = field(default_factory=list)
    por_categoria: Counter = field(default_factory=Counter)
    motivos_descarte: Counter = field(default_factory=Counter)
    por_despacho: Counter = field(default_factory=Counter)
    # V2.6 · auditoria da edição (todos os processos do XML, não só os gravados)
    oposicoes: int = 0
    indeferimentos: int = 0
    representacao: Counter = field(default_factory=Counter)  # nos processos de oposição/indeferimento
    representacao_por_tipo: dict = field(default_factory=dict)
    duplicados: int = 0
    _vistos: set = field(default_factory=set)
    _contados: set = field(default_factory=set)

    def as_json(self) -> dict:
        return {
            "processos_no_xml": self.processos_no_xml,
            "processos_importados": self.processos_importados,
            "publicacoes_novas": self.publicacoes_novas,
            "oportunidades_elegiveis": self.oportunidades_elegiveis,
            "oportunidades_descartadas": self.oportunidades_descartadas,
            "titulares_unicos": self.titulares_unicos,
            "despachos_novos": self.despachos_novos,
            "elegiveis_por_categoria": dict(self.por_categoria),
            "motivos_descarte": dict(self.motivos_descarte),
            "publicacoes_por_despacho": dict(self.por_despacho.most_common()),
            "oposicoes": self.oposicoes,
            "indeferimentos": self.indeferimentos,
            "representacao": dict(self.representacao),
            "representacao_por_tipo": {k: dict(v) for k, v in self.representacao_por_tipo.items()},
            "duplicados_no_xml": self.duplicados,
        }


def _load_catalog(conn: Connection) -> dict[str, dict]:
    rows = conn.execute("select codigo, categoria_comercial, ativo_para_leads from despacho_types").fetchall()
    return {r["codigo"]: r for r in rows}


def _register_new_despachos(conn: Connection, procs: list[ProcessoRPI], catalog: dict, edicao: int) -> list[str]:
    novos = {}
    for p in procs:
        for d in p.despachos:
            if d.codigo and d.codigo not in catalog and d.codigo not in novos:
                novos[d.codigo] = d.nome or d.codigo
    for codigo, nome in novos.items():
        conn.execute(
            """insert into despacho_types (codigo, nome, categoria_comercial, ativo_para_leads, revisar, fonte)
               values (%s, %s, 'outro', false, true, %s) on conflict do nothing""",
            (codigo, nome, f"detectado na RPI {edicao}"),
        )
        conn.execute(
            """insert into review_tasks (entidade, entidade_id, motivo)
               values ('despacho_type', %s, %s)""",
            (codigo, f"Despacho novo na RPI {edicao}: '{nome}'. Classifique a relevância comercial."),
        )
        catalog[codigo] = {"codigo": codigo, "categoria_comercial": "outro", "ativo_para_leads": False}
    return sorted(novos)


# Deferimento com itens excluídos ou indeferidos = deferimento parcial (pode caber recurso). Na RPI nacional não há
# código próprio: o despacho é IPAS029 e o status de cada especificação vem em <lista-classe-nice>/<status>.
PARCIAL_STATUS = ("Excluída", "Indeferida")


def categoria_do_despacho(p: ProcessoRPI, d, catalog: dict) -> str | None:
    cat = catalog.get(d.codigo, {})
    if cat.get("ativo_para_leads"):
        return cat["categoria_comercial"]
    if d.codigo == "IPAS029" and any(n.get("status") in PARCIAL_STATUS for n in p.nice_detalhes):
        return "deferimento_parcial"
    return None


def _load_tracked(conn: Connection) -> set[str]:
    """Processos acompanhados: tudo o que for publicado deles é gravado (recurso, decisão, arquivamento...)."""
    return {r["numero_processo"] for r in conn.execute("select distinct numero_processo from oportunidades_servico")}


def _is_target(p: ProcessoRPI, catalog: dict, tracked: set[str] | None = None) -> bool:
    return (tracked is not None and p.numero in tracked) or any(categoria_do_despacho(p, d, catalog) for d in p.despachos)


def import_processes(
    conn: Connection,
    edition_id: int,
    edicao_numero: int,
    rpi_file_id: int | None,
    processos: Iterable[ProcessoRPI],
    scope: str = "alvo",
) -> ImportStats:
    stats = ImportStats()
    catalog = _load_catalog(conn)
    catalog["__tracked__"] = _load_tracked(conn)  # type: ignore[assignment]
    titulares_vistos: set[str] = set()
    batch: list[ProcessoRPI] = []

    for p in processos:
        stats.processos_no_xml += 1
        if p.numero in stats._vistos:
            stats.duplicados += 1
        stats._vistos.add(p.numero)
        for d in p.despachos:
            stats.por_despacho[d.codigo] += 1
        _auditar(p, catalog, stats)
        batch.append(p)
        if len(batch) >= BATCH:
            _flush(conn, edition_id, edicao_numero, rpi_file_id, batch, catalog, scope, stats, titulares_vistos)
            batch = []
    if batch:
        _flush(conn, edition_id, edicao_numero, rpi_file_id, batch, catalog, scope, stats, titulares_vistos)

    stats.titulares_unicos = len(titulares_vistos)
    return stats


def _status_procurador(p: ProcessoRPI) -> str:
    if p.procurador:
        return "com_procurador"
    return "erro_identificacao" if p.procurador_vazio else "sem_na_rpi"


def _auditar(p: ProcessoRPI, catalog: dict, stats: ImportStats) -> None:
    """Conta oposições e indeferimentos da edição inteira e a representação de cada um (relatório de completude)."""
    for d in p.despachos:
        cat = categoria_do_despacho(p, d, catalog)
        if cat not in ("oposicao_apresentada", "indeferimento") or (p.numero, d.codigo) in stats._contados:
            continue
        stats._contados.add((p.numero, d.codigo))
        if cat == "oposicao_apresentada":
            stats.oposicoes += 1
        else:
            stats.indeferimentos += 1
        sit = comercial.situacao_procurador(_status_procurador(p))
        stats.representacao[sit] += 1
        stats.representacao_por_tipo.setdefault(cat, Counter())[sit] += 1


def _flush(conn, edition_id, edicao, rpi_file_id, batch, catalog, scope, stats, titulares_vistos):
    stats.despachos_novos += _register_new_despachos(conn, batch, catalog, edicao)
    tracked = catalog.get("__tracked__")
    procs = batch if scope == "todos" else [p for p in batch if _is_target(p, catalog, tracked)]
    if not procs:
        return
    fonte = f"rpi:{edicao}"
    numeros = [p.numero for p in procs]

    # Última edição em que cada processo já apareceu: uma edição ANTIGA (importada depois, para o histórico)
    # não pode sobrescrever a titularidade atual.
    ultima_vista = {
        r["numero_processo"]: r["numero"]
        for r in conn.execute(
            """select p.numero_processo, e.numero from processes p join rpi_editions e on e.id = p.last_seen_edition_id
                where p.numero_processo = any(%s)""",
            (numeros,),
        ).fetchall()
    }

    with conn.cursor() as cur:
        # 1. Titulares
        holders = {}
        for p in procs:
            for t in p.titulares:
                norm = normalize_name(t.nome)
                key = f"{norm}|{t.uf or ''}|{t.pais or ''}"
                holders[key] = (t.nome, norm, t.uf, t.pais, guess_tipo(t.nome))
        titulares_vistos.update(holders)
        cur.executemany(
            """insert into holders (nome_original, nome_normalizado, uf, pais, tipo_provavel)
               values (%s, %s, %s, %s, %s) on conflict (holder_key) do nothing""",
            list(holders.values()),
        )
        ids = {
            r["holder_key"]: r["id"]
            for r in conn.execute("select id, holder_key from holders where holder_key = any(%s)", (list(holders),)).fetchall()
        }

        # 2. Processos (sem apagar dados que esta publicação não traz)
        cur.executemany(
            """
            insert into processes as p (
              numero_processo, marca_nome, apresentacao, natureza, classes_nice, nice_detalhes,
              classes_vienna, data_deposito, data_concessao, data_vigencia, apostila, madri,
              numero_inscricao_internacional, procurador_status, procurador_nome, procurador_fonte,
              first_seen_edition_id, last_seen_edition_id)
            values (%(numero)s, %(marca)s, %(apres)s, %(nat)s, %(nice)s, %(nice_det)s, %(vienna)s,
                    %(dep)s, %(conc)s, %(vig)s, %(apost)s, %(madri)s, %(madri_num)s,
                    %(ps)s, %(proc)s, %(fonte)s, %(ed)s, %(ed)s)
            on conflict (numero_processo) do update set
              marca_nome     = coalesce(excluded.marca_nome, p.marca_nome),
              apresentacao   = coalesce(excluded.apresentacao, p.apresentacao),
              natureza       = coalesce(excluded.natureza, p.natureza),
              classes_nice   = case when cardinality(excluded.classes_nice) > 0
                                    then excluded.classes_nice else p.classes_nice end,
              nice_detalhes  = case when jsonb_array_length(excluded.nice_detalhes) > 0
                                    then excluded.nice_detalhes else p.nice_detalhes end,
              classes_vienna = case when cardinality(excluded.classes_vienna) > 0
                                    then excluded.classes_vienna else p.classes_vienna end,
              data_deposito  = coalesce(excluded.data_deposito, p.data_deposito),
              data_concessao = coalesce(excluded.data_concessao, p.data_concessao),
              data_vigencia  = coalesce(excluded.data_vigencia, p.data_vigencia),
              apostila       = coalesce(excluded.apostila, p.apostila),
              madri          = p.madri or excluded.madri,
              numero_inscricao_internacional =
                               coalesce(excluded.numero_inscricao_internacional, p.numero_inscricao_internacional),
              procurador_status = case
                  when excluded.procurador_status = 'com_procurador' then 'com_procurador'
                  when p.procurador_status = 'desconhecido' then excluded.procurador_status
                  else p.procurador_status end,
              procurador_nome = case
                  when excluded.procurador_status = 'com_procurador' then excluded.procurador_nome
                  else p.procurador_nome end,
              procurador_fonte = case
                  when excluded.procurador_status = 'com_procurador' or p.procurador_status = 'desconhecido'
                  then excluded.procurador_fonte else p.procurador_fonte end,
              first_seen_edition_id = coalesce(p.first_seen_edition_id, excluded.first_seen_edition_id),
              last_seen_edition_id = case
                  when (select numero from rpi_editions where id = excluded.last_seen_edition_id)
                     >= coalesce((select numero from rpi_editions where id = p.last_seen_edition_id), 0)
                  then excluded.last_seen_edition_id else p.last_seen_edition_id end
            """,
            [
                {
                    "numero": p.numero,
                    "marca": p.marca_nome,
                    "apres": p.apresentacao,
                    "nat": p.natureza,
                    "nice": p.classes_nice,
                    "nice_det": Jsonb(p.nice_detalhes),
                    "vienna": p.classes_vienna,
                    "dep": p.data_deposito,
                    "conc": p.data_concessao,
                    "vig": p.data_vigencia,
                    "apost": p.apostila,
                    "madri": p.madri,
                    "madri_num": p.numero_inscricao_internacional,
                    "ps": _status_procurador(p),
                    "proc": p.procurador,
                    "fonte": fonte,
                    "ed": edition_id,
                }
                for p in procs
            ],
        )
        stats.processos_importados += len(procs)

        # 3. Titularidade atual = titulares desta publicação
        com_titulares = [p for p in procs if p.titulares and ultima_vista.get(p.numero, 0) <= edicao]
        conn.execute(
            "delete from process_holders where numero_processo = any(%s)",
            ([p.numero for p in com_titulares],),
        )
        cur.executemany(
            "insert into process_holders (numero_processo, holder_id, ordem) values (%s, %s, %s) on conflict do nothing",
            [
                (p.numero, ids[f"{normalize_name(t.nome)}|{t.uf or ''}|{t.pais or ''}"], i)
                for p in com_titulares
                for i, t in enumerate(p.titulares, start=1)
            ],
        )

        # 4. Publicações (idempotente)
        before = conn.execute("select count(*) as n from publications where edition_id = %s", (edition_id,))
        n0 = before.fetchone()["n"]
        cur.executemany(
            """insert into publications (numero_processo, edition_id, rpi_file_id, despacho_codigo, despacho_nome,
                                         texto_complementar, protocolos, procurador_na_publicacao, raw_hash)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (numero_processo, edition_id, despacho_codigo) do nothing""",
            [
                (
                    p.numero,
                    edition_id,
                    rpi_file_id,
                    d.codigo,
                    d.nome,
                    d.texto_complementar,
                    Jsonb(d.protocolos),
                    p.procurador,
                    p.raw_hash,
                )
                for p in procs
                for d in p.despachos
                if d.codigo
            ],
        )
        n1 = conn.execute("select count(*) as n from publications where edition_id = %s", (edition_id,)).fetchone()
        stats.publicacoes_novas += n1["n"] - n0

        # 5. Oportunidades
        status_atual = {
            r["numero_processo"]: r["procurador_status"]
            for r in conn.execute(
                "select numero_processo, procurador_status from processes where numero_processo = any(%s)",
                (numeros,),
            ).fetchall()
        }
        opps = []
        minimo = comercial.edicao_minima()
        for p in procs:
            for d in p.despachos:
                categoria = categoria_do_despacho(p, d, catalog)
                if not categoria:
                    continue
                motivo = None
                if edicao < minimo:
                    motivo = f"fora do corte: RPI anterior à edição mínima operacional ({minimo})"
                elif m := comercial.motivo_procurador(status_atual.get(p.numero)):
                    motivo = m
                elif p.madri:
                    motivo = "Protocolo de Madri"
                elif p.titulares and not any(t.pais == "BR" for t in p.titulares):
                    motivo = "titular estrangeiro"
                opps.append(
                    (
                        p.numero,
                        edition_id,
                        d.codigo,
                        categoria,
                        "descartada" if motivo else "elegivel",
                        motivo,
                    )
                )
                if motivo:
                    stats.oportunidades_descartadas += 1
                    stats.motivos_descarte[motivo] += 1
                else:
                    stats.oportunidades_elegiveis += 1
                    stats.por_categoria[categoria] += 1
        cur.executemany(
            """insert into opportunities (numero_processo, edition_id, despacho_codigo, categoria, status,
                                          motivo_descarte)
               values (%s, %s, %s, %s, %s, %s)
               on conflict (numero_processo, edition_id, despacho_codigo) do update
                 set status = excluded.status, motivo_descarte = excluded.motivo_descarte""",
            opps,
        )

        # 6. Procurador identificado agora invalida oportunidades antigas
        conn.execute(
            """update opportunities o set status = 'descartada',
                      motivo_descarte = 'procurador identificado na RPI ' || %s
                where o.status = 'elegivel' and o.numero_processo = any(%s)
                  and exists (select 1 from processes p where p.numero_processo = o.numero_processo
                                and p.procurador_status = 'com_procurador')""",
            (edicao, numeros),
        )
