"""Páginas de detalhe do pePI reconstruídas com a marcação real observada em 12/11/2026.

Os dados (processo, marca, situação, petições com protocolo, data, serviço e cliente) foram consultados
no pePI em 12/11/2026 para os processos reais usados nos testes. Nomes de pessoas físicas foram substituídos.
"""

# numero: (marca, situação, titular, procurador, depósito, [(protocolo, data, serviço, descrição, cliente)])
PEPI = {
    "944040470": ("TELEVAULT", "Aguardando manifestação sobre oposição", "CEI - CONTROLES ELETRÔNICOS INTELIGENTES LTDA", None,
                  "10/06/2026", [
                      ("850260447873", "31/08/2026", "332", "Oposição - valor por classe", "ASSA ABLOY BRASIL INDÚSTRIA E COMÉRCIO LTDA"),
                      ("850260280901", "10/06/2026", "389", "Pedido de registro de marca (com especificação pré-aprovada) - valor por classe",
                       "CEI - CONTROLES ELETRÔNICOS INTELIGENTES LTDA"),
                  ]),
    "944032028": ("EPROK", "Aguardando manifestação sobre oposição", "Tprojetto Group LTDA", None, "09/06/2026", [
        ("850260505259", "28/09/2026", "332", "Oposição - valor por classe", "EPIROC AKTIEBOLAG"),
        ("850260279661", "09/06/2026", "389", "Pedido de registro de marca (com especificação pré-aprovada) - valor por classe",
         "Tprojetto Group LTDA"),
    ]),
    "943447259": ("HEALTH ESSENCE", "Aguardando exame de mérito", "JOAO TESTE PEREIRA", None, "19/04/2026", [
        ("850260494593", "23/09/2026", "339", "Manifestação", "JOAO TESTE PEREIRA"),
        ("850260358046", "17/07/2026", "332", "Oposição - valor por classe", "INP INDUSTRIA DE ALIMENTOS LTDA"),
        ("850260183253", "19/04/2026", "389", "Pedido de registro de marca (com especificação pré-aprovada) - valor por classe",
         "JOAO TESTE PEREIRA"),
    ]),
    "942100506": ("Instituto Ela por Elas", "Aguardando exame de mérito", "INSTITUTO ELA POR ELAS", None, "05/12/2025", [
        ("850260077262", "20/02/2026", "332", "Oposição - valor por classe", "GLOBO COMUNICAÇÃO E PARTICIPAÇÕES S.A."),
        ("850260058486", "09/02/2026", "332", "Oposição - valor por classe", "IGREJA APOSTOLICA PLENITUDE DO TRONO DE DEUS"),
        ("850250690571", "05/12/2025", "389", "Pedido de registro de marca (com especificação pré-aprovada) - valor por classe",
         "INSTITUTO ELA POR ELAS"),
    ]),
    "938028383": ("ESCOLA DAS CIDADES", "Aguardando apresentação e exame de recurso contra o indeferimento", "TDBUSINESS LTDA", None,
                  "14/02/2025", [
                      ("850250076465", "14/02/2025", "389", "Pedido de registro de marca (com especificação pré-aprovada) - valor por classe",
                       "TDBUSINESS LTDA"),
                  ]),
    "930647033": ("Enraizador", "Aguardando apresentação e exame de recurso contra o indeferimento", "MARIA TESTE GUERRA", None,
                  "01/06/2023", [
                      ("850230254940", "01/06/2023", "394",
                       "Pedido de registro de marca (com especificação de livre preenchimento) - valor por classe", "MARIA TESTE GUERRA"),
                  ]),
    "930932480": ("EKOA LIFE SCIENCES", "Aguardando apresentação e exame de recurso contra o indeferimento", "IMP BIOINSUMOS LTDA", None,
                  "27/06/2023", [
                      ("850260549596", "21/10/2026", "3000", "Recurso contra indeferimento de pedido de registro de marca - valor por classe",
                       "IMP BIOINSUMOS LTDA"),
                      ("850230600631", "07/12/2023", "339", "Manifestação", "IMP BIOINSUMOS LTDA"),
                      ("850230448655", "18/09/2023", "332", "Oposição - valor por classe", "EKKOA COMERCIO PRODUTOS DE LIMPEZA EIRELI"),
                      ("850230297790", "27/06/2023", "394",
                       "Pedido de registro de marca (com especificação de livre preenchimento) - valor por classe", "IMP BIOINSUMOS LTDA"),
                  ]),
    "939053594": ("XUCRO CORAÇÃO", "Aguardando processamento da concessão do registro de marca", "MV EVENTOS E SERVICOS LTDA", None,
                  "08/05/2025", [
                      ("301260304524", "05/11/2026", "3023", "Concessão de registro de marca e expedição de certificado - Protocolo interno automático",
                       "DIRMA/GABINETE"),
                      ("850250232510", "08/05/2025", "394",
                       "Pedido de registro de marca (com especificação de livre preenchimento) - valor por classe", "MV EVENTOS E SERVICOS LTDA"),
                  ]),
    "943437644": ("Massa Snow Acrilex", "Aguardando exame de mérito", "ACRILEX TINTAS ESPECIAIS S/A", "Vilage Marcas e Patentes  Ltda",
                  "17/04/2026", [
                      ("850260566568", "28/10/2026", "339", "Manifestação", "ACRILEX TINTAS ESPECIAIS S/A"),
                      ("850260315646", "26/06/2026", "332", "Oposição - valor por classe",
                       "VOLKSWAGEN DO BRASIL INDÚSTRIA DE VEÍCULOS AUTOMOTORES LTDA."),
                  ]),
}


def _peticao(i: int, protocolo: str, data: str, servico: str, descricao: str, cliente: str) -> str:
    # Mesma estrutura da linha real: célula de pagamento com tabela aninhada, serviço com descrição em "popup"
    return f"""<tr bgColor=#e9e9e9>
<td align="center" width=10>
<font class=normal>
<font class=normal>
<a class=normal href="javascript:void(0)" onmouseout="hideMe('pgto{i}')" onmouseover="showMe('pgto{i}')" onClick="DisableHide()">
</a>
</font>
<div id='pgto{i}' style="POSITION: absolute; VISIBILITY: hidden;">
<table border=1 borderColor="#006363" cellPadding=5 cellSpacing=0 width="100%">
<tr>
<td align="center" bgColor="#b5d6ad"><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>
<td><font class=normal>Informações do Banco:</font></td><td width="30"><a href="javascript:EnableHide('pgto{i}');"></a></td>
</tr></table></td>
</tr>
<tr><td align=left bgColor="#ffffff"><font class=normal>001 - Banco do Brasil S.A.<br>Data: {data}<br>Valor: R$180.0<br></font></td></tr>
</table>
</div>
</font>
</td>
<td align="center" width=50><font class=normal>{protocolo}</font></td>
<td align="center" width=62><font class=normal>{data}</font></td>
<td align="center" width=10><font class=normal>
-
</font></td>
<td align="center" width=10><font class=normal>
</font></td>
<td align="center" width=30>
<font class=normal>
<a class=normal href="javascript:void(0)" onmouseout="hideMe('{servico}')" onmouseover="showMe('{servico}')" onClick="DisableHide()">
{servico}
</a>
</font>
<div id='{servico}' style="POSITION: absolute; VISIBILITY: hidden;">
<table border=1 borderColor="#006363" cellPadding=5 cellSpacing=0 width="100%">
<tr><td align="center" bgColor="#b5d6ad"><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>
<td><font class=normal>Descrição do Serviço</font></td><td width="30"><a href="javascript:EnableHide('{servico}');"></a></td>
</tr></table></td></tr>
<tr><td align=left bgColor="#ffffff"><font class=normal>
<b>{servico}</b>
{descricao}
</font></td></tr>
</table>
</div>
</td>
<td align="center" width=246><font class=normal>{cliente}</font></td>
<td align="center" width=10><font class=normal>
</font></td>
<td align="center" width=10><font class="normal">&nbsp;
-
</font></td>
</tr>"""


def detalhe_real(numero: str) -> str:
    marca, situacao, titular, procurador, deposito, peticoes = PEPI[numero]
    rep = (
        f'<tr bgColor="#e9e9e9" align="center">\n<td width="20"><font class=normal>Procurador:</font></td>\n'
        f'<td width="400"><font class=normal>{procurador}</font></td>\n</tr>'
        if procurador
        else ""
    )
    linhas = "\n".join(_peticao(i, *p) for i, p in enumerate(peticoes))
    return f"""<html><head></head><body bgColor="#ffffff">
<div id="janelaModalCaptchaDownload" class="janelaModal"><div class="g-recaptcha" data-sitekey="x"></div></div>
<table width="780px" border="0" cellpadding="0" cellspacing="0">
<tr><td align="left" width=120><font class=normal>Nº do Processo:</font></td>
<td align=left valign="middle"><font class=marcador>&nbsp;<b>{numero}</b></font>
<input type="hidden" id="numeroProcesso" name="numeroProcesso" value ="{numero}" /></td></tr>
<tr>
<tr><td align="left"><font class=normal>Marca:</font></td><td align=left><font class=normal>&nbsp;{marca}</font></td></tr>
<tr><td align="left"><font class=normal>Situação:</font></td><td align=left><font class=normal>&nbsp;
{situacao}
</font></td></tr>
<tr><td align="left"><font class=normal>Apresentação:</font></td><td align=left><font class=normal>&nbsp;Nominativa</font></td></tr>
<tr><td align="left"><font class=normal>Natureza:</font></td><td align=left><font class=normal>&nbsp;Produtos e/ou Serviço</font></td></tr>
</table>
<div class="accordions"><div class="accordion-item">
<input type="checkbox" name="accordion" checked='checked' id="accordion-titulares" />
<label for= "accordion-titulares"><font class="titulo">Titulares</font></label>
<div class="accordion-content"><table width="780px"><thead><tr bgcolor="#b5d6ad"><th width="20"><font class=normal></font></th>
<th width="400"><font class=normal>Nome</font></th></tr></thead>
<tbody><tr bgColor="#e9e9e9" align="center"><td width="20"><font class=normal>Titular(1):</font></td>
<td width="400"><font
class=normal>{titular}
</font></td></tr></tbody></table></div></div></div>
<div class="accordions"><div class="accordion-item">
<input type="checkbox" name="accordion" checked='checked' id="accordion-representantes" />
<label for= "accordion-representantes"><font class="titulo">Representante Legal</font></label>
<div class="accordion-content"><table width="780px"><thead><tr bgcolor="#b5d6ad"><th width="20"><font class=normal></font></th>
<th width="400"><font class=normal>Nome</font></th></tr></thead><tbody>
{rep}
</tbody></table></div></div></div>
<div class="accordions"><div class="accordion-item">
<input type="checkbox" name="accordion" checked='checked' id="accordion-datas" />
<label for= "accordion-datas"><font class="titulo">Datas</font></label>
<div class="accordion-content"><table width="780px"><thead><tr bgcolor="#b5d6ad"><th width="260"><font class=normal>Data de Depósito</font></th>
<th width="260"><font class=normal>Data de Concessão</font></th><th width="260"><font class=normal>Data de Vigência</font></th></tr></thead>
<tbody><tr bgColor="#e9e9e9"><th><font class=normal>
{deposito}
</font></th><th><font class=normal>
</font></th><th><font class=normal>
</font></th></tr></tbody></table></div></div></div>
<div class="accordions"><div class="accordion-item">
<input type="checkbox" name="accordion" checked='checked' id="accordion-1" />
<label for= "accordion-1"><font class="titulo">Petições</font>
<font class=normal><a class=normal href="javascript:void(0)" onClick="DisableHide()"></a></font>
</label>
<div class="accordion-content">
<table width="780px">
<thead>
<tr bgcolor="#b5d6ad">
<th width="10"><font class=normal>Pgo</font>
<th width="50"><font class=normal>Protocolo</font>
<th width="62"><font class=normal>Data</font>
<th width="10"><font class=normal>Img</font>
<th width="10">
<th width="30"><font class=normal>Serviço</font>
<th width="246"><font class=normal>Cliente</font>
<th width="10"><font class=normal>Delivery</font>
<th width="10"><font class=normal>Data</font>
<tbody>
{linhas}
</table>
</div>
</div>
</div>
</body></html>"""
