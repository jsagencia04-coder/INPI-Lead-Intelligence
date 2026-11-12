"use client";

import { usePathname } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { TOM, itemAtual } from "@/lib/nav";

/** Cabeçalho padrão das telas: identidade do módulo (ícone e cor), título, descrição e ações. */
export function PageHeader({ title, description, children }: { title: string; description?: string; children?: React.ReactNode }) {
  const atual = itemAtual(usePathname());
  const tom = atual ? TOM[atual.item.tom] : null;
  const Icon = atual?.item.icon;
  return (
    <div className="entrar mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="flex min-w-0 items-center gap-4">
        {Icon && tom && (
          <div className={cn("hidden size-12 shrink-0 place-items-center rounded-2xl bg-gradient-to-br text-white shadow-lg sm:grid", tom.chip)}
            style={{ boxShadow: `0 10px 24px -10px ${tom.hex}` }}>
            <Icon className="size-6" />
          </div>
        )}
        <div className="min-w-0">
          {atual && <div className={cn("eyebrow", tom?.texto)}>{atual.grupo}</div>}
          <h1 className="text-2xl font-semibold tracking-tight md:text-[1.7rem]">{title}</h1>
          {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
        </div>
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-700 dark:text-red-300">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <span>
        Não foi possível falar com a API: {error}.
        {/fetch|500|502|503|ECONN/i.test(error) && <span> Confira se o serviço da API está no ar e abra <code>/health</code>.</span>}
      </span>
    </div>
  );
}
