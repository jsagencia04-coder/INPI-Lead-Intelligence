# Segurança

## 1. Ambientes

| `APP_ENV` | Para quê | Login | Dados fictícios |
|---|---|---|---|
| `demo` (padrão) | Testes e demonstração | Opcional | Aceitos |
| `homologacao` | Testes com dados reais | **Obrigatório** | Recusados pelo banco |
| `producao` | Operação | **Obrigatório** | Recusados pelo banco |

- O ambiente fica gravado **no banco**. Ele só sobe (demo → homologação → produção). A API se recusa a iniciar se você apontar uma configuração de ambiente inferior para um banco de ambiente superior.
- Fora do demo, o banco recusa contatos e evidências com domínios reservados (`.invalid`, `.test`, `.example`, `.local`, `example.com`, IP literal etc.).
- A API **não inicia** com configuração insegura e diz o motivo: homologação/produção sem login; `APP_SECRET_KEY` curta; CORS `*`; produção com a senha padrão do banco; envio de WhatsApp ativo sem `WHATSAPP_APP_SECRET`.
- O envio real de WhatsApp é bloqueado sem login, em qualquer ambiente.

## 2. Ligando o login próprio

No `backend/.env`:

```
APP_ENV=homologacao
AUTH_MODE=local
APP_SECRET_KEY=<valor longo e aleatório, 32+ caracteres>
BOOTSTRAP_ADMIN_EMAIL=seu@email.com.br
BOOTSTRAP_ADMIN_PASSWORD=<senha com 10+ caracteres, letras e números>
```

Para gerar a chave: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Reinicie (`docker compose -f docker-compose.prod.yml up -d --build`). O primeiro administrador é criado só se não houver nenhum usuário. Depois de entrar, **apague `BOOTSTRAP_ADMIN_PASSWORD` do arquivo** e troque a senha.

Atenção: mudar `APP_ENV` para `homologacao` é definitivo para aquele banco (o ambiente não desce).

## 3. Perfis

| Perfil | Pode |
|---|---|
| Leitor | Ver tudo. Não altera nem exporta |
| Operador | + importar RPI, disparar pesquisas, registrar contatos, anotações, prospecções e opt-out, exportar, cancelar mensagem na fila |
| Revisor | + aprovar leads, confirmar contatos, escolher CNPJ, resolver revisões, preparar mensagens de WhatsApp, ver auditoria |
| Administrador | + usuários, agenda dos agentes, classificação de despachos, jobs avulsos |

- A política está em um único lugar (`backend/app/security.py`, lista `REGRAS`).
- **Negar é o padrão**: uma rota de alteração nova, sem regra, nasce restrita a administrador.
- O último administrador ativo não pode ser rebaixado nem desativado.
- No login via Supabase vale a mesma tabela de usuários: e-mail fora da lista não entra.

## 4. Proteções do login

- Senhas com scrypt (nunca em texto, nunca na auditoria).
- 5 erros seguidos bloqueiam a conta por 15 minutos; 10 tentativas por minuto por endereço.
- A resposta de erro é única: não revela se o e-mail existe.
- Sessão de 12 horas (`TOKEN_HORAS`). Usuário desativado perde o acesso na hora.
- Erros de token não devolvem detalhes.

## 5. SSRF (acesso a endereços de fora)

Todo acesso a sites de titulares e a páginas citadas pela pesquisa passa por `backend/app/net_guard.py`:
só http/https nas portas 80/443; o nome é resolvido e todos os IPs precisam ser públicos; redirecionamentos seguidos manualmente (máx. 5), cada salto conferido; resposta limitada a 3 MB; nomes sem ponto (ex.: `db`) e IPs literais recusados.

Risco residual: DNS rebinding (o nome mudar de IP entre a conferência e a conexão). Mitigação possível no futuro: fixar o IP conferido na conexão.

## 6. Segredos

- Chaves de API, token do WhatsApp e `APP_SECRET_KEY` ficam só no `backend/.env`, que não entra no pacote nem na imagem.
- Nenhuma rota devolve segredo; a tela do WhatsApp mostra apenas se cada um está definido.

## 7. Auditoria

Todas as tabelas de negócio têm gatilho de auditoria (quem, quando, antes e depois), agora incluindo publicações, vínculo lead–processo, pesquisas, relatórios, exportações, usuários e configuração de ambiente.

## 8. Pendências conhecidas

- O token do escritório virtual ainda vai na URL do WebSocket (pode aparecer em logs de proxy).
- Limite de taxa é por processo, em memória (suficiente para uma instância).
- Backup: ainda não há rotina automática. Enquanto isso: `docker compose -f docker-compose.prod.yml exec db pg_dump -U postgres inpi > backup.sql`.
- Sem segundo fator de autenticação.
- A limpeza de eventos do escritório com mais de 30 dias continua ativa (apontada na auditoria V1.5).
