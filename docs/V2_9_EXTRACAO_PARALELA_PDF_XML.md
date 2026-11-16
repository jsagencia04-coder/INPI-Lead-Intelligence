# V2.9: extração paralela PDF + XML da Revista do INPI

Estado em 16/11/2026.

| Item | Situação |
|---|---|
| Código | 208 testes do backend aprovados, sendo 4 novos. Frontend: 34 testes, tipos e lint sem problemas |
| Validação com a RPI real 2914 | Concluída no servidor de produção, com o PDF do Volume I e o XML oficial (resultado abaixo) |

## 1. Como funciona

1. **Detecção independente.** O índice da RPI é consultado a cada 10 minutos às terças e quartas (agendamento `rpi-terca`). Cada arquivo é registrado em `rpi_fontes` no momento em que aparece, com o horário de detecção próprio:
   - PDF do Volume I;
   - PDF do Volume II;
   - XML.
2. **O PDF do Volume I começa sozinho.** Assim que ele aparece, o job `rpi.pdf` é executado, sem esperar o XML:
   - baixa o arquivo e guarda o original com sha256;
   - extrai o texto com `pdftotext`, em cerca de 36 s para as 8.068 páginas da RPI 2914;
   - separa as entradas de interesse comercial: oposições, indeferimentos e deferimentos parciais.
3. **Qualificação por estado.** O job `rpi.pdf_importar` processa um lote por estado: **SC primeiro**, depois RS, PR e os demais. Dentro de cada lote, as oposições vêm antes dos indeferimentos. Cada lote:
   - grava os dados pelo mesmo importador do XML, com origem `pdf`;
   - analisa os prazos;
   - aciona a operação semanal, que monta os leads.

   Os primeiros leads de SC saem antes mesmo de o XML existir.
4. **O XML complementa e valida.** Quando sai, o XML é lido pelo fluxo de sempre e acontece o seguinte:
   - substitui o texto das publicações vindas do PDF, que ficam marcadas com `publications.fonte`;
   - traz os dados estruturados: marca, classes e datas;
   - recupera o que o PDF não trouxe;
   - passa pela **conciliação** (`rpi_reconciliacao`): cada processo e despacho fica marcado como `confere`, `so_pdf`, `so_xml` ou `divergente`.

   Divergências e registros que só o PDF trouxe viram tarefa de revisão.
5. **Nada é apagado.** O trecho original de cada entrada do PDF fica em `rpi_pdf_registros`, com a página. O `procurador_fonte` registra quando a informação veio do PDF (`rpi:2914:pdf`).
6. **Quando um arquivo atrasa:**
   - **XML atrasado:** o PDF segue e o XML tem nova tentativa com espera.
   - **PDF indisponível:** o XML segue normalmente e o PDF continua monitorado.
   - **XML já lido:** o PDF é dispensado e fica com a situação "Não necessário".

## 2. Indicadores (página RPI → painel "PDF e XML em paralelo")

O painel usa `GET /api/rpi-fontes?numero=` e mostra:

- data de publicação e momento da detecção;
- detecção, download e processamento de cada arquivo, com a duração de cada etapa;
- registros lidos e registros de interesse em cada fonte;
- publicações por origem;
- conciliação, com a lista do que precisa de revisão;
- leads qualificados por estado, inclusive quantos vieram pelo PDF;
- estado que está sendo processado agora.

## 3. Validação com a RPI 2914 real

| Medida | PDF (Volume I) | XML oficial |
|---|---|---|
| Notificações de oposição (IPAS423) | 481 | 481 |
| Indeferimentos (IPAS024 e IPAS658) | 1.770 | 1.770 |
| Presentes nas duas fontes | **2.251 de 2.251 (100%)** | — |
| Procurador diferente | 1 caso | — |
| Titulares de SC entre oposições e indeferimentos | 171 | — |

As 48 diferenças restantes são despachos de **designação (Protocolo de Madri)**, que o sistema já descarta. Elas não estão nessas seções do Volume I.

## 4. Arquivos

- **Banco:** migration `20261119000019_extracao_paralela_pdf_xml_v29.sql`. Cria:
  - as tabelas `rpi_fontes`, `rpi_pdf_registros` e `rpi_reconciliacao`;
  - a coluna `publications.fonte`;
  - a chave `app_config.rpi_pdf_primeiro` (padrão `true`; com `false`, a leitura antecipada é desligada sem deploy).
- **Backend:**
  - `app/rpi/pdf_parser.py` (novo): leitura do texto, função pura e testada;
  - `app/agents/rpi_pdf.py` (novo): agentes, monitoramento e conciliação;
  - alterados: `app/agents/rpi.py` (descoberta por arquivo, status que não volta atrás, conciliação), `app/rpi/importer.py` (origem), `app/api/comercial_routes.py` (indicadores), `app/jobs/queue.py` e `app/jobs/registry.py`.
- **Imagem:** o `backend/Dockerfile` passa a instalar `poppler-utils`.
- **Frontend:** `components/fontes-rpi.tsx` e a página `rpi`.
- **Testes:** `tests/test_extracao_v29.py` e a fixture `tests/fixtures/marcas_2914_I_trecho.txt`, um trecho no formato real.
