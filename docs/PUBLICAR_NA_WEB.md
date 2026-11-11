# Publicar na web e atualizar continuamente

Objetivo: o sistema em um endereço `https://`, funcionando 24 horas, recebendo atualizações sem perder dados.

## Por que um servidor próprio (VPS)

O sistema tem três partes que precisam ficar ligadas o tempo todo (telas, API e o **worker** dos agentes), mais o banco e cerca de **8 GB** da base CNPJ da Receita em disco. Hospedagens gratuitas desligam o worker ou não têm esse disco. Um VPS Linux pequeno resolve tudo em uma máquina só:

- 2 vCPU, 4 GB de RAM, **40 GB de disco** ou mais, Ubuntu 24.04.
- Um domínio (ou subdomínio) apontando para o IP do servidor.

## O que só você pode fazer

1. Contratar o VPS e anotar o IP.
2. Ter um domínio e criar um registro DNS tipo **A** (ex.: `sistema.seudominio.com.br` → IP do servidor).
3. Criar um repositório **privado** no GitHub e enviar o projeto para ele.

## Primeira publicação (no servidor, por SSH)

```bash
# 1. Docker
curl -fsSL https://get.docker.com | sh

# 2. Projeto
git clone https://github.com/SEU-USUARIO/inpi-lead-intelligence.git
cd inpi-lead-intelligence

# 3. Configuração
cp .env.web.example .env            # preencha DOMINIO e POSTGRES_PASSWORD
cp backend/.env.example backend/.env
nano backend/.env
```

No `backend/.env`, o mínimo para a web (login é **obrigatório**):

```
APP_ENV=homologacao
AUTH_MODE=local
APP_SECRET_KEY=<gere com: openssl rand -hex 32>
BOOTSTRAP_ADMIN_EMAIL=seu@email.com.br
BOOTSTRAP_ADMIN_PASSWORD=<senha com 10+ caracteres, letras e números>
```

Apague as linhas `AUTH_MODE=dev` e `DATABASE_URL=` do arquivo, se existirem (o compose define o banco).

```bash
# 4. Subir
docker compose -f docker-compose.web.yml up -d --build
```

Abra `https://SEU-DOMINIO`. O certificado HTTPS é emitido sozinho no primeiro acesso (leva até um minuto). Entre com o administrador, troque a senha e apague `BOOTSTRAP_ADMIN_PASSWORD` do arquivo.

Firewall: libere só as portas 22, 80 e 443 (`ufw allow 22,80,443/tcp && ufw enable`).

## Atualizar (em tempo real, sem perder dados)

Sempre que houver versão nova no GitHub:

```bash
./deploy/atualizar.sh
```

O script faz **backup do banco**, baixa a versão, reconstrói e sobe. As migrations entram sozinhas; os dados ficam nos volumes do Docker e não são tocados. A troca leva de um a três minutos.

**Automático:** o arquivo `.github/workflows/deploy.yml` roda esse mesmo script a cada envio para a branch `main`, **depois que os testes passam**. Para ligar: cadastre no GitHub os segredos `SERVIDOR_HOST`, `SERVIDOR_USUARIO`, `SERVIDOR_CHAVE_SSH` e a variável `DEPLOY_ATIVO=true`.

## Trazer os dados do seu computador (opcional)

No seu computador:
```powershell
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres inpi > inpi.sql
```
Envie `inpi.sql` ao servidor e, **antes do primeiro acesso**:
```bash
docker compose -f docker-compose.web.yml up -d db
docker compose -f docker-compose.web.yml exec -T db psql -U postgres inpi < inpi.sql
docker compose -f docker-compose.web.yml up -d --build
```

## WhatsApp Business

Com o sistema na web, o webhook passa a funcionar: `https://SEU-DOMINIO/webhooks/whatsapp` (veja `WHATSAPP_API.md`).

## Cuidados

- O ambiente `homologacao` é definitivo para aquele banco e recusa dados fictícios.
- Os backups ficam em `backups/` no próprio servidor; copie-os para outro lugar de tempos em tempos.
- A sincronização da base CNPJ baixa cerca de 8 GB na primeira vez.
