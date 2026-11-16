"use client";

import { AlertTriangle, FileText, Loader2 } from "lucide-react";
import { useApi } from "@/components/use-api";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

/** V2.9 · Extração paralela PDF + XML: o que chegou, quando, quanto foi lido e o que diverge. */
type Fonte = {
  fonte: "pdf_i" | "pdf_ii" | "xml";
  status: string;
  detectado_em: string | null;
  baixado_em: string | null;
  processado_em: string | null;
  tempo_download_s: number | null;
  tempo_processamento_s: number | null;
  paginas: number | null;
  registros: number | null;
  registros_alvo: number | null;
  tentativas: number;
  ultimo_erro: string | null;
  etapa: string | null;
  uf_em_processamento: string | null;
};
type Dados = {
  edicao: { numero: number; data_publicacao: string | null; status: string; detectada_em: string } | null;
  fontes: Fonte[];
  publicacoes_por_fonte: Record<string, number>;
  conciliacao: Record<string, number>;
  divergencias: { numero_processo: string; despacho_codigo: string; situacao: string; diferencas: Record<string, unknown> }[];
  leads_qualificados: { uf: string; n: number; pelo_pdf: number }[];
  em_processamento: { fonte: string; etapa: string | null; uf: string | null } | null;
};

const NOME: Record<string, string> = { pdf_i: "PDF · Volume I", xml: "XML de marcas", pdf_ii: "PDF · Volume II" };
const STATUS: Record<string, [string, string]> = {
  detectado: ["Detectado", "bg-slate-100 text-slate-700"],
  baixando: ["Baixando", "bg-sky-100 text-sky-800"],
  baixado: ["Baixado", "bg-sky-100 text-sky-800"],
  processando: ["Processando", "bg-amber-100 text-amber-900"],
  processado: ["Processado", "bg-emerald-100 text-emerald-800"],
  erro: ["Erro (nova tentativa)", "bg-rose-100 text-rose-800"],
  ignorado: ["Não necessário", "bg-slate-100 text-slate-600"],
};
const SIT: Record<string, string> = { confere: "Conferem", so_pdf: "Só no PDF", so_xml: "Só no XML", divergente: "Divergentes" };
const n = (v: number | null | undefined) => (v == null ? "—" : Number(v).toLocaleString("pt-BR"));
const hora = (v: string | null) => (v ? fmtDate(v) : "—");
const seg = (v: number | null) => (v == null ? "—" : v < 90 ? `${Math.round(v)} s` : `${(v / 60).toFixed(1)} min`);

export function FontesRpi() {
  const { data: d } = useApi<Dados>("/api/rpi-fontes", 30000);
  if (!d?.edicao || d.fontes.length === 0) return null;
  const conc = Object.entries(d.conciliacao);
  return (
    <div className="surface mb-4 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm font-semibold">
        <FileText className="size-4" />RPI {d.edicao.numero} · PDF e XML em paralelo
        <span className="text-xs font-normal text-muted-foreground">publicação {d.edicao.data_publicacao ? d.edicao.data_publicacao.split("-").reverse().join("/") : "—"} · detectada {hora(d.edicao.detectada_em)}</span>
        {d.em_processamento && (
          <span className="ml-auto flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-normal text-amber-900">
            <Loader2 className="size-3 animate-spin" />{NOME[d.em_processamento.fonte]}: {d.em_processamento.etapa ?? "processando"}{d.em_processamento.uf ? ` · estado ${d.em_processamento.uf}` : ""}
          </span>
        )}
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        {d.fontes.map((f) => {
          const [rot, cor] = STATUS[f.status] ?? [f.status, ""];
          return (
            <div key={f.fonte} className="rounded-lg border p-3 text-xs">
              <div className="mb-1 flex items-center justify-between"><span className="font-medium">{NOME[f.fonte]}</span><span className={cn("rounded-full px-2 py-0.5", cor)}>{rot}</span></div>
              <dl className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-muted-foreground">
                <dt>Detectado</dt><dd className="text-foreground">{hora(f.detectado_em)}</dd>
                <dt>Baixado</dt><dd className="text-foreground">{hora(f.baixado_em)} {f.tempo_download_s != null && `(${seg(f.tempo_download_s)})`}</dd>
                <dt>Processado</dt><dd className="text-foreground">{hora(f.processado_em)} {f.tempo_processamento_s != null && `(${seg(f.tempo_processamento_s)})`}</dd>
                {f.fonte !== "pdf_ii" && <><dt>Registros lidos</dt><dd className="num text-foreground">{n(f.registros)}{f.paginas ? ` · ${n(f.paginas)} pág.` : ""}</dd>
                <dt>De interesse</dt><dd className="num text-foreground">{n(f.registros_alvo)}</dd></>}
              </dl>
              {f.status === "erro" && f.ultimo_erro && <p className="mt-1 flex gap-1 text-rose-700"><AlertTriangle className="mt-0.5 size-3 shrink-0" />{f.ultimo_erro}</p>}
              {f.fonte === "pdf_ii" && <p className="mt-1 text-[11px] text-muted-foreground">Concessões: só monitorado (não gera oportunidade).</p>}
            </div>
          );
        })}
      </div>
      <div className="mt-3 grid gap-3 text-xs md:grid-cols-[1fr_1fr]">
        <div>
          <div className="mb-1 font-medium">Leads qualificados desta edição</div>
          <ul className="flex flex-wrap gap-1.5">{d.leads_qualificados.map((l) => (
            <li key={l.uf} className="rounded-md border px-2 py-1"><span className="font-medium">{l.uf}</span> {n(l.n)}{l.pelo_pdf ? <span className="text-muted-foreground"> · {n(l.pelo_pdf)} pelo PDF</span> : null}</li>
          ))}{d.leads_qualificados.length === 0 && <li className="text-muted-foreground">Ainda nenhum.</li>}</ul>
          <p className="mt-1 text-muted-foreground">Publicações por origem: PDF {n(d.publicacoes_por_fonte.pdf ?? 0)} · XML {n(d.publicacoes_por_fonte.xml ?? 0)}</p>
        </div>
        <div>
          <div className="mb-1 font-medium">Conciliação PDF × XML</div>
          {conc.length === 0 ? <p className="text-muted-foreground">Acontece quando os dois arquivos tiverem sido lidos.</p> : (
            <ul className="flex flex-wrap gap-1.5">{conc.map(([k, v]) => (
              <li key={k} className={cn("rounded-md border px-2 py-1", (k === "divergente" || k === "so_pdf") && v > 0 && "border-amber-400 bg-amber-50")}>{SIT[k] ?? k}: <span className="num font-medium">{n(v)}</span></li>
            ))}</ul>
          )}
          {d.divergencias.length > 0 && (
            <details className="mt-1"><summary className="cursor-pointer text-amber-800">Ver {d.divergencias.length} para revisão</summary>
              <ul className="mt-1 space-y-0.5">{d.divergencias.map((x) => (
                <li key={`${x.numero_processo}-${x.despacho_codigo}`}>{x.numero_processo} · {x.despacho_codigo} · {SIT[x.situacao]}{Object.keys(x.diferencas).length ? ` (${Object.keys(x.diferencas).join(", ")})` : ""}</li>
              ))}</ul>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
