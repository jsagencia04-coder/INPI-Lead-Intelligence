"use client";
/** Gráficos leves em SVG (sem biblioteca): tendência, barras horizontais, rosca e minigráfico.
 *  Cores de série seguem a ordem fixa validada (--series-1..8); textos sempre na cor de texto, nunca na da série. */
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export const SERIE = (n: number) => `var(--series-${n})`;
const fmt = (n: number) => n.toLocaleString("pt-BR");

function useLargura<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

function escala(max: number) {
  if (max <= 4) return { topo: 4, passos: [0, 1, 2, 3, 4] };
  const bruto = max / 4;
  const mag = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => p >= bruto) ?? bruto;
  return { topo: passo * 4, passos: [0, 1, 2, 3, 4].map((i) => i * passo) };
}

export function Legenda({ itens }: { itens: { rotulo: string; cor: string; valor?: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {itens.map((i) => (
        <li key={i.rotulo} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: i.cor }} />
          <span>{i.rotulo}</span>
          {i.valor && <span className="num font-medium text-foreground">{i.valor}</span>}
        </li>
      ))}
    </ul>
  );
}

/** Linhas ao longo do tempo, com cruz de leitura e dica ao passar o mouse. Um único eixo. */
export function TrendChart({ dados, series, altura = 220 }: {
  dados: Record<string, number | string>[];
  series: { chave: string; rotulo: string; cor: string }[];
  altura?: number;
}) {
  const [ref, w] = useLargura<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const pad = { l: 36, r: 12, t: 12, b: 24 };
  const iw = w - pad.l - pad.r, ih = altura - pad.t - pad.b;
  const max = Math.max(1, ...dados.flatMap((d) => series.map((s) => Number(d[s.chave]) || 0)));
  const { topo, passos } = escala(max);
  const x = (i: number) => pad.l + (dados.length <= 1 ? iw / 2 : (i * iw) / (dados.length - 1));
  const y = (v: number) => pad.t + ih - (v / topo) * ih;
  const dia = (d: Record<string, number | string>) => { const [, m, dd] = String(d.dia).split("-"); return `${dd}/${m}`; };
  const cada = Math.ceil(dados.length / Math.max(2, Math.floor(iw / 64)));

  return (
    <div ref={ref} className="relative">
      <svg width={w} height={altura} role="img" aria-label={`Evolução diária: ${series.map((s) => s.rotulo).join(", ")}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const i = Math.round(((e.clientX - r.left - pad.l) / iw) * (dados.length - 1));
          setHover(Math.max(0, Math.min(dados.length - 1, i)));
        }}>
        <defs>
          {series.map((s, k) => (
            <linearGradient key={s.chave} id={`area-${k}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={s.cor} stopOpacity={0.22} /><stop offset="100%" stopColor={s.cor} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        {passos.map((p) => (
          <g key={p}>
            <line x1={pad.l} x2={w - pad.r} y1={y(p)} y2={y(p)} stroke="var(--border)" strokeDasharray={p ? "3 4" : undefined} />
            <text x={pad.l - 8} y={y(p) + 4} textAnchor="end" className="fill-muted-foreground text-[10px] num">{fmt(p)}</text>
          </g>
        ))}
        {dados.map((d, i) => (i % cada === 0 || i === dados.length - 1) && (
          <text key={i} x={x(i)} y={altura - 6} textAnchor="middle" className="fill-muted-foreground text-[10px]">{dia(d)}</text>
        ))}
        {series.map((s, k) => {
          const pts = dados.map((d, i) => `${x(i)},${y(Number(d[s.chave]) || 0)}`);
          return (
            <g key={s.chave}>
              {k === 0 && <polygon points={`${x(0)},${y(0)} ${pts.join(" ")} ${x(dados.length - 1)},${y(0)}`} fill={`url(#area-${k})`} />}
              <polyline points={pts.join(" ")} fill="none" stroke={s.cor} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            </g>
          );
        })}
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + ih} stroke="var(--muted-foreground)" strokeOpacity={0.4} />
            {series.map((s) => (
              <circle key={s.chave} cx={x(hover)} cy={y(Number(dados[hover][s.chave]) || 0)} r={4.5} fill={s.cor} stroke="var(--card)" strokeWidth={2} />
            ))}
          </g>
        )}
      </svg>
      {hover !== null && dados[hover] && (
        <div className="pointer-events-none absolute top-2 z-10 min-w-36 rounded-lg border bg-card px-3 py-2 text-xs shadow-lg"
          style={{ left: Math.min(Math.max(x(hover) + 12, 0), w - 160) }}>
          <div className="mb-1 font-medium">{dia(dados[hover])}</div>
          {series.map((s) => (
            <div key={s.chave} className="flex items-center gap-2">
              <span className="size-2 rounded-sm" style={{ background: s.cor }} />
              <span className="flex-1 text-muted-foreground">{s.rotulo}</span>
              <span className="num font-medium">{fmt(Number(dados[hover][s.chave]) || 0)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Barras horizontais com rótulo, valor e participação. Uma cor por gráfico, salvo quando cada barra é uma entidade. */
export function BarList({ itens, cor = SERIE(1), vazio = "Sem dados ainda.", href }: {
  itens: { chave: string; rotulo: string; n: number; cor?: string; nota?: string }[];
  cor?: string;
  vazio?: string;
  href?: (chave: string) => string | undefined;
}) {
  const total = itens.reduce((s, i) => s + i.n, 0);
  const max = Math.max(1, ...itens.map((i) => i.n));
  if (!itens.length || !total) return <p className="py-6 text-center text-sm text-muted-foreground">{vazio}</p>;
  return (
    <ul className="space-y-2.5">
      {itens.map((i) => {
        const conteudo = (
          <>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 truncate">{i.rotulo}{i.nota && <span className="ml-1.5 text-xs text-muted-foreground">{i.nota}</span>}</span>
              <span className="num shrink-0 font-medium">{fmt(i.n)}<span className="ml-1.5 text-xs font-normal text-muted-foreground">{Math.round((i.n / total) * 100)}%</span></span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full transition-[width] duration-700" style={{ width: `${Math.max(2, (i.n / max) * 100)}%`, background: i.cor ?? cor }} />
            </div>
          </>
        );
        const link = href?.(i.chave);
        return (
          <li key={i.chave} title={`${i.rotulo}: ${fmt(i.n)} (${Math.round((i.n / total) * 100)}%)`}>
            {link ? <a href={link} className="block rounded-md hover:opacity-80">{conteudo}</a> : conteudo}
          </li>
        );
      })}
    </ul>
  );
}

/** Rosca de partes de um todo (até 5 fatias), com legenda e valores. */
export function Donut({ itens, centro, rotuloCentro, tamanho = 148 }: {
  itens: { rotulo: string; n: number; cor: string }[];
  centro?: string;
  rotuloCentro?: string;
  tamanho?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const total = itens.reduce((s, i) => s + i.n, 0);
  const r = tamanho / 2 - 10, c = 2 * Math.PI * r;
  let acc = 0;
  return (
    <div className="flex flex-wrap items-center justify-center gap-5">
      <div className="relative" style={{ width: tamanho, height: tamanho }}>
        <svg width={tamanho} height={tamanho} viewBox={`0 0 ${tamanho} ${tamanho}`} className="-rotate-90" role="img"
          aria-label={itens.map((i) => `${i.rotulo}: ${i.n}`).join(", ")}>
          <circle cx={tamanho / 2} cy={tamanho / 2} r={r} fill="none" stroke="var(--muted)" strokeWidth={16} />
          {total > 0 && itens.map((it, k) => {
            const frac = it.n / total;
            const len = Math.max(0, frac * c - (itens.filter((x) => x.n).length > 1 ? 2 : 0));
            const off = -acc * c;
            acc += frac;
            return it.n ? (
              <circle key={it.rotulo} cx={tamanho / 2} cy={tamanho / 2} r={r} fill="none" stroke={it.cor} strokeWidth={hover === k ? 20 : 16}
                strokeDasharray={`${len} ${c - len}`} strokeDashoffset={off} className="transition-all"
                onMouseEnter={() => setHover(k)} onMouseLeave={() => setHover(null)} />
            ) : null;
          })}
        </svg>
        <div className="pointer-events-none absolute inset-0 grid place-content-center text-center">
          <div className="num text-2xl font-semibold">{hover !== null ? fmt(itens[hover].n) : centro ?? fmt(total)}</div>
          <div className="max-w-24 text-[11px] leading-tight text-muted-foreground">{hover !== null ? itens[hover].rotulo : rotuloCentro}</div>
        </div>
      </div>
      <ul className="min-w-40 flex-1 space-y-1.5 text-sm">
        {itens.map((i, k) => (
          <li key={i.rotulo} className={cn("flex items-center gap-2 rounded-md px-1", hover === k && "bg-accent/60")}
            onMouseEnter={() => setHover(k)} onMouseLeave={() => setHover(null)}>
            <span className="size-2.5 shrink-0 rounded-sm" style={{ background: i.cor }} />
            <span className="min-w-0 flex-1 leading-tight text-muted-foreground">{i.rotulo}</span>
            <span className="num font-medium">{fmt(i.n)}</span>
            <span className="num w-9 text-right text-xs text-muted-foreground">{total ? Math.round((i.n / total) * 100) : 0}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Minigráfico de tendência para os cards de indicador. */
export function Sparkline({ valores, cor, altura = 34 }: { valores: number[]; cor: string; altura?: number }) {
  const w = 120;
  if (valores.length < 2) return null;
  const max = Math.max(1, ...valores);
  const pts = valores.map((v, i) => `${(i * w) / (valores.length - 1)},${altura - 3 - (v / max) * (altura - 6)}`);
  const id = `sp-${cor.replace(/[^a-z0-9]/gi, "")}`;
  return (
    <svg viewBox={`0 0 ${w} ${altura}`} preserveAspectRatio="none" className="h-9 w-full" aria-hidden>
      <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={cor} stopOpacity={0.25} /><stop offset="100%" stopColor={cor} stopOpacity={0} /></linearGradient></defs>
      <polygon points={`0,${altura} ${pts.join(" ")} ${w},${altura}`} fill={`url(#${id})`} />
      <polyline points={pts.join(" ")} fill="none" stroke={cor} strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}
