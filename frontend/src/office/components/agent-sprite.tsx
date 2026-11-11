/** Personagem em pixel art (desenho original), com cores por agente e animação por estado. */
import { ESTADOS } from "../config";
import { iso } from "../iso";
import type { Agent, AgentStatus } from "../types";

const P = 2.6; // tamanho do "pixel"
// 12 x 18. H cabelo, S pele, E olho, M boca, C camisa, T destaque (crachá), P calça, B sapato
// minúsculas = mesma cor com sombreado (c, s) ou brilho (h)
const MAPA = [
  "....HHHH....",
  "...HhhHHH...",
  "..HhHHHHHH..",
  "..HSSSSSSH..",
  "..SSESSESs..",
  "..SSSSSSSs..",
  "...SSMMSs...",
  "....SSSs....",
  "..CCCCCCcc..",
  ".CCCCTCCCcc.",
  ".CCCCTCCCcc.",
  ".SCCCCCCCcS.",
  ".S.CCCCCcc.s",
  "...PPPPPPp..",
  "...PPPPPPp..",
  "...PP..PPp..",
  "...PP..PPp..",
  "..BBB..BBB..",
];
const COR: Record<string, string> = {
  H: "var(--cabelo)", S: "var(--pele)", E: "#1f2937", M: "#9f1239", C: "var(--camisa)", T: "var(--destaque)",
  P: "var(--calca)", B: "#111827",
};
const AJUSTE: Record<string, [string, string, number]> = {
  h: ["H", "#ffffff", 0.28], s: ["S", "#000000", 0.18], c: ["C", "#000000", 0.24], p: ["P", "#000000", 0.25],
};
export const SPRITE_W = 12 * P;
export const SPRITE_H = MAPA.length * P;

/** Definição única do sprite (reutilizada por todos os personagens via <use>). */
/** Definição única do sprite (reutilizada por todos via <use>): contorno + cores + sombreado. */
export function SpriteDefs() {
  const rects: React.ReactNode[] = [];
  const cheio = (x: number, y: number) => y >= 0 && y < MAPA.length && x >= 0 && x < 12 && MAPA[y][x] !== ".";
  // contorno: células vazias vizinhas de células preenchidas
  for (let y = -1; y <= MAPA.length; y++) {
    for (let x = -1; x <= 12; x++) {
      if (cheio(x, y)) continue;
      if (cheio(x - 1, y) || cheio(x + 1, y) || cheio(x, y - 1) || cheio(x, y + 1)) {
        rects.push(<rect key={`o${x}-${y}`} x={x * P} y={y * P} width={P + 0.2} height={P + 0.2} fill="#151922" />);
      }
    }
  }
  MAPA.forEach((linha, y) => {
    for (let x = 0; x < linha.length; x++) {
      const c = linha[x];
      if (c === ".") continue;
      const aj = AJUSTE[c];
      rects.push(<rect key={`${x}-${y}`} x={x * P} y={y * P} width={P + 0.2} height={P + 0.2} style={{ fill: COR[aj ? aj[0] : c] }} />);
      if (aj) rects.push(<rect key={`a${x}-${y}`} x={x * P} y={y * P} width={P + 0.2} height={P + 0.2} fill={aj[1]} opacity={aj[2]} />);
    }
  });
  return (
    <defs>
      <symbol id="office-pessoa" viewBox={`${-P} ${-P} ${SPRITE_W + 2 * P} ${SPRITE_H + 2 * P}`} width={SPRITE_W + 2 * P}
        height={SPRITE_H + 2 * P} overflow="visible">
        {rects}
      </symbol>
    </defs>
  );
}

export function AgentSprite({ agent, status, x, y, selecionado, onSelect }: {
  agent: Agent; status: AgentStatus; x: number; y: number; selecionado: boolean; onSelect: (id: string) => void;
}) {
  const p = iso(x, y);
  const est = ESTADOS[status.state];
  const v = agent.visual;
  return (
    <g transform={`translate(${p.x} ${p.y})`} className={`office-agent office-agent--${status.state} ${selecionado ? "is-selected" : ""}`}
      onClick={(e) => { e.stopPropagation(); onSelect(agent.id); }} role="button" tabIndex={0}
      aria-label={`${agent.nome}, ${agent.cargo}: ${est.descricao}`}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect(agent.id); }}>
      <title>{`${agent.nome} · ${agent.cargo} · ${est.rotulo}`}</title>
      <ellipse rx={15} ry={7} fill="url(#office-sombra)" />
      <ellipse className="office-agent-ring" rx={17} ry={8.5} style={{ stroke: est.cor, fill: est.cor }} />
      <g className="office-agent-body">
        <use href="#office-pessoa" x={-SPRITE_W / 2 - P} y={-SPRITE_H + 2 - P}
          style={{ ["--cabelo" as string]: v.cabelo, ["--pele" as string]: v.pele, ["--camisa" as string]: v.camisa,
            ["--calca" as string]: v.calca, ["--destaque" as string]: v.destaque }} />
      </g>
      <g className="office-agent-icon" transform={`translate(0 ${-SPRITE_H - 14})`}>
        {status.state === "thinking" && (
          <g className="office-bubble">
            <rect x={-15} y={-11} width={30} height={16} rx={8} fill="#fff" stroke="#3b82f6" strokeWidth={1.5} />
            {[-7, 0, 7].map((cx, i) => <circle key={i} cx={cx} cy={-3} r={2.2} fill="#3b82f6" style={{ animationDelay: `${i * 0.2}s` }} />)}
          </g>
        )}
        {status.state === "waiting" && (
          <g className="office-hourglass">
            <circle r={10} fill="#fff7ed" stroke="#f59e0b" strokeWidth={1.5} />
            <path d="M-4,-5 H4 L0,0 L4,5 H-4 L0,0 Z" fill="#f59e0b" />
          </g>
        )}
        {status.state === "completed" && (
          <g className="office-check">
            <circle r={10} fill="#10b981" />
            <path d="M-4.5,0 L-1,3.5 L5,-3.5" stroke="#fff" strokeWidth={2.5} fill="none" strokeLinecap="round" />
          </g>
        )}
        {status.state === "error" && (
          <g className="office-alert">
            <circle r={10} fill="#ef4444" />
            <rect x={-1.5} y={-6} width={3} height={7} fill="#fff" />
            <rect x={-1.5} y={3} width={3} height={3} fill="#fff" />
          </g>
        )}
      </g>
      <g className="office-agent-tag" transform={`translate(0 ${-SPRITE_H - (status.state === "idle" || status.state === "working" ? 8 : 34)})`}>
        <rect x={-(agent.nome.length * 3.6 + 8)} y={-11} width={agent.nome.length * 7.2 + 16} height={15} rx={4} fill="#111827" opacity={0.85} />
        <text textAnchor="middle" y={0} fontSize={10} fill="#fff" fontWeight={600}>{agent.nome}</text>
      </g>
    </g>
  );
}
