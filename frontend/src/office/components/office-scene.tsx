"use client";

/** Cena do escritório: SVG isométrico com zoom (roda, pinça, botões, teclado) e arraste para navegar. */
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { AGENTES, DEPARTAMENTOS, GAP, ROOM_D, ROOM_W, roomOrigin } from "../config";
import { iso, zoomAt } from "../iso";
import type { AgentStatus, DeptStatus } from "../types";
import { SpriteDefs } from "./agent-sprite";
import { Room } from "./room";

const COLS = 4, ROWS = 2;
const MUNDO_W = COLS * (ROOM_W + GAP), MUNDO_D = ROWS * (ROOM_D + GAP);
// limites da cena em pixels (inclui paredes e cabeças acima do piso)
const FACHADA_H = 150;
const B = { minX: iso(-1, MUNDO_D).x - 10, maxX: iso(MUNDO_W, -1).x + 10, minY: iso(-1, -1).y - FACHADA_H - 10, maxY: iso(MUNDO_W, MUNDO_D).y + 40 };

/** Gradientes compartilhados: sombra, foco de luz, latão e céu noturno. */
function SceneDefs() {
  return (
    <defs>
      <radialGradient id="office-sombra"><stop offset="0" stopColor="#000" stopOpacity="0.38" /><stop offset="1" stopColor="#000" stopOpacity="0" /></radialGradient>
      <radialGradient id="office-luz"><stop offset="0" stopColor="#ffe3a3" stopOpacity="0.55" /><stop offset="0.6" stopColor="#ffd27a" stopOpacity="0.16" /><stop offset="1" stopColor="#ffd27a" stopOpacity="0" /></radialGradient>
      <linearGradient id="office-latao" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#f0d9a3" /><stop offset="0.5" stopColor="#c9a45c" /><stop offset="1" stopColor="#e2c27c" /></linearGradient>
      <linearGradient id="office-ceu" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#0a1228" /><stop offset="0.65" stopColor="#1a2550" /><stop offset="1" stopColor="#3a2f5e" /></linearGradient>
    </defs>
  );
}

/** Pseudoaleatório determinístico (a silhueta da cidade é sempre a mesma). */
function rnd(i: number) { const x = Math.sin(i * 12.9898) * 43758.5453; return x - Math.floor(x); }

/** Fachada de vidro com a cidade ao fundo, desenhada no plano da parede (skew isométrico). */
function Fachada({ comprimento, espelhar, marca }: { comprimento: number; espelhar?: boolean; marca?: boolean }) {
  const o = iso(-1, -1);
  const L = comprimento * 32;
  const predios: React.ReactNode[] = [];
  let u = 0, i = espelhar ? 100 : 0;
  while (u < L) {
    const w = 22 + rnd(i) * 34, h = 35 + rnd(i + 1) * 95;
    predios.push(<rect key={`p${i}`} x={u} y={-h} width={w} height={h} fill={rnd(i + 2) > 0.5 ? "#101a33" : "#0d1529"} />);
    for (let j = 0; j < 6; j++) {
      if (rnd(i * 7 + j) > 0.55) continue;
      predios.push(<rect key={`j${i}-${j}`} x={u + 4 + rnd(i + j) * (w - 10)} y={-h + 8 + rnd(i * 3 + j) * (h - 16)} width={3} height={4}
        fill="#fcd77a" opacity={0.75} className={j % 3 === 0 ? "office-city-light" : undefined} />);
    }
    u += w + 3; i += 3;
  }
  const montantes = [];
  for (let k = 0; k <= L; k += 64) montantes.push(<line key={k} x1={k} y1={0} x2={k} y2={-FACHADA_H} stroke="#2a3140" strokeWidth={3} />);
  return (
    <g transform={`translate(${o.x} ${o.y}) ${espelhar ? "scale(-1 1) " : ""}skewY(26.565)`}>
      <rect x={0} y={-FACHADA_H} width={L} height={FACHADA_H} fill="url(#office-ceu)" />
      {predios}
      <rect x={0} y={-FACHADA_H} width={L} height={FACHADA_H} fill="#9ec5ff" opacity={0.07} />
      <line x1={0} y1={-FACHADA_H * 0.55} x2={L} y2={-FACHADA_H * 0.55} stroke="#2a3140" strokeWidth={1.5} />
      {montantes}
      <rect x={0} y={-FACHADA_H - 6} width={L} height={6} fill="#2a3140" />
      {marca && (
        <g transform={`translate(${L - 320} ${-FACHADA_H + 34})`}>
          <text fontSize={20} fontWeight={800} letterSpacing={6} fill="url(#office-latao)">INPI AI OFFICE</text>
          <text y={16} fontSize={8.5} letterSpacing={3.2} fill="#c9a45c" opacity={0.85}>INTELIGÊNCIA EM PROPRIEDADE INDUSTRIAL</text>
        </g>
      )}
    </g>
  );
}

export type OfficeSceneHandle = { focusDept: (id: string) => void; zoom: (f: number) => void; reset: () => void };

type Props = {
  statuses: Record<string, AgentStatus>;
  deptStatus: Record<string, DeptStatus>;
  selecionado: { tipo: "agente" | "dept"; id: string } | null;
  onSelect: (s: { tipo: "agente" | "dept"; id: string } | null) => void;
};

export const OfficeScene = forwardRef<OfficeSceneHandle, Props>(function OfficeScene(
  { statuses, deptStatus, selecionado, onSelect }, ref) {
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 1200, h: 700 });
  const [view, setView] = useState({ x: 0, y: 0, s: 1 });
  const ponteiros = useRef(new Map<number, { x: number; y: number }>());
  const arraste = useRef({ moved: 0, pinch: 0 });

  const fit = useCallback((w: number, h: number) => {
    const s = Math.min(w / (B.maxX - B.minX), h / (B.maxY - B.minY)) * 0.96;
    return { s, x: (w - (B.maxX - B.minX) * s) / 2 - B.minX * s, y: (h - (B.maxY - B.minY) * s) / 2 - B.minY * s };
  }, []);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      setSize({ w: width, h: height });
      setView(fit(width, height));
    });
    ro.observe(el);
    const onWheel = (ev: WheelEvent) => {
      ev.preventDefault();
      const r = el.getBoundingClientRect();
      setView((v) => zoomAt(v, Math.exp(-ev.deltaY * 0.0015), ev.clientX - r.left, ev.clientY - r.top));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => { ro.disconnect(); el.removeEventListener("wheel", onWheel); };
  }, [fit]);

  useImperativeHandle(ref, () => ({
    zoom: (f) => setView((v) => zoomAt(v, f, size.w / 2, size.h / 2)),
    reset: () => setView(fit(size.w, size.h)),
    focusDept: (id) => {
      const d = DEPARTAMENTOS.find((x) => x.id === id);
      if (!d) return;
      const o = roomOrigin(d);
      const c = iso(o.x + ROOM_W / 2, o.y + ROOM_D / 2, 20);
      const s = Math.max(1.1, fit(size.w, size.h).s * 2.2);
      setView({ s, x: size.w / 2 - c.x * s, y: size.h / 2 - c.y * s });
    },
  }), [fit, size]);

  function onPointerDown(e: React.PointerEvent) {
    ponteiros.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    arraste.current.moved = 0;
    if (ponteiros.current.size === 2) {
      const [p, q] = [...ponteiros.current.values()];
      arraste.current.pinch = Math.hypot(p.x - q.x, p.y - q.y);
    }
  }
  function onPointerMove(e: React.PointerEvent) {
    const ant = ponteiros.current.get(e.pointerId);
    if (!ant) return;
    const atual = { x: e.clientX, y: e.clientY };
    ponteiros.current.set(e.pointerId, atual);
    if (ponteiros.current.size === 2) {
      const [p, q] = [...ponteiros.current.values()];
      const dist = Math.hypot(p.x - q.x, p.y - q.y);
      const r = wrap.current!.getBoundingClientRect();
      if (arraste.current.pinch) setView((v) => zoomAt(v, dist / arraste.current.pinch, (p.x + q.x) / 2 - r.left, (p.y + q.y) / 2 - r.top));
      arraste.current.pinch = dist;
      arraste.current.moved += 10;
      return;
    }
    const dx = atual.x - ant.x, dy = atual.y - ant.y;
    arraste.current.moved += Math.abs(dx) + Math.abs(dy);
    if (arraste.current.moved > 4) {
      if (!wrap.current?.hasPointerCapture(e.pointerId)) wrap.current?.setPointerCapture(e.pointerId);
      setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
    }
  }
  function onPointerUp(e: React.PointerEvent) {
    ponteiros.current.delete(e.pointerId);
    if (ponteiros.current.size < 2) arraste.current.pinch = 0;
  }
  // clique depois de arrastar não seleciona nada
  function onClickCapture(e: React.MouseEvent) {
    if (arraste.current.moved > 4) { e.stopPropagation(); e.preventDefault(); }
  }
  function onKeyDown(e: React.KeyboardEvent) {
    const passo = 40;
    if (e.key === "+" || e.key === "=") setView((v) => zoomAt(v, 1.2, size.w / 2, size.h / 2));
    else if (e.key === "-") setView((v) => zoomAt(v, 1 / 1.2, size.w / 2, size.h / 2));
    else if (e.key === "0") setView(fit(size.w, size.h));
    else if (e.key === "ArrowLeft") setView((v) => ({ ...v, x: v.x + passo }));
    else if (e.key === "ArrowRight") setView((v) => ({ ...v, x: v.x - passo }));
    else if (e.key === "ArrowUp") setView((v) => ({ ...v, y: v.y + passo }));
    else if (e.key === "ArrowDown") setView((v) => ({ ...v, y: v.y - passo }));
    else if (e.key === "Escape") onSelect(null);
    else return;
    e.preventDefault();
  }

  const salas = [...DEPARTAMENTOS].sort((a, b) => a.row + a.col - (b.row + b.col));
  const piso = [iso(-1, -1), iso(MUNDO_W - 1, -1), iso(MUNDO_W - 1, MUNDO_D - 1), iso(-1, MUNDO_D - 1)];
  const LAJE = 22; // espessura da laje do andar
  const desce = (p: { x: number; y: number }) => ({ x: p.x, y: p.y + LAJE });
  const ladoX = [piso[1], piso[2], desce(piso[2]), desce(piso[1])];
  const ladoY = [piso[3], piso[2], desce(piso[2]), desce(piso[3])];

  return (
    <div ref={wrap} className="office-viewport" tabIndex={0} onKeyDown={onKeyDown} onPointerDown={onPointerDown}
      onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onClickCapture={onClickCapture}
      aria-label="Escritório virtual. Arraste para navegar, use a roda do mouse ou + e - para zoom.">
      <svg width={size.w} height={size.h} className="office-svg" onClick={() => onSelect(null)}>
        <SpriteDefs />
        <SceneDefs />
        <g transform={`translate(${view.x} ${view.y}) scale(${view.s})`}>
          <ellipse cx={(iso(MUNDO_W, MUNDO_D).x + iso(-1, -1).x) / 2} cy={iso(MUNDO_W, MUNDO_D).y + 30} rx={900} ry={90} fill="url(#office-sombra)" />
          <polygon points={ladoX.map((p) => `${p.x},${p.y}`).join(" ")} fill="#1c212b" />
          <polygon points={ladoY.map((p) => `${p.x},${p.y}`).join(" ")} fill="#262c38" />
          <polygon points={piso.map((p) => `${p.x},${p.y}`).join(" ")} fill="#d8d3cb" />
          <polyline points={[piso[3], piso[2], piso[1]].map((p) => `${p.x},${p.y}`).join(" ")} fill="none" stroke="#c9a45c" strokeWidth={2} opacity={0.8} />
          <Fachada comprimento={MUNDO_W} marca />
          <Fachada comprimento={MUNDO_D} espelhar />
          {salas.map((d) => (
            <Room key={d.id} dept={d} agentes={AGENTES.filter((a) => a.departamento === d.id)} statuses={statuses}
              status={deptStatus[d.id]} selecionado={selecionado?.tipo === "dept" && selecionado.id === d.id}
              agenteSelecionado={selecionado?.tipo === "agente" ? selecionado.id : null}
              onSelectDept={(id) => onSelect({ tipo: "dept", id })} onSelectAgent={(id) => onSelect({ tipo: "agente", id })} />
          ))}
        </g>
      </svg>
    </div>
  );
});
