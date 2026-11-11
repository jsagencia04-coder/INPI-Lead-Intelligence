/** Sala de alto padrão: piso de madeira, tapete, divisórias de vidro, placa de latão e luz quente. */
import { DEPT_ESTADO_COR } from "../demo";
import { ROOM_D, ROOM_W, WALL_H, roomOrigin } from "../config";
import { depth, iso, pts, shade } from "../iso";
import type { Agent, AgentStatus, Department, DeptStatus } from "../types";
import { AgentSprite } from "./agent-sprite";
import { Desk, FocoDeLuz, Pendente, Prop } from "./furniture";

const MADEIRA = ["#b58a63", "#ab8059", "#bc9269"];

export function Room({ dept, agentes, statuses, status, selecionado, agenteSelecionado, onSelectDept, onSelectAgent }: {
  dept: Department; agentes: Agent[]; statuses: Record<string, AgentStatus>; status: DeptStatus;
  selecionado: boolean; agenteSelecionado: string | null;
  onSelectDept: (id: string) => void; onSelectAgent: (id: string) => void;
}) {
  const o = roomOrigin(dept);
  const up = (p: { x: number; y: number }, h = WALL_H) => ({ x: p.x, y: p.y - h });

  // piso em tábuas de madeira (direção x), com variação sutil de tom
  const tabuas: React.ReactNode[] = [];
  for (let i = 0; i < ROOM_W; i++) {
    for (let j = 0; j < ROOM_D; j++) {
      const cor = MADEIRA[(i * 7 + j * 3) % MADEIRA.length];
      tabuas.push(<polygon key={`t${i}-${j}`} fill={cor}
        points={pts([iso(o.x + i, o.y + j), iso(o.x + i + 1, o.y + j), iso(o.x + i + 1, o.y + j + 1), iso(o.x + i, o.y + j + 1)])} />);
    }
    for (let j = 0; j < ROOM_D * 2; j++) {
      const a = iso(o.x, o.y + j / 2), b = iso(o.x + ROOM_W, o.y + j / 2);
      if (i === 0) tabuas.push(<line key={`l${j}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#8a6343" strokeWidth={0.6} opacity={0.45} />);
    }
  }
  const tapete = [iso(o.x + 0.9, o.y + 0.9), iso(o.x + ROOM_W - 0.9, o.y + 0.9), iso(o.x + ROOM_W - 0.9, o.y + ROOM_D - 0.9), iso(o.x + 0.9, o.y + ROOM_D - 0.9)];

  const a = iso(o.x, o.y), b = iso(o.x + ROOM_W, o.y), d = iso(o.x, o.y + ROOM_D);
  // caixilhos verticais das divisórias de vidro
  const montantes: React.ReactNode[] = [];
  for (let k = 0; k <= ROOM_W; k += 2) {
    const p = iso(o.x + k, o.y);
    montantes.push(<line key={`mx${k}`} x1={p.x} y1={p.y} x2={p.x} y2={p.y - WALL_H} stroke="#3a4150" strokeWidth={1.4} />);
  }
  for (let k = 2; k <= ROOM_D; k += 2) {
    const p = iso(o.x, o.y + k);
    montantes.push(<line key={`my${k}`} x1={p.x} y1={p.y} x2={p.x} y2={p.y - WALL_H} stroke="#3a4150" strokeWidth={1.4} />);
  }

  const itens: { d: number; n: React.ReactNode }[] = [];
  dept.props.forEach((p, i) => itens.push({ d: depth(o.x + p.x, o.y + p.y), n: <Prop key={`p${i}`} kind={p.kind} x={o.x + p.x} y={o.y + p.y} cor={dept.cor} /> }));
  agentes.forEach((ag) => {
    const st = statuses[ag.id];
    const mx = o.x + ag.mesa.x, my = o.y + ag.mesa.y;
    const ligado = st?.state === "working" || st?.state === "thinking";
    itens.push({ d: depth(mx, my) + 1, n: <Desk key={`d${ag.id}`} x={mx} y={my} ligado={ligado} cor={dept.cor} /> });
    if (st) {
      itens.push({ d: depth(mx + 1, my + 1.6), n: <AgentSprite key={`a${ag.id}`} agent={ag} status={st} x={mx + 1} y={my + 1.55}
        selecionado={agenteSelecionado === ag.id} onSelect={onSelectAgent} /> });
    }
  });
  itens.sort((p, q) => p.d - q.d);

  const placa = iso(o.x + 0.6, o.y, WALL_H - 12);
  const lamp = DEPT_ESTADO_COR[status.estado];
  const largura = dept.nome.length * 7.6 + 36;

  return (
    <g className={`office-room ${selecionado ? "is-selected" : ""}`} data-dept={dept.id}>
      <g onClick={(e) => { e.stopPropagation(); onSelectDept(dept.id); }} className="office-room-hit" role="button" tabIndex={0}
        aria-label={`Departamento ${dept.nome}: ${status.estado}`}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelectDept(dept.id); }}>
        <title>{`${dept.nome} · ${status.estado}`}</title>
        {tabuas}
        <polygon points={pts(tapete)} fill={shade(dept.cor, 0.62)} opacity={0.55} stroke={shade(dept.cor, 0.3)} strokeWidth={1.5} />
        {/* divisórias de vidro */}
        <polygon points={pts([d, a, up(a), up(d)])} fill="#cfe0f0" opacity={0.22} />
        <polygon points={pts([a, b, up(b), up(a)])} fill="#dbe8f5" opacity={0.28} />
        {montantes}
        <polyline points={pts([d, a, b])} fill="none" stroke="#2a2f3a" strokeWidth={3} />
        <polyline points={pts([up(d), up(a), up(b)])} fill="none" stroke={shade(dept.cor, -0.15)} strokeWidth={4} strokeLinejoin="round" />
        <polygon className="office-room-outline" points={pts([a, b, iso(o.x + ROOM_W, o.y + ROOM_D), d])} />
        {/* placa de latão */}
        <g transform={`translate(${placa.x} ${placa.y}) skewY(26.565)`}>
          <rect x={0} y={-15} width={largura} height={22} rx={2} fill="url(#office-latao)" stroke="#8a6d3b" strokeWidth={0.8} />
          <circle cx={11} cy={-4} r={4.5} fill={lamp} stroke="#1f2937" strokeWidth={1}
            className={status.estado === "Em atividade" || status.estado === "Atenção" ? "office-lamp--pulse" : ""} />
          <text x={22} y={0} fontSize={11.5} fontWeight={700} fill="#2b2112" letterSpacing={1.2}>{dept.nome.toUpperCase()}</text>
        </g>
      </g>
      {agentes.map((ag) => <FocoDeLuz key={`f${ag.id}`} x={o.x + ag.mesa.x + 1} y={o.y + ag.mesa.y + 0.9} />)}
      {itens.map((i) => i.n)}
      {agentes.map((ag) => <Pendente key={`pe${ag.id}`} x={o.x + ag.mesa.x + 1} y={o.y + ag.mesa.y + 0.5} />)}
    </g>
  );
}
