"use client";
/** Mapa vetorial interativo do Brasil (26 estados + DF): cor por volume, dica ao passar o mouse, clique para filtrar.
 *  Estados sem dado processado ficam hachurados ("sem dados"), nunca pintados como zero. */
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { BRASIL_UFS, BRASIL_VIEWBOX } from "@/lib/brasil-geo";
import { RAMPA, degrau } from "@/lib/territorio";

export type ValorUF = { uf: string; valor: number; detalhe?: { rotulo: string; valor: string }[] };

export function BrasilMap({ valores, selecionado, onSelect, semDados, rotuloMetrica, formatar = (v) => v.toLocaleString("pt-BR"), destaque = [] }: {
  valores: ValorUF[];
  selecionado: string | null;
  onSelect: (uf: string | null) => void;
  semDados: boolean;
  rotuloMetrica: string;
  formatar?: (v: number) => string;
  /** UFs com anel de prioridade (ex.: SC, RS, PR) */
  destaque?: string[];
}) {
  const [hover, setHover] = useState<string | null>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [centros, setCentros] = useState<Record<string, { x: number; y: number }>>({});
  const caixa = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const por = Object.fromEntries(valores.map((v) => [v.uf, v]));
  const max = Math.max(0, ...valores.map((v) => v.valor));

  useEffect(() => {
    if (!svg.current) return;
    const c: Record<string, { x: number; y: number }> = {};
    svg.current.querySelectorAll<SVGPathElement>("path[data-uf]").forEach((p) => {
      const b = p.getBBox();
      c[p.dataset.uf!] = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
    });
    // ajustes de leitura para estados com recorte irregular
    if (c.GO && c.DF) c.GO = { x: c.GO.x - 14, y: c.GO.y + 6 };
    if (c.RJ) c.RJ = { x: c.RJ.x + 4, y: c.RJ.y + 2 };
    setCentros(c);
  }, []);

  const cor = (uf: string) => {
    if (semDados) return "url(#sem-dados)";
    const d = degrau(por[uf]?.valor ?? 0, max);
    return d < 0 ? "var(--map-zero)" : RAMPA[d];
  };
  const pequeno = new Set(["DF", "SE", "AL", "PB", "RN", "ES", "RJ", "PE"]);
  const h = hover ? BRASIL_UFS.find((u) => u.uf === hover) : null;

  return (
    <div ref={caixa} className="relative [--map-zero:#eef2f7] dark:[--map-zero:#1e2433]"
      onMouseMove={(e) => { const r = caixa.current!.getBoundingClientRect(); setPos({ x: e.clientX - r.left, y: e.clientY - r.top }); }}>
      <svg ref={svg} viewBox={BRASIL_VIEWBOX} className="h-auto w-full select-none" role="group" aria-label="Mapa do Brasil por estado">
        <defs>
          <pattern id="sem-dados" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="var(--map-zero)" /><line x1="0" y1="0" x2="0" y2="6" stroke="#94a3b8" strokeWidth="1.2" opacity="0.45" />
          </pattern>
          <filter id="sombra-uf" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity="0.35" /></filter>
        </defs>
        {BRASIL_UFS.map((u) => {
          const sel = selecionado === u.uf;
          return (
            <path key={u.uf} d={u.path} data-uf={u.uf} fill={cor(u.uf)} role="button" tabIndex={0}
              aria-label={`${u.nome}: ${semDados ? "sem dados processados" : `${formatar(por[u.uf]?.valor ?? 0)} ${rotuloMetrica}`}`}
              aria-pressed={sel}
              className={cn("cursor-pointer outline-none transition-[opacity,filter] duration-200", selecionado && !sel && "opacity-55",
                hover === u.uf && "brightness-110")}
              stroke={sel ? "var(--primary)" : "var(--card)"} strokeWidth={sel ? 2.4 : 0.9} strokeLinejoin="round"
              filter={sel ? "url(#sombra-uf)" : undefined}
              onMouseEnter={() => setHover(u.uf)} onMouseLeave={() => setHover(null)}
              onClick={() => onSelect(sel ? null : u.uf)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(sel ? null : u.uf); } }} />
          );
        })}
        {/* o selecionado por cima, para o contorno aparecer inteiro */}
        {selecionado && BRASIL_UFS.filter((u) => u.uf === selecionado).map((u) => (
          <path key="sel" d={u.path} fill="none" stroke="var(--primary)" strokeWidth={2.4} pointerEvents="none" />
        ))}
        {destaque.map((uf, i) => centros[uf] && (
          <g key={uf} pointerEvents="none">
            <circle cx={centros[uf].x + 13} cy={centros[uf].y - 9} r={6.5} fill="#f59e0b" stroke="var(--card)" strokeWidth={1.5} />
            <text x={centros[uf].x + 13} y={centros[uf].y - 6.4} textAnchor="middle" className="fill-white text-[8px] font-bold">{i + 1}</text>
          </g>
        ))}
        {Object.entries(centros).map(([uf, c]) => {
          const d = semDados ? -1 : degrau(por[uf]?.valor ?? 0, max);
          return (
            <text key={uf} x={c.x} y={c.y + 3} textAnchor="middle" pointerEvents="none"
              className={cn("font-semibold", pequeno.has(uf) ? "text-[7px]" : "text-[10px]")}
              fill={d >= 3 ? "#ffffff" : "#334155"} opacity={0.9}>{uf}</text>
          );
        })}
      </svg>
      {h && pos && (
        <div className="pointer-events-none absolute z-10 min-w-44 rounded-xl border bg-card px-3 py-2 text-xs shadow-xl"
          style={{ left: Math.min(pos.x + 14, (caixa.current?.clientWidth ?? 400) - 190), top: Math.max(pos.y - 10, 0) }}>
          <div className="mb-1 font-semibold">{h.nome} <span className="text-muted-foreground">({h.uf})</span></div>
          {semDados ? <div className="text-muted-foreground">Sem RPI processada ainda</div> : (
            <>
              <div className="flex justify-between gap-4"><span className="text-muted-foreground">{rotuloMetrica}</span><b className="num">{formatar(por[h.uf]?.valor ?? 0)}</b></div>
              {por[h.uf]?.detalhe?.map((d) => (
                <div key={d.rotulo} className="flex justify-between gap-4"><span className="text-muted-foreground">{d.rotulo}</span><span className="num">{d.valor}</span></div>
              ))}
            </>
          )}
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
        <span>{rotuloMetrica}:</span>
        <span className="flex items-center gap-1"><span className="size-3 rounded-sm border" style={{ background: "var(--map-zero)" }} />0</span>
        <span className="flex items-center">{RAMPA.map((c) => <span key={c} className="h-3 w-6 first:rounded-l-sm last:rounded-r-sm" style={{ background: c }} />)}</span>
        <span className="num">até {formatar(max)}</span>
        <span className="flex items-center gap-1"><svg width="12" height="12"><rect width="12" height="12" fill="url(#sem-dados)" /></svg>sem dados</span>
        {destaque.length > 0 && <span className="flex items-center gap-1"><span className="size-3 rounded-full bg-amber-500" />ordem de prioridade</span>}
      </div>
    </div>
  );
}
