"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Building2, CheckCircle2, Download, ExternalLink, Flame, Gavel, MapPin, MessageCircle, Newspaper, Search, Sparkles, Users, X } from "lucide-react";
import { BrasilMap } from "@/components/brasil-map";
import { BarList, SERIE } from "@/components/charts";
import { Secao } from "@/components/kpi-card";
import { ErrorBox, PageHeader } from "@/components/page-header";
import { Select } from "@/components/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/components/use-api";
import { api, apiDownload } from "@/lib/api";
import { BRASIL_UFS } from "@/lib/brasil-geo";
import { categoriaLabel, fmtDay } from "@/lib/format";
import { ETAPAS } from "@/lib/pipeline";
import { LOCALIZACAO, TEMPERATURA, type IndicadoresUF, type Mapa, type PainelUF } from "@/lib/territorio";
import { cn } from "@/lib/utils";
import { formatWhats } from "@/lib/whatsapp";
import type { Paged } from "@/lib/types";

const NOME = Object.fromEntries([...BRASIL_UFS.map((u) => [u.uf, u.nome]), ["PENDENTE", "Localização pendente"]]);
const METRICAS: Record<string, { rotulo: string; campo: keyof IndicadoresUF }> = {
  leads: { rotulo: "Leads", campo: "leads" },
  quentes: { rotulo: "Leads quentes", campo: "quentes" },
  oposicoes_apresentadas: { rotulo: "Oposições apresentadas", campo: "oposicoes_apresentadas" },
  com_contato_validado: { rotulo: "Com contato validado", campo: "com_contato_validado" },
  novos_ultima_rpi: { rotulo: "Novos na última RPI", campo: "novos_ultima_rpi" },
};
const PAGE = 25;
const n = (v: number | null | undefined) => Number(v ?? 0).toLocaleString("pt-BR");
const NOME_ETAPA = Object.fromEntries(ETAPAS.map((e) => [e.id, e.nome]));

type LeadLinha = {
  id: number; holder_id: number; titular: string; marcas: string | null; processos: string | null; geo_uf: string | null; geo_municipio: string | null;
  geo_status: string; geo_fonte: string | null; categoria_principal: string | null; ultima_publicacao: string | null; temperatura: string | null;
  temperatura_motivos: string[]; score: number | null; whatsapp: string | null; whatsapp_status: string | null; n_validados: number; n_contatos: number;
  pipeline_stage: string; cnpj: string | null;
};

function Indicador({ icon: I, rotulo, valor, sub, cor }: { icon: typeof Users; rotulo: string; valor: string; sub?: string; cor: string }) {
  return (
    <div className="rounded-xl border bg-card p-3">
      <div className="flex items-center gap-2 text-[11px] font-medium text-muted-foreground"><span className={cn("grid size-6 place-items-center rounded-md", cor)}><I className="size-3.5" /></span>{rotulo}</div>
      <div className="num mt-1 text-xl font-semibold">{valor}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

function Temp({ t, motivos }: { t: string | null; motivos?: string[] }) {
  const x = TEMPERATURA[t ?? "em_pesquisa"];
  return (
    <span title={motivos?.length ? `Motivos:\n• ${motivos.join("\n• ")}` : undefined}
      className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", x.classe)}>
      <span className={cn("size-1.5 rounded-full", x.ponto)} />{x.rotulo}
    </span>
  );
}

function LocalizacaoPendente({ holderId, onFeito }: { holderId: number; onFeito: () => void }) {
  const [uf, setUf] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  return (
    <span className="inline-flex items-center gap-1">
      <Select value={uf} onChange={setUf} placeholder="UF…" options={Object.fromEntries(BRASIL_UFS.map((u) => [u.uf, u.uf]))} className="h-7 w-20 text-xs" />
      <Button size="sm" variant="outline" className="h-7 px-2 text-xs" disabled={!uf}
        onClick={() => api(`/api/holders/${holderId}/localizacao`, { method: "POST", body: JSON.stringify({ uf }) }).then(onFeito).catch((e) => setErro(String(e.message ?? e)))}>
        Confirmar
      </Button>
      {erro && <span className="text-[10px] text-destructive">{erro}</span>}
    </span>
  );
}

function Painel({ uf, q, onFechar }: { uf: string; q: string; onFechar: () => void }) {
  const { data: p, error } = useApi<PainelUF>(`/api/mapa/${uf}?${q}`);
  const i = p?.indicadores;
  const ordem = p?.info?.ordem;
  return (
    <div className="entrar space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="eyebrow text-primary">{p?.info?.regiao ?? (uf === "PENDENTE" ? "Sem UF" : "")}</div>
          <h2 className="text-xl font-semibold">{NOME[uf]} {uf !== "PENDENTE" && <span className="text-muted-foreground">({uf})</span>}</h2>
          {ordem && ordem <= 3 && <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-semibold text-amber-800"><Sparkles className="size-3" />Prioridade {ordem === 1 ? "máxima" : "alta"} · {ordem}º na fila</span>}
          {ordem && ordem > 3 && <span className="mt-1 inline-block text-[11px] text-muted-foreground">{ordem}º na ordem de processamento</span>}
        </div>
        <button onClick={onFechar} className="rounded-lg p-1.5 hover:bg-accent" aria-label="Fechar estado"><X className="size-4" /></button>
      </div>
      <ErrorBox error={error} />
      {!i ? <div className="h-64 animate-pulse rounded-xl bg-muted" /> : (
        <>
          <div className="grid grid-cols-2 gap-2">
            <Indicador icon={Users} rotulo="Leads identificados" valor={n(i.leads)} sub={`${n(i.titulares)} titulares · ${n(i.empresas)} empresas`} cor="bg-indigo-500/10 text-indigo-600" />
            <Indicador icon={Gavel} rotulo="Oposições apresentadas" valor={n(i.oposicoes_apresentadas)} sub="categoria A" cor="bg-rose-500/10 text-rose-600" />
            <Indicador icon={Newspaper} rotulo="Publicados p/ oposição" valor={n(i.publicados_oposicao)} sub="categoria B" cor="bg-amber-500/10 text-amber-700" />
            <Indicador icon={Sparkles} rotulo="Novos na última RPI" valor={n(i.novos_ultima_rpi)} cor="bg-sky-500/10 text-sky-600" />
            <Indicador icon={MessageCircle} rotulo="Contato validado" valor={n(i.com_contato_validado)} cor="bg-emerald-500/10 text-emerald-600" />
            <Indicador icon={Flame} rotulo="Prioritários (quentes)" valor={n(i.quentes)} sub={`${n(i.mornos)} mornos · ${n(i.em_pesquisa)} em pesquisa`} cor="bg-rose-500/10 text-rose-600" />
          </div>
          <div>
            <div className="mb-1 flex justify-between text-xs"><span className="font-medium">Situação comercial</span><span className="text-muted-foreground">{n(i.em_analise)} em análise · {n(i.trabalhados)} já trabalhados</span></div>
            <div className="flex h-2 overflow-hidden rounded-full bg-muted">
              <div style={{ width: `${i.leads ? (i.em_analise / i.leads) * 100 : 0}%`, background: SERIE(1) }} />
              <div style={{ width: `${i.leads ? (i.trabalhados / i.leads) * 100 : 0}%`, background: SERIE(3) }} />
            </div>
            <div className="mt-2 text-[11px] text-muted-foreground">
              Localização: <b className="text-foreground">{n(i.localizacao_confirmada)}</b> confirmada(s) pela Receita ou por pessoa · <b className="text-foreground">{n(i.localizacao_estimada)}</b> estimada(s) pela RPI
            </div>
          </div>
          <div>
            <div className="mb-2 text-sm font-semibold">Leads prioritários para abordagem</div>
            {p.prioritarios.length === 0 ? <p className="text-sm text-muted-foreground">Nenhum lead neste filtro.</p> : (
              <ul className="space-y-1.5">
                {p.prioritarios.map((l) => (
                  <li key={l.id}>
                    <Link href={`/leads/${l.id}`} className="flex items-center gap-2 rounded-lg border p-2 text-sm transition-colors hover:bg-accent/40">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{l.titular}</span>
                        <span className="block truncate text-[11px] text-muted-foreground">
                          {l.marcas ?? "—"} · {l.municipio ?? "município não informado"} · {categoriaLabel[l.categoria_principal ?? ""] ?? "—"}
                        </span>
                      </span>
                      {l.whatsapp && <MessageCircle className={cn("size-4", l.whatsapp_status === "candidato" ? "text-amber-500" : "text-[#25D366]")} />}
                      <Temp t={l.temperatura} motivos={l.temperatura_motivos} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {p.municipios.length > 0 && uf !== "PENDENTE" && (
            <div><div className="mb-2 text-sm font-semibold">Municípios</div><BarList cor={SERIE(1)} itens={p.municipios.map((m) => ({ chave: m.chave, rotulo: m.chave, n: m.n }))} /></div>
          )}
          {p.historico.length > 0 && (
            <div>
              <div className="mb-2 text-sm font-semibold">Histórico por edição da RPI</div>
              <table className="w-full text-xs">
                <thead className="text-muted-foreground"><tr><th className="py-1 text-left font-medium">RPI</th><th className="text-right font-medium">Leads</th><th className="text-right font-medium">Opos. A</th><th className="text-right font-medium">Publ. B</th><th className="text-right font-medium">Quentes</th><th className="text-right font-medium">Contatos feitos</th></tr></thead>
                <tbody>{p.historico.map((h) => (
                  <tr key={h.numero} className="border-t"><td className="py-1">{h.numero} <span className="text-muted-foreground">{fmtDay(h.data_publicacao)}</span></td><td className="num text-right">{h.leads}</td><td className="num text-right">{h.oposicoes_apresentadas}</td><td className="num text-right">{h.publicados_oposicao}</td><td className="num text-right">{h.quentes}</td><td className="num text-right">{h.abordagens}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Ranking({ estados, metrica, onSelect }: { estados: IndicadoresUF[]; metrica: string; onSelect: (uf: string) => void }) {
  const campo = METRICAS[metrica].campo;
  const top = [...estados].filter((e) => Number(e[campo]) > 0).sort((a, b) => Number(b[campo]) - Number(a[campo])).slice(0, 10);
  if (!top.length) return <p className="py-8 text-center text-sm text-muted-foreground">Nenhum estado com {METRICAS[metrica].rotulo.toLowerCase()} neste filtro.</p>;
  const max = Number(top[0][campo]) || 1;
  return (
    <ul className="space-y-2">
      {top.map((e, k) => (
        <li key={e.uf}>
          <button onClick={() => onSelect(e.uf)} className="w-full text-left">
            <div className="mb-1 flex justify-between text-sm"><span><span className="num mr-2 text-xs text-muted-foreground">{k + 1}</span>{NOME[e.uf]}</span><b className="num">{n(Number(e[campo]))}</b></div>
            <div className="h-2 rounded-full bg-muted"><div className="h-full rounded-full" style={{ width: `${(Number(e[campo]) / max) * 100}%`, background: SERIE(1) }} /></div>
          </button>
        </li>
      ))}
    </ul>
  );
}

function MapaInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const uf = sp.get("uf");
  const [edicao, setEdicao] = useState("");
  const [categoria, setCategoria] = useState(sp.get("categoria") ?? "");
  const [temperatura, setTemperatura] = useState(sp.get("temperatura") ?? "");
  const [desde, setDesde] = useState("");
  const [ate, setAte] = useState("");
  const [metrica, setMetrica] = useState("leads");
  const [modo, setModo] = useState<"absoluto" | "normalizado">("absoluto");
  const [busca, setBusca] = useState("");
  const [offset, setOffset] = useState(0);

  const f = new URLSearchParams();
  if (edicao) f.set("edicao", edicao);
  if (categoria) f.set("categoria", categoria);
  if (temperatura) f.set("temperatura", temperatura);
  if (desde) f.set("desde", desde);
  if (ate) f.set("ate", ate);
  const { data: m, error, reload } = useApi<Mapa>(`/api/mapa?${f}`, 60000);
  const { data: eds } = useApi<{ edicoes: { numero: number; data_publicacao: string | null }[] }>("/api/rpi-semana");

  const lf = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (uf) lf.set("geo_uf", uf);
  if (edicao) lf.set("edicao", edicao);
  if (categoria) lf.set("categoria", categoria);
  if (temperatura) lf.set("temperatura", temperatura);
  if (busca.trim()) lf.set("q", busca.trim());
  const leads = useApi<Paged<LeadLinha>>(`/api/leads?${lf}`);

  const selecionar = (u: string | null) => {
    const p = new URLSearchParams(sp);
    if (u) p.set("uf", u); else p.delete("uf");
    setOffset(0);
    router.replace(`${pathname}?${p}`, { scroll: false });
  };
  const campo = METRICAS[metrica].campo;
  const valor = (e: IndicadoresUF) => (modo === "normalizado" ? (e.leads ? (Number(e[campo]) / e.leads) * 100 : 0) : Number(e[campo]));
  const exportar = (formato: string) => {
    const p = new URLSearchParams(lf); p.delete("limit"); p.delete("offset"); p.delete("q"); p.set("formato", formato);
    apiDownload(`/api/leads-export?${p}`, `leads-${uf ?? "brasil"}.${formato}`);
  };

  return (
    <>
      <PageHeader title="Mapa de Oportunidades – Brasil" description={m ? (m.processado ? `${n(m.total)} lead(s) no filtro · última RPI processada: nº ${m.ultima_edicao}` : "Nenhuma RPI processada ainda: o mapa mostra “sem dados”, não zero.") : undefined}>
        <Button variant="outline" onClick={() => exportar("xlsx")}><Download className="size-4" /> Excel</Button>
        <Button variant="outline" onClick={() => exportar("csv")}><Download className="size-4" /> CSV</Button>
      </PageHeader>
      <ErrorBox error={error} />

      <div className="surface mb-4 flex flex-wrap items-end gap-3 p-3">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Edição da RPI<Select value={edicao} onChange={(v) => { setEdicao(v); setOffset(0); }} placeholder="Todas"
          options={Object.fromEntries((eds?.edicoes ?? []).map((e) => [String(e.numero), `nº ${e.numero}${e.data_publicacao ? ` · ${fmtDay(e.data_publicacao)}` : ""}`]))} /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Publicada de<Input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className="w-36" /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">até<Input type="date" value={ate} onChange={(e) => setAte(e.target.value)} className="w-36" /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Situação processual<Select value={categoria} onChange={(v) => { setCategoria(v); setOffset(0); }} placeholder="Todas"
          options={{ oposicao_apresentada: "Oposição apresentada (A)", oposicao: "Publicado para oposição (B)", indeferimento: "Indeferimento", exigencia: "Exigência", extincao_prorrogacao: "Extinção" }} /></label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Prioridade<Select value={temperatura} onChange={(v) => { setTemperatura(v); setOffset(0); }} placeholder="Todas"
          options={{ quente: "Quente", morno: "Morno", em_pesquisa: "Em pesquisa" }} /></label>
        <div className="flex flex-wrap items-end gap-2 xl:ml-auto">
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">Colorir por<Select value={metrica} onChange={setMetrica} options={Object.fromEntries(Object.entries(METRICAS).map(([k, v]) => [k, v.rotulo]))} /></label>
          <div className="flex rounded-lg border bg-muted/50 p-0.5 text-xs" role="radiogroup" aria-label="Escala">
            {(["absoluto", "normalizado"] as const).map((k) => (
              <button key={k} role="radio" aria-checked={modo === k} onClick={() => setModo(k)} title={k === "normalizado" ? "Percentual sobre os leads do estado (compara estados de tamanhos diferentes)" : "Quantidade"}
                className={cn("rounded-md px-2.5 py-1.5 font-medium", modo === k ? "bg-card shadow-sm" : "text-muted-foreground")}>{k === "absoluto" ? "Volume" : "% do estado"}</button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <section className="surface entrar p-4 md:p-5">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-semibold">{METRICAS[metrica].rotulo}{modo === "normalizado" ? " (% dos leads do estado)" : ""}</div>
            {m?.pendente && m.pendente.leads > 0 && (
              <button onClick={() => selecionar("PENDENTE")} className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs", uf === "PENDENTE" ? "border-primary bg-primary/10 text-primary" : "hover:bg-accent")}>
                <MapPin className="size-3.5" />Localização pendente <b className="num">{n(m.pendente.leads)}</b>
              </button>
            )}
          </div>
          {!m ? <div className="aspect-square animate-pulse rounded-xl bg-muted" /> : (
            <BrasilMap semDados={!m.processado} selecionado={uf} onSelect={selecionar} destaque={["SC", "RS", "PR"]}
              rotuloMetrica={modo === "normalizado" ? "% do estado" : METRICAS[metrica].rotulo.toLowerCase()}
              formatar={(v) => (modo === "normalizado" ? `${v.toFixed(0)}%` : v.toLocaleString("pt-BR"))}
              valores={m.estados.map((e) => ({ uf: e.uf, valor: valor(e), detalhe: ([
                ["leads", "Leads", n(e.leads)], ["oposicoes_apresentadas", "Oposições apresentadas", n(e.oposicoes_apresentadas)],
                ["publicados", "Publicados p/ oposição", n(e.publicados_oposicao)], ["com_contato_validado", "Contato validado", n(e.com_contato_validado)],
                ["quentes", "Quentes", n(e.quentes)],
              ] as const).filter(([k]) => modo === "normalizado" || k !== metrica).map(([, rotulo, v]) => ({ rotulo, valor: v })) }))} />
          )}
          <p className="mt-3 text-[10px] text-muted-foreground">Contornos dos estados: @svg-maps/brazil (VictorCazanave), licença CC BY 4.0.</p>
        </section>
        <section className="surface entrar p-4 md:p-5">
          {uf ? <Painel uf={uf} q={f.toString()} onFechar={() => selecionar(null)} /> : (
            <>
              <div className="mb-3 flex items-center gap-2"><span className="grid size-8 place-items-center rounded-lg bg-primary/10 text-primary"><Building2 className="size-4" /></span>
                <div><h2 className="font-semibold">Estados com mais {METRICAS[metrica].rotulo.toLowerCase()}</h2><p className="text-xs text-muted-foreground">Clique em um estado no mapa ou na lista para abrir o painel.</p></div></div>
              {m ? (m.processado ? <Ranking estados={m.estados} metrica={metrica} onSelect={selecionar} /> : <p className="py-8 text-center text-sm text-muted-foreground">Assim que a primeira RPI for processada, os estados aparecem aqui.</p>) : null}
              <div className="mt-5 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-900 dark:text-amber-200">
                <b>Ordem de trabalho dos agentes:</b> Santa Catarina primeiro, depois Rio Grande do Sul, Paraná e os demais estados. A UF vem do endereço do CNPJ na Receita (confirmada) ou do declarado na RPI (estimada).
              </div>
            </>
          )}
        </section>
      </div>

      <Secao className="mt-6" titulo={uf ? `Leads · ${NOME[uf]}` : "Leads · todos os estados"} subtitulo={leads.data ? `${n(leads.data.total)} lead(s) com os filtros acima` : undefined} icon={Users}
        acao={<label className="flex h-9 items-center gap-2 rounded-lg border bg-card px-2.5 text-sm"><Search className="size-4 text-muted-foreground" /><input value={busca} onChange={(e) => { setBusca(e.target.value); setOffset(0); }} placeholder="Empresa, CNPJ, marca, processo" className="w-56 bg-transparent outline-none" /></label>}>
        <ErrorBox error={leads.error} />
        <Table>
          <TableHeader><TableRow>
            <TableHead>Empresa / marca</TableHead><TableHead>Local</TableHead><TableHead>Processo</TableHead><TableHead>Movimentação</TableHead>
            <TableHead>Publicação</TableHead><TableHead>Prioridade</TableHead><TableHead>Contatos</TableHead><TableHead>Status comercial</TableHead><TableHead />
          </TableRow></TableHeader>
          <TableBody>
            {leads.data?.items.length === 0 && <TableRow><TableCell colSpan={9} className="py-8 text-center text-muted-foreground">Nenhum lead com esses filtros.</TableCell></TableRow>}
            {leads.data?.items.map((l) => (
              <TableRow key={l.id} className="align-top">
                <TableCell className="max-w-64"><Link href={`/leads/${l.id}`} className="block truncate font-medium hover:underline" title={l.titular}>{l.titular}</Link>
                  <span className="block truncate text-xs text-muted-foreground" title={l.marcas ?? ""}>{l.marcas ?? "—"}</span></TableCell>
                <TableCell className="text-xs">
                  {l.geo_uf ? <span className="font-medium">{l.geo_municipio ? `${l.geo_municipio} · ` : ""}{l.geo_uf}</span> : <span className="text-amber-700">Pendente</span>}
                  <span className="block text-muted-foreground" title={LOCALIZACAO[l.geo_status]?.dica}>{LOCALIZACAO[l.geo_status]?.rotulo}</span>
                  {l.geo_status === "pendente" && <LocalizacaoPendente holderId={l.holder_id} onFeito={() => { leads.reload(); reload(); }} />}
                </TableCell>
                <TableCell className="max-w-32 truncate font-mono text-xs" title={l.processos ?? ""}>{l.processos}</TableCell>
                <TableCell className="text-xs">{categoriaLabel[l.categoria_principal ?? ""] ?? "—"}</TableCell>
                <TableCell className="text-xs">{fmtDay(l.ultima_publicacao)}</TableCell>
                <TableCell><Temp t={l.temperatura} motivos={l.temperatura_motivos} /><span className="num ml-1 text-[11px] text-muted-foreground">{l.score != null ? Math.round(Number(l.score)) : ""}</span></TableCell>
                <TableCell className="text-xs">
                  {l.whatsapp ? <span className="flex items-center gap-1"><MessageCircle className={cn("size-3.5", l.whatsapp_status === "candidato" ? "text-amber-500" : "text-[#25D366]")} />{formatWhats(l.whatsapp)}</span> : null}
                  <span className="flex items-center gap-1 text-muted-foreground">{l.n_validados ? <CheckCircle2 className="size-3 text-emerald-600" /> : <AlertTriangle className="size-3" />}{l.n_validados} validado(s) de {l.n_contatos}</span>
                </TableCell>
                <TableCell className="text-xs">{NOME_ETAPA[l.pipeline_stage] ?? l.pipeline_stage}</TableCell>
                <TableCell className="text-right"><Link href={`/leads/${l.id}`} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">Detalhes<ExternalLink className="size-3" /></Link></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {leads.data && leads.data.total > PAGE && (
          <div className="mt-4 flex items-center justify-end gap-2 text-sm">
            <span className="text-muted-foreground">{offset + 1}–{Math.min(offset + PAGE, leads.data.total)} de {n(leads.data.total)}</span>
            <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>Anterior</Button>
            <Button size="sm" variant="outline" disabled={offset + PAGE >= leads.data.total} onClick={() => setOffset(offset + PAGE)}>Próxima</Button>
          </div>
        )}
        <p className="mt-3 text-[11px] text-muted-foreground">Observações, histórico de contatos e fontes oficiais de cada lead ficam em “Detalhes”. Contatos seguem as regras de opt-out e autorização.</p>
      </Secao>
    </>
  );
}

export default function MapaPage() {
  return <Suspense><MapaInner /></Suspense>;
}
