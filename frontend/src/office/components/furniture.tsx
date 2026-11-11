/** Mobiliário de alto padrão (SVG isométrico): nogueira, metal escuro, vidro, latão e luz quente. */
import { iso, isoBox, pts, shade } from "../iso";
import type { PropKind } from "../types";

const NOGUEIRA = "#7a5133";
const METAL = "#2a2f3a";
const LATAO = "#c9a45c";

export function Box({ x, y, w, d, h, z = 0, cor, className, opacity }: {
  x: number; y: number; w: number; d: number; h: number; z?: number; cor: string; className?: string; opacity?: number;
}) {
  const b = isoBox(x, y, w, d, h, z);
  return (
    <g className={className} opacity={opacity}>
      <polygon points={b.left} fill={shade(cor, -0.16)} />
      <polygon points={b.right} fill={shade(cor, -0.34)} />
      <polygon points={b.top} fill={cor} />
    </g>
  );
}

/** Sombra suave no piso (gradiente radial; sem filtros, para não pesar). */
export function Sombra({ x, y, w, d, forca = 1 }: { x: number; y: number; w: number; d: number; forca?: number }) {
  const c = iso(x + w / 2, y + d / 2);
  return <ellipse cx={c.x} cy={c.y + 2} rx={(w + d) * 17} ry={(w + d) * 8.5} fill="url(#office-sombra)" opacity={forca} />;
}

/** Foco de luz quente da luminária pendente sobre o piso/mesa. */
export function FocoDeLuz({ x, y }: { x: number; y: number }) {
  const c = iso(x, y);
  return <ellipse cx={c.x} cy={c.y} rx={58} ry={29} fill="url(#office-luz)" className="office-light-pool" />;
}

export function Pendente({ x, y }: { x: number; y: number }) {
  const topo = iso(x, y, 128), cupula = iso(x, y, 96);
  return (
    <g>
      <line x1={topo.x} y1={topo.y} x2={cupula.x} y2={cupula.y} stroke="#111827" strokeWidth={1} opacity={0.7} />
      <path d={`M${cupula.x - 9},${cupula.y + 6} Q${cupula.x},${cupula.y - 8} ${cupula.x + 9},${cupula.y + 6} Z`} fill={LATAO} />
      <ellipse cx={cupula.x} cy={cupula.y + 6} rx={9} ry={3} fill="#fff4d6" className="office-bulb" />
    </g>
  );
}

/** Estação de trabalho: tampo de nogueira, pés metálicos, dois monitores que acendem com o trabalho real. */
export function Desk({ x, y, ligado, cor }: { x: number; y: number; ligado: boolean; cor: string }) {
  const telaA = isoBox(x + 0.35, y + 0.18, 0.62, 0.06, 18, 21);
  const telaB = isoBox(x + 1.05, y + 0.18, 0.62, 0.06, 18, 21);
  return (
    <g>
      <Sombra x={x} y={y} w={2} d={1} forca={0.9} />
      <Box x={x + 0.05} y={y + 0.08} w={0.08} d={0.84} h={16} cor={METAL} />
      <Box x={x + 1.87} y={y + 0.08} w={0.08} d={0.84} h={16} cor={METAL} />
      <Box x={x} y={y} w={2} d={1} h={3} z={16} cor={NOGUEIRA} />
      <Box x={x + 0.62} y={y + 0.22} w={0.06} d={0.06} h={4} z={19} cor="#111827" />
      <Box x={x + 1.32} y={y + 0.22} w={0.06} d={0.06} h={4} z={19} cor="#111827" />
      <Box x={x + 0.35} y={y + 0.18} w={0.62} d={0.06} h={18} z={21} cor="#0f141c" />
      <Box x={x + 1.05} y={y + 0.18} w={0.62} d={0.06} h={18} z={21} cor="#0f141c" />
      <polygon points={telaA.left} className={`office-screen ${ligado ? "office-screen--on" : ""}`} style={{ ["--tela" as string]: cor }} />
      <polygon points={telaB.left} className={`office-screen ${ligado ? "office-screen--on" : ""}`} style={{ ["--tela" as string]: shade(cor, 0.35), animationDelay: "0.4s" }} />
      <Box x={x + 0.55} y={y + 0.58} w={0.85} d={0.22} h={1.2} z={19} cor="#e5e7eb" />
      <Box x={x + 1.6} y={y + 0.6} w={0.16} d={0.16} h={6} z={19} cor="#f8fafc" />
    </g>
  );
}

function Leds({ x, y, n }: { x: number; y: number; n: number }) {
  return (
    <g>
      {Array.from({ length: n }, (_, i) => {
        const p = iso(x + 0.18 + (i % 2) * 0.32, y + 0.9, 12 + Math.floor(i / 2) * 13);
        return <rect key={i} x={p.x} y={p.y} width={3} height={1.6} className="office-led" style={{ animationDelay: `${i * 0.37}s` }} />;
      })}
    </g>
  );
}

function Planta({ x, y }: { x: number; y: number }) {
  const c = iso(x + 0.25, y + 0.25, 30);
  const folhas = [[-10, 8, 9, "#2f6b3a"], [10, 6, 9, "#3c7f47"], [-4, -6, 10, "#4a9356"], [7, -14, 8, "#3c7f47"],
    [-8, -20, 7, "#56a463"], [2, -26, 7, "#4a9356"]] as const;
  return (
    <g>
      <Sombra x={x} y={y} w={0.5} d={0.5} />
      <Box x={x} y={y} w={0.5} d={0.5} h={22} cor="#ece7df" />
      <line x1={c.x} y1={c.y + 8} x2={c.x} y2={c.y - 24} stroke="#5b4636" strokeWidth={1.5} />
      {folhas.map(([dx, dy, r, f], i) => <ellipse key={i} cx={c.x + dx} cy={c.y + dy} rx={r} ry={r * 0.72} fill={f} />)}
    </g>
  );
}

export function Prop({ kind, x, y, cor }: { kind: PropKind; x: number; y: number; cor: string }) {
  switch (kind) {
    case "plant":
      return <Planta x={x} y={y} />;
    case "server":
      return (
        <g>
          <Sombra x={x} y={y} w={0.8} d={0.9} />
          <Box x={x} y={y} w={0.8} d={0.9} h={74} cor="#161b24" />
          <polygon points={isoBox(x, y + 0.9, 0.8, 0.001, 70, 2).left} fill="#5b8bd6" opacity={0.08} />
          <Leds x={x} y={y} n={10} />
        </g>
      );
    case "cabinet": // aparador de nogueira com puxadores de latão
      return (
        <g>
          <Sombra x={x} y={y} w={0.7} d={0.9} />
          <Box x={x} y={y} w={0.7} d={0.9} h={30} cor={NOGUEIRA} />
          {[0.3, 0.6].map((t) => { const p = iso(x + 0.7, y + t, 18); return <rect key={t} x={p.x - 1} y={p.y} width={2} height={6} fill={LATAO} />; })}
          <Box x={x + 0.2} y={y + 0.25} w={0.3} d={0.3} h={10} z={30} cor="#e8dcc8" />
        </g>
      );
    case "shelf": {
      const livros = ["#7f1d1d", "#1e3a8a", "#a16207", "#14532d", "#4c1d95", "#9f1239", "#334155"];
      return (
        <g>
          <Sombra x={x} y={y} w={0.45} d={1.6} />
          <Box x={x} y={y} w={0.45} d={1.6} h={70} cor={NOGUEIRA} />
          {[14, 36, 56].map((z, k) => livros.map((c, i) => {
            if ((i + k) % 4 === 3) return null;
            const a = iso(x + 0.45, y + 0.12 + i * 0.2, z);
            return <rect key={`${z}-${i}`} x={a.x - 3} y={a.y - 13} width={4} height={13} fill={c} />;
          }))}
        </g>
      );
    }
    case "board": { // painel de vidro com notas
      const b = isoBox(x, y, 0.05, 1.8, 40, 20);
      return (
        <g>
          <polygon points={b.right} fill="#dbeafe" opacity={0.35} stroke="#94a3b8" strokeWidth={1.2} />
          {["#fde68a", "#fbcfe8", "#bfdbfe", "#bbf7d0", "#fed7aa"].map((c, i) => {
            const p = iso(x + 0.05, y + 0.3 + (i % 3) * 0.48, 50 - Math.floor(i / 3) * 14);
            return <polygon key={i} points={pts([p, { x: p.x + 8, y: p.y + 4 }, { x: p.x + 8, y: p.y + 13 }, { x: p.x, y: p.y + 9 }])} fill={c} />;
          })}
        </g>
      );
    }
    case "chart": { // TV de parede com painel de indicadores
      const b = isoBox(x, y, 0.05, 1.9, 34, 26);
      return (
        <g>
          <polygon points={b.right} fill="#0b1220" stroke="#1f2937" strokeWidth={2} />
          {[10, 18, 13, 24, 20].map((h, i) => {
            const p = iso(x + 0.05, y + 0.35 + i * 0.3, 30);
            return <polygon key={i} points={pts([p, { x: p.x + 6, y: p.y + 3 }, { x: p.x + 6, y: p.y + 3 - h }, { x: p.x, y: p.y - h }])} fill={cor} className="office-chart-bar" style={{ animationDelay: `${i * 0.3}s` }} />;
          })}
        </g>
      );
    }
    case "table": { // mesa de reunião em vidro com cadeiras
      const cadeiras = [[0.15, -0.55], [0.95, -0.55], [-0.55, 0.3], [2.25, 0.3], [0.15, 1.35], [0.95, 1.35]];
      return (
        <g>
          <Sombra x={x} y={y} w={2} d={1.2} />
          {cadeiras.slice(0, 3).map(([dx, dy], i) => <Box key={i} x={x + dx} y={y + dy} w={0.5} d={0.45} h={10} cor="#3b3f4a" />)}
          <Box x={x + 0.9} y={y + 0.5} w={0.2} d={0.2} h={14} cor={METAL} />
          <Box x={x} y={y} w={2} d={1.2} h={2} z={14} cor="#cfe3f1" opacity={0.75} />
          {cadeiras.slice(3).map(([dx, dy], i) => <Box key={i} x={x + dx} y={y + dy} w={0.5} d={0.45} h={10} cor="#3b3f4a" />)}
        </g>
      );
    }
    case "sofa": // sofá de design com almofadas
      return (
        <g>
          <Sombra x={x} y={y} w={2.2} d={1} />
          <Box x={x} y={y} w={2.2} d={0.3} h={24} cor={shade(cor, -0.25)} />
          <Box x={x} y={y + 0.3} w={2.2} d={0.7} h={11} cor={shade(cor, -0.1)} />
          <Box x={x + 0.25} y={y + 0.32} w={0.45} d={0.15} h={10} z={11} cor={LATAO} />
          <Box x={x + 1.5} y={y + 0.32} w={0.45} d={0.15} h={10} z={11} cor="#e8dcc8" />
        </g>
      );
    case "printer":
      return (
        <g>
          <Sombra x={x} y={y} w={0.8} d={0.6} />
          <Box x={x} y={y} w={0.8} d={0.6} h={16} cor="#d4d4d8" />
          <Box x={x + 0.1} y={y + 0.1} w={0.6} d={0.3} h={2} z={16} cor="#fafafa" />
        </g>
      );
    case "boxes": // arquivo de revistas
      return (
        <g>
          <Sombra x={x} y={y} w={0.7} d={0.6} />
          <Box x={x} y={y} w={0.7} d={0.6} h={14} cor="#d8c3a5" />
          <Box x={x} y={y} w={0.7} d={0.6} h={14} z={14} cor="#cdb592" />
          <Box x={x + 0.08} y={y + 0.06} w={0.55} d={0.5} h={10} z={28} cor="#e3d2b8" />
        </g>
      );
    case "water": // estação de café
      return (
        <g>
          <Sombra x={x} y={y} w={0.6} d={0.5} />
          <Box x={x} y={y} w={0.6} d={0.5} h={26} cor={NOGUEIRA} />
          <Box x={x + 0.1} y={y + 0.08} w={0.32} d={0.3} h={14} z={26} cor="#1f2937" />
          <Box x={x + 0.45} y={y + 0.2} w={0.08} d={0.08} h={4} z={26} cor="#f8fafc" />
        </g>
      );
  }
}
