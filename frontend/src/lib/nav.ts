/** Mapa de navegação da plataforma: grupos, páginas, ícones e cores de identidade de cada módulo. */
import {
  Activity, BarChart3, BookOpen, Building2, ClipboardCheck, Contact, FileText, Filter, LayoutDashboard, ListChecks,
  Map as MapIcon, MessageCircle, PlugZap, Radar, Scale, Send, Settings2, ShieldCheck, Users, type LucideIcon,
} from "lucide-react";

export type Tom = "violet" | "indigo" | "blue" | "cyan" | "emerald" | "amber" | "orange" | "rose" | "slate";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  tom: Tom;
  descricao: string;
  /** chave de pendência (/api/alerts) cujo número aparece ao lado do item */
  alerta?: string[];
  admin?: boolean;
};
export type NavGrupo = { titulo: string; itens: NavItem[] };

export const NAV: NavGrupo[] = [
  {
    titulo: "Visão geral",
    itens: [
      { href: "/", label: "Painel executivo", icon: LayoutDashboard, tom: "indigo", descricao: "Indicadores, prioridades e evolução da operação" },
      { href: "/escritorio", label: "Central de Operações IA", icon: Building2, tom: "violet", descricao: "Agentes, tarefas em andamento e escritório virtual", alerta: ["worker", "falhas"] },
    ],
  },
  {
    titulo: "Comercial",
    itens: [
      { href: "/oportunidades", label: "Oportunidades de serviço", icon: Scale, tom: "violet", descricao: "Manifestação à oposição e recurso contra indeferimento, com prazos", alerta: ["servicos_quentes", "prazos_curtos"] },
      { href: "/mapa", label: "Mapa de oportunidades", icon: MapIcon, tom: "blue", descricao: "Leads por estado, oposições e contatos validados", alerta: ["sc_quentes", "geo_pendente"] },
      { href: "/pipeline", label: "Pipeline comercial", icon: Filter, tom: "rose", descricao: "Funil de 17 etapas e a jornada de cada lead", alerta: ["respostas", "elegiveis"] },
      { href: "/leads", label: "Leads", icon: Users, tom: "orange", descricao: "Titulares qualificados, prioridade e aprovação", alerta: ["aprovar"] },
      { href: "/contatos", label: "Central de contatos", icon: Contact, tom: "emerald", descricao: "WhatsApp, telefones, e-mails, origem e autorização" },
      { href: "/primeiro-contato", label: "Primeiro contato", icon: Send, tom: "emerald", descricao: "Mensagem sugerida pela IA, aprovada por você e enviada só com autorização" },
      { href: "/integracao-whatsapp", label: "Integração WhatsApp", icon: PlugZap, tom: "cyan", descricao: "Evolution API: conexão, simulação e botão de emergência" },
      { href: "/whatsapp", label: "WhatsApp Business", icon: MessageCircle, tom: "emerald", descricao: "API oficial, mensagens e status de entrega", alerta: ["msg_falhas"] },
    ],
  },
  {
    titulo: "Inteligência INPI",
    itens: [
      { href: "/rpi-semanal", label: "Central RPI semanal", icon: Radar, tom: "indigo", descricao: "Operação de terça-feira: detecção, extração e SC → RS → PR", alerta: ["rpi_falha", "rpi_atrasada"] },
      { href: "/rpi", label: "Edições da RPI", icon: BookOpen, tom: "blue", descricao: "Revistas semanais importadas e arquivos originais" },
      { href: "/processos", label: "Processos", icon: FileText, tom: "blue", descricao: "Processos, despachos e situação do procurador" },
      { href: "/despachos", label: "Despachos", icon: ListChecks, tom: "cyan", descricao: "Classificação comercial dos despachos" },
    ],
  },
  {
    titulo: "Operação",
    itens: [
      { href: "/revisoes", label: "Revisões", icon: ClipboardCheck, tom: "amber", descricao: "Decisões que os agentes deixaram para você", alerta: ["revisoes"] },
      { href: "/jobs", label: "Agentes e jobs", icon: Activity, tom: "violet", descricao: "Fila de execução, resultados e falhas" },
      { href: "/relatorios", label: "Relatórios", icon: BarChart3, tom: "indigo", descricao: "Relatórios semanais e exportações" },
      { href: "/operacao", label: "Operação", icon: Settings2, tom: "slate", descricao: "Agenda dos agentes, custos e configuração", alerta: ["receita"] },
    ],
  },
  {
    titulo: "Administração",
    itens: [{ href: "/usuarios", label: "Usuários", icon: ShieldCheck, tom: "slate", descricao: "Acessos e perfis de permissão", admin: true }],
  },
];

export const TODOS: NavItem[] = NAV.flatMap((g) => g.itens);

export function itemAtual(pathname: string): { item: NavItem; grupo: string } | null {
  let melhor: { item: NavItem; grupo: string } | null = null;
  for (const g of NAV) {
    for (const i of g.itens) {
      const ok = i.href === "/" ? pathname === "/" : pathname === i.href || pathname.startsWith(i.href + "/");
      if (ok && (!melhor || i.href.length > melhor.item.href.length)) melhor = { item: i, grupo: g.titulo };
    }
  }
  return melhor;
}

/** Classes de cada tom de identidade (chip do ícone, texto e brilho). */
export const TOM: Record<Tom, { chip: string; texto: string; barra: string; suave: string; hex: string }> = {
  violet: { chip: "from-violet-500 to-fuchsia-500", texto: "text-violet-600", barra: "bg-violet-500", suave: "bg-violet-500/10", hex: "#8b5cf6" },
  indigo: { chip: "from-indigo-500 to-violet-500", texto: "text-indigo-600", barra: "bg-indigo-500", suave: "bg-indigo-500/10", hex: "#6366f1" },
  blue: { chip: "from-blue-500 to-sky-500", texto: "text-blue-600", barra: "bg-blue-500", suave: "bg-blue-500/10", hex: "#3b82f6" },
  cyan: { chip: "from-cyan-500 to-teal-500", texto: "text-cyan-600", barra: "bg-cyan-500", suave: "bg-cyan-500/10", hex: "#06b6d4" },
  emerald: { chip: "from-emerald-500 to-teal-500", texto: "text-emerald-600", barra: "bg-emerald-500", suave: "bg-emerald-500/10", hex: "#10b981" },
  amber: { chip: "from-amber-500 to-orange-500", texto: "text-amber-600", barra: "bg-amber-500", suave: "bg-amber-500/10", hex: "#f59e0b" },
  orange: { chip: "from-orange-500 to-rose-500", texto: "text-orange-600", barra: "bg-orange-500", suave: "bg-orange-500/10", hex: "#f97316" },
  rose: { chip: "from-rose-500 to-pink-500", texto: "text-rose-600", barra: "bg-rose-500", suave: "bg-rose-500/10", hex: "#f43f5e" },
  slate: { chip: "from-slate-600 to-slate-500", texto: "text-slate-600", barra: "bg-slate-500", suave: "bg-slate-500/10", hex: "#64748b" },
};
