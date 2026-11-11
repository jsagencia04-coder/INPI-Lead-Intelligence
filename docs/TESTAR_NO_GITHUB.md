# Testar no navegador com o GitHub Codespaces

Nada é instalado no seu computador. O sistema roda num computador do GitHub, que você
abre pelo navegador.

## Primeira vez (cerca de 10 minutos)

1. **Crie o repositório.** Em https://github.com/new:
   - Nome: `inpi-lead-intelligence`
   - Marque **Private**
   - Marque **Add a README file**
   - Clique em **Create repository**

2. **Abra o Codespace.** No repositório, clique no botão verde **Code** → aba
   **Codespaces** → **Create codespace on main**. Em cerca de 1 minuto, abre um editor
   parecido com o VS Code.

3. **Envie o projeto.** Arraste o arquivo `inpi-lead-intelligence-v1.0.zip` do seu
   computador para o painel de arquivos, à esquerda do editor.

4. **Rode o comando.** No terminal (parte de baixo da tela), cole e aperte Enter:

   ```bash
   unzip -oq inpi-lead-intelligence-*.zip && cp -rf inpi-lead-intelligence/. . && rm -rf inpi-lead-intelligence inpi-lead-intelligence-*.zip && bash scripts/iniciar.sh
   ```

   Na primeira vez, ele instala tudo (3 a 5 minutos). Quando aparecer **Pronto!**,
   abra o link mostrado no terminal. Se preferir, use a aba **PORTAS** e clique no globo
   da porta 3000.

5. **Importe a RPI.** Nas telas, vá em **Edições da RPI** → **Verificar novas edições**.
   O terminal mostra o que os agentes estão fazendo. Em 1 a 2 minutos, a edição aparece
   como **Processada**.

6. **Opcional: salve no GitHub** para não precisar repetir os passos 3 e 4. No terminal,
   aperte Ctrl+C e rode:

   ```bash
   git add -A && git commit -m "Projeto INPI Lead Intelligence" && git push
   ```

## Nas próximas vezes

O Codespace desliga sozinho depois de 30 minutos parado, e seus dados continuam lá.
Para voltar, abra https://github.com/codespaces, clique no seu Codespace e rode no terminal:

```bash
bash scripts/iniciar.sh
```

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| A edição fica em **Erro** com "403" ou "timeout" | O site do INPI pode estar bloqueando servidores do GitHub. Baixe o XML em https://revistas.inpi.gov.br/rpi/ (coluna Marcas, link "XML") e use **Enviar RM.zip** na tela Edições da RPI. |
| "As telas não subiram" | Rode de novo `bash scripts/iniciar.sh`. Se persistir, mande o conteúdo de `logs/web.log` e `logs/api.log`. |
| Quero começar do zero | `docker compose down -v` apaga o banco. Depois, rode `bash scripts/iniciar.sh`. |

## Custo

Contas pessoais do GitHub têm uma cota gratuita mensal de Codespaces, suficiente para
testes. O consumo só acontece enquanto o Codespace está ligado. Para não gastar à toa,
pare o Codespace em https://github.com/codespaces (menu **⋯** → **Stop codespace**).
