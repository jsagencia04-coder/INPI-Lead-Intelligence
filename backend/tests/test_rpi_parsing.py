import io

from app.rpi.index import parse_index
from app.rpi.normalize import guess_tipo, normalize_name
from app.rpi.xml_parser import iter_rpi
from tests.rpi_helpers import FIX, xml_text


def test_indice_real_da_rpi():
    eds = parse_index((FIX / "rpi_index.html").read_text(encoding="utf-8"))
    assert [e.numero for e in eds] == [2914, 2913]
    e = eds[0]
    assert str(e.data) == "2026-11-10"
    assert e.marcas_xml == "https://revistas.inpi.gov.br/txt/RM2914.zip"
    assert e.marcas_pdfs == [
        "https://revistas.inpi.gov.br/pdf/Marcas2914_I.pdf",
        "https://revistas.inpi.gov.br/pdf/Marcas2914_II.pdf",
    ]


def test_normalizacao_e_tipo():
    assert normalize_name("Indústria  e Comércio GAMA Ltda -ME") == "INDUSTRIA E COMERCIO GAMA LTDA ME"
    assert normalize_name("P. A. Freitas") == "P A FREITAS"
    assert guess_tipo("COMÉRCIO EXEMPLO BETA LTDA") == "PJ"
    assert guess_tipo("A. B. TETA DE OLIVEIRA") == "PJ"  # firma de empresário individual
    assert guess_tipo("ETA TRADING LIMITED") == "PJ"
    assert guess_tipo("FULANO DE TAL EXEMPLO") == "indefinido"  # não presumimos PF


def _procs():
    revista, it = iter_rpi(io.BytesIO(xml_text().encode()))
    return revista, {p.numero: p for p in it}


def test_cabecalho_e_campos():
    revista, procs = _procs()
    assert revista.numero == 2914 and str(revista.data) == "2026-11-10"
    assert len(procs) == 12
    p = procs["945424620"]
    assert (p.marca_nome, p.apresentacao, p.classes_nice) == ("MARCA ALFA", "Nominativa", ["09"])
    assert p.nice_detalhes[0]["status"] == "Pendente" and p.procurador is None
    assert str(p.data_deposito) == "2026-10-02"
    assert procs["945410948"].procurador == "PROCURADORA FICTÍCIA UM"
    assert procs["828886318"].marca_nome is None  # extinção não traz a marca
    assert procs["940001120"].classes_vienna == ["27.5.1"]
    assert procs["823650243"].apostila.startswith("SEM DIREITO")


def test_procurador_de_peticao_nao_e_procurador_do_processo():
    _, procs = _procs()
    p = procs["942334000"]
    assert p.procurador is None
    d185 = next(d for d in p.despachos if d.codigo == "IPAS185")
    assert d185.protocolos[0]["procurador"] == "PROCURADOR DO OPONENTE"
    assert d185.protocolos[0]["requerente"]["nome"] == "INSTITUTO TERCEIRO OPONENTE"


def test_despacho_repetido_e_agrupado():
    _, procs = _procs()
    p = procs["823650243"]
    assert [d.codigo for d in p.despachos] == ["IPAS270"]
    assert [x["numero"] for x in p.despachos[0].protocolos] == ["800260252181", "800260252199"]


def test_madri():
    _, procs = _procs()
    assert procs["940001112"].madri and procs["940001112"].numero_inscricao_internacional == "1234567"
