/** Personagem em ilustração vetorial (desenho original), estilo corporativo: proporções reais, sombreado suave,
 *  roupa social (blazer + camisa + crachá/gravata na cor de destaque). Cores por agente; dois cortes de cabelo. */
import { ESTADOS } from "../config";
import { iso } from "../iso";
import type { Agent, AgentStatus } from "../types";

export const SPRITE_W = 32;
export const SPRITE_H = 50;

function Corpo({ longo }: { longo: boolean }) {
  return (
    <>
      {/* cabelo de trás (longo) */}
      {longo && <path d="M8.6 12.5 C8 5.5 11.5 3 16 3 C20.5 3 24 5.5 23.4 12.5 C23.6 17 24.6 21 25.4 24.5 L19 24 L13 24 L6.6 24.5 C7.4 21 8.4 17 8.6 12.5Z" style={{ fill: "var(--cabelo)" }} />}
      {/* pernas e sapatos */}
      <path d="M11.2 35 h4.3 v11.4 h-4.3z" style={{ fill: "var(--calca)" }} />
      <path d="M16.5 35 h4.3 v11.4 h-4.3z" style={{ fill: "var(--calca)" }} />
      <path d="M16.5 35 h4.3 v11.4 h-4.3z" fill="#000" opacity={0.18} />
      <ellipse cx={13.1} cy={47} rx={3.2} ry={1.5} fill="#1b1f27" />
      <ellipse cx={18.9} cy={47} rx={3.2} ry={1.5} fill="#1b1f27" />
      {/* braços */}
      <rect x={6} y={22.5} width={4.2} height={13.5} rx={2.1} style={{ fill: "var(--camisa)" }} />
      <rect x={21.8} y={22.5} width={4.2} height={13.5} rx={2.1} style={{ fill: "var(--camisa)" }} />
      <rect x={21.8} y={22.5} width={4.2} height={13.5} rx={2.1} fill="#000" opacity={0.2} />
      <circle cx={8.1} cy={36.4} r={1.9} style={{ fill: "var(--pele)" }} />
      <circle cx={23.9} cy={36.4} r={1.9} style={{ fill: "var(--pele)" }} />
      {/* tronco: blazer */}
      <path d="M9.4 22.6 C10.5 20.4 13 19.6 16 19.6 C19 19.6 21.5 20.4 22.6 22.6 L22.4 36.2 H9.6Z" style={{ fill: "var(--camisa)" }} />
      <path d="M16 19.6 C19 19.6 21.5 20.4 22.6 22.6 L22.4 36.2 H16Z" fill="#000" opacity={0.14} />
      {/* camisa e gravata/crachá na cor de destaque */}
      <path d="M13.4 20.1 L16 26.5 L18.6 20.1 C17.8 19.8 16.9 19.7 16 19.7 C15.1 19.7 14.2 19.8 13.4 20.1Z" fill="#f4f6fa" />
      <path d="M15.3 22 h1.4 l0.6 5.6 l-1.3 1.4 l-1.3 -1.4z" style={{ fill: "var(--destaque)" }} />
      <path d="M13.4 20.1 L15.2 25.4 L12.6 23.4Z M18.6 20.1 L16.8 25.4 L19.4 23.4Z" fill="#000" opacity={0.16} />
      {/* pescoço e cabeça */}
      <path d="M14.3 15.5 h3.4 v4.6 c-1.1 0.7 -2.3 0.7 -3.4 0z" style={{ fill: "var(--pele)" }} />
      <path d="M14.3 17.2 h3.4 v1.2 c-1.1 0.5 -2.3 0.5 -3.4 0z" fill="#000" opacity={0.15} />
      <ellipse cx={9.5} cy={11.6} rx={1.1} ry={1.6} style={{ fill: "var(--pele)" }} />
      <ellipse cx={22.5} cy={11.6} rx={1.1} ry={1.6} style={{ fill: "var(--pele)" }} />
      <path d="M9.8 10.6 C9.8 6.4 12.5 4.4 16 4.4 C19.5 4.4 22.2 6.4 22.2 10.6 C22.2 14.6 19.6 17.4 16 17.4 C12.4 17.4 9.8 14.6 9.8 10.6Z" style={{ fill: "var(--pele)" }} />
      <path d="M16 4.4 C19.5 4.4 22.2 6.4 22.2 10.6 C22.2 14.6 19.6 17.4 16 17.4Z" fill="#000" opacity={0.07} />
      {/* rosto discreto */}
      <ellipse cx={13.7} cy={11.2} rx={0.75} ry={0.85} fill="#1f2430" />
      <ellipse cx={18.3} cy={11.2} rx={0.75} ry={0.85} fill="#1f2430" />
      <path d="M12.7 9.5 q1 -0.6 2 0 M17.3 9.5 q1 -0.6 2 0" stroke="#000" strokeOpacity={0.35} strokeWidth={0.5} fill="none" strokeLinecap="round" />
      <path d="M14.4 14.2 q1.6 1 3.2 0" stroke="#7a3b2e" strokeOpacity={0.7} strokeWidth={0.6} fill="none" strokeLinecap="round" />
      {/* cabelo de cima */}
      {longo
        ? <path d="M9.6 11 C9.2 5.6 12.3 3.3 16 3.3 C19.9 3.3 22.9 5.8 22.4 11.4 C21.4 8.4 19.6 6.6 16.8 6.4 C15 7.8 12.4 8.6 9.6 11Z" style={{ fill: "var(--cabelo)" }} />
        : <path d="M9.5 10.4 C9.2 5.4 12.2 3.4 16 3.4 C19.8 3.4 22.8 5.4 22.5 10.4 C21.9 8.1 20.6 7 18.6 6.8 C16.4 7.4 13.4 7.3 11.6 7.1 C10.4 7.6 9.8 8.8 9.5 10.4Z" style={{ fill: "var(--cabelo)" }} />}
      <path d="M12 4.6 C13.4 3.8 15 3.6 16.4 3.7" stroke="#fff" strokeOpacity={0.22} strokeWidth={0.8} fill="none" strokeLinecap="round" />
    </>
  );
}

/** Definições únicas reutilizadas por todos os personagens via <use> (cabelo curto e longo). */
export function SpriteDefs() {
  return (
    <defs>
      {[false, true].map((longo) => (
        <symbol key={String(longo)} id={longo ? "office-pessoa-l" : "office-pessoa"} viewBox={`0 0 ${SPRITE_W} ${SPRITE_H}`}
          width={SPRITE_W} height={SPRITE_H} overflow="visible">
          <Corpo longo={longo} />
        </symbol>
      ))}
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
        <use href={v.longo ? "#office-pessoa-l" : "#office-pessoa"} x={-SPRITE_W / 2} y={-SPRITE_H + 2}
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
