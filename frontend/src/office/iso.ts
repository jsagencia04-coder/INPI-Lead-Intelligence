/** Projeção isométrica 2:1. Coordenadas de mundo em "tiles"; retorno em pixels SVG. */
export const TILE_W = 64;
export const TILE_H = 32;

export type Pt = { x: number; y: number };

export function iso(x: number, y: number, z = 0): Pt {
  return { x: (x - y) * (TILE_W / 2), y: (x + y) * (TILE_H / 2) - z };
}

export function pts(list: Pt[]): string {
  return list.map((p) => `${round(p.x)},${round(p.y)}`).join(" ");
}

const round = (n: number) => Math.round(n * 10) / 10;

/** Faces de uma caixa isométrica: base em (x,y), tamanho w×d tiles, altura h px. */
export function isoBox(x: number, y: number, w: number, d: number, h: number, z = 0) {
  const a = iso(x, y, z), b = iso(x + w, y, z), c = iso(x + w, y + d, z), dd = iso(x, y + d, z);
  const up = (p: Pt) => ({ x: p.x, y: p.y - h });
  return {
    top: pts([up(a), up(b), up(c), up(dd)]),
    right: pts([b, c, up(c), up(b)]), // face voltada para +x
    left: pts([dd, c, up(c), up(dd)]), // face voltada para +y
  };
}

/** Profundidade para ordenar o desenho (o que está "mais à frente" é desenhado depois). */
export function depth(x: number, y: number): number {
  return x + y;
}

/** Clareia/escurece uma cor hex (fator -1..1). */
export function shade(hex: string, f: number): string {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) =>
    Math.max(0, Math.min(255, Math.round(f < 0 ? c * (1 + f) : c + (255 - c) * f))),
  );
  return "#" + ch.map((c) => c.toString(16).padStart(2, "0")).join("");
}

/** Limita o zoom e aplica zoom ancorado em um ponto da tela. */
export function zoomAt(view: { x: number; y: number; s: number }, factor: number, px: number, py: number,
  min = 0.35, max = 3) {
  const s = Math.max(min, Math.min(max, view.s * factor));
  const k = s / view.s;
  return { s, x: px - (px - view.x) * k, y: py - (py - view.y) * k };
}
