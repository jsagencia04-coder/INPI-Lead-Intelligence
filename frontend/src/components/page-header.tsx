export function PageHeader({ title, description, children }: { title: string; description?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-sm text-muted-foreground mt-1">{description}</p>}
      </div>
      {children}
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
      Não foi possível falar com a API: {error}.
      {/fetch|500|502|503|ECONN/i.test(error) && (
        <span> Confira se o backend está rodando (janela do <code>uvicorn</code>) e abra <code>/health</code> no navegador.</span>
      )}
    </div>
  );
}
