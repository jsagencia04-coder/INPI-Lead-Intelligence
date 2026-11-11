"""HTML do pePI com a estrutura observada em 10/11/2026 (nomes fictícios)."""

LOGIN = "<html><body>pePI - Pesquisa em Propriedade Industrial <a href='/pePI/servlet/LoginController?action=login'>Continuar....</a></body></html>"


def resultado(numero: str, cod: str, marca: str = "MARCA", titular: str = "TITULAR") -> str:
    return f"""<html><body>RESULTADO DA PESQUISA Nº do Processo: "{numero}"Foram encontrados 1 processos
<table><tr bgcolor="#E0E0E0" class="normal"> <td align="center"> <font class="normal">
<a href="/pePI/servlet/MarcasServletController?Action=detail&amp;CodPedido={cod}" class="visitado"> {numero} </a>
</font> </td> <td align="center"> <font class="normal"> 02/10/2026 </font> </td>
<td align="left"> <font class="normal"> <b> {marca} </b> </font> </td>
<td class="left padding-5"> <font class="normal"> Aguardando prazo de apresentação de oposição </font> </td>
<td class="left"> <font class="normal titular-marcas"> {titular} </font> </td></tr></table></body></html>"""


def nao_encontrado(numero: str) -> str:
    return f"""<html><body><table><tr><td > <b>AVISO: </b> O pedido de registro de marca nº {numero} consta em
nosso banco de dados. Por favor, acesse regularmente a Revista da Propriedade Industrial (RPI).</td></tr></table>
</body></html>"""


def detalhe(
    numero: str,
    marca: str,
    titular: str,
    procurador: str | None = None,
    situacao: str = "Aguardando prazo de apresentação de oposição",
    com_secao_rep: bool = True,
) -> str:
    rep_rows = (
        (
            f'<tr bgColor="#e9e9e9" align="center"> <td width="20"><font class=normal>Procurador:</font></td> '
            f'<td width="400"><font class=normal>{procurador}</font></td> </tr>'
        )
        if procurador
        else ""
    )
    rep = (
        f"""<div class="accordions"><div class="accordion-item">
 <input type="checkbox" name="accordion" checked='checked' id="accordion-representantes" />
 <label for= "accordion-representantes"><font class="titulo">Representante Legal</font></label>
 <div class="accordion-content"> <table width="780px"> <thead> <tr bgcolor="#b5d6ad"> <th width="20"><font class=normal></font></th>
 <th width="400"><font class=normal>Nome</font></th> </tr> </thead> <tbody> {rep_rows} </tbody> </table> </div></div></div>"""
        if com_secao_rep
        else ""
    )
    return f"""<html><head></head><body bgColor="#ffffff">
<div id="janelaModalCaptchaDownload" class="janelaModal"> <div class="tituloModal">Digite o texto da imagem abaixo</div>
<div class="g-recaptcha" data-sitekey="x"></div></div>
<table width="780px" border="0"> <tr> <td align="left" width=120> <font class=normal>Nº do Processo:</font> </td>
<td align=left valign="middle"> <font class=marcador>&nbsp;<b>{numero}</b></font>
<input type="hidden" id="numeroProcesso" name="numeroProcesso" value ="{numero}" /> </td> </tr>
<tr> <tr> <td align="left"> <font class=normal>Marca:</font> </td> <td align=left> <font class=normal>&nbsp;{marca}</font> </td> </tr>
<tr> <td align="left"> <font class=normal>Situação:</font> </td> <td align=left> <font class=normal>&nbsp; {situacao} </font> </td> </tr>
<tr> <td align="left"> <font class=normal>Apresentação:</font> </td> <td align=left> <font class=normal>&nbsp;Nominativa</font> </td> </tr>
<tr> <td align="left"> <font class=normal>Natureza:</font> </td> <td align=left> <font class=normal>&nbsp;Produtos e/ou Serviço</font> </td> </tr>
</table>
<div class="accordions"><div class="accordion-item"><input type="checkbox" id="accordion-titulares" />
<div class="accordion-content"><table><thead><tr><th>x</th></tr></thead><tbody>
<tr bgColor="#e9e9e9" align="center"> <td width="20"><font class=normal>Titular(1):</font></td>
<td width="400"><font class=normal>{titular} </font></td> </tr></tbody></table></div></div></div>
{rep}
<div class="accordions"><div class="accordion-item"><input type="checkbox" checked='checked' id="accordion-datas" />
<div class="accordion-content"> <table width="780px"> <thead> <tr bgcolor="#b5d6ad"> <th>Data de Depósito</th>
<th>Data de Concessão</th><th>Data de Vigência <div id='helpdatavigencia'><table><tr><td>Leia-me</td></tr></table></div></th>
</tr> </thead> <tbody> <tr bgColor="#e9e9e9"><td align="center"><font class=normal>02/10/2026</font></td>
<td align="center"><font class=normal></font></td><td align="center"><font class=normal></font></td></tr></tbody></table></div></div></div>
<div class="accordions"><div class="accordion-item"><input type="checkbox" id="accordion-2" />
<div class="accordion-content"><table><thead><tr><th>RPI</th></tr></thead><tbody> <tr bgColor=#e9e9e9>
<td align="center" width=28><font class=normal>2914</font></td> <td align="center" width=55><font class=normal><b>10/11/2026</b></font></td>
<td align="center" width=74> <font class=normal> Publicação de pedido de registro para oposição (exame formal concluído) </font> </td>
<td align=center width=10> <font class=normal> - </font> </td> <td align=center width=10> <font class=normal> - </font> </td>
<td align=left width=623> </td></tr></tbody></table></div></div></div>
</body></html>"""


BLOQUEIO = "<html><body><div class='g-recaptcha'></div>Acesso temporariamente bloqueado</body></html>"
