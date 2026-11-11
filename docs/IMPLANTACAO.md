# Implantação (Fase 7)

Há três formas de colocar o sistema no ar, da mais simples para a mais completa.

## A. No seu computador, com Docker (mais simples)

Requer Docker Desktop. Na pasta do projeto:

```bash
cp backend/.env.example backend/.env      # edite: ANTHROPIC_API_KEY e o orçamento
docker compose -f docker-compose.prod.yml up -d --build
```

Abra http://localhost:3000. Banco, arquivos originais e cache da Receita ficam em volumes do Docker.
Esta opção resolve o principal risco de rede: o computador de casa ou do escritório
acessa o site do INPI normalmente.

## B. Na nuvem: Supabase + Render + Vercel

| Parte | Onde | Observação |
|---|---|---|
| Banco + arquivos + login | Supabase | Bucket privado `rpi-originais` |
| API + worker | Render (`render.yaml`) | Uma imagem, dois serviços |
| Telas | Vercel | `BACKEND_URL` = endereço da API no Render |

1. **Supabase.** Crie o projeto. Em *Storage*, crie o bucket **privado** `rpi-originais`.
   Em *Authentication > Users*, crie os usuários (não há cadastro público). Anote: URL do
   projeto, *anon key*, *service role key*, JWT secret (se o projeto usar chave legada) e a
   connection string (*Session pooler*).
2. **Render.** *New > Blueprint*, aponte para o repositório (ele lê o `render.yaml`).
   Preencha as variáveis marcadas: `DATABASE_URL`, `SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` (se houver) e `ANTHROPIC_API_KEY`.
   A API aplica as migrations sozinha ao iniciar.
3. **Vercel.** Importe o repositório com *Root Directory* = `frontend`. Variáveis:
   `BACKEND_URL` (ex.: `https://inpi-api.onrender.com`), `NEXT_PUBLIC_SUPABASE_URL` e
   `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Com o Supabase configurado, as telas exigem login.

**Atenção à rede.** Servidores do Render ficam fora do Brasil, e o INPI pode bloquear esse
acesso. Se a tela Edições mostrar erro 403 ou se surgir a revisão "Consulta ao INPI
pausada", há duas saídas:
- usar o upload manual do RM.zip (Fase 2);
- rodar **só o worker** no seu computador, apontando `DATABASE_URL` e o Storage para o
  Supabase: `python -m app.worker`. API e telas continuam na nuvem.

**Base CNPJ na nuvem.** O agendamento `cnpj-receita` baixa cerca de 8 GB por mês. Ligue-o
só num worker com disco persistente (o seu computador ou um disco do Render).

## C. GitHub Codespaces (testes)

Veja `docs/TESTAR_NO_GITHUB.md`.

## Checklist de produção

- [ ] `AUTH_MODE=supabase` na API e usuários criados no Supabase
- [ ] `IA_ORCAMENTO_SEMANAL_USD` definido; preços conferidos em anthropic.com/pricing
- [ ] Bucket `rpi-originais` privado; service role key só no backend
- [ ] Tela **Operação**: agendamentos revisados; `cnpj-receita` ligado só com disco suficiente
- [ ] LGPD: LIA (avaliação de legítimo interesse) documentado e procedimento de opt-out
      definido. O botão "Opt-out" no lead já bloqueia contato e exportação.
- [ ] Backup do banco (o Supabase faz backup diário nos planos pagos)
- [ ] Acompanhar semanalmente: **Revisões**, falhas em **Operação** e o custo de IA
