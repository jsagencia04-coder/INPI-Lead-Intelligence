-- V2.14 · Primeiro contato pelo sistema sem autorização prévia (decisão do titular do sistema em 17/11/2026).
-- Base legal do 1º contato: legítimo interesse (B2B), só para WhatsApp publicado pela própria empresa ou confirmado
-- por pessoa. Continuam valendo: descadastro (opt-out), lead aprovado, uma única mensagem por contato, limite diário,
-- botão de emergência e auditoria. Para voltar à regra anterior: valor = 'consentimento'.
insert into app_config (chave, valor) values ('primeiro_contato_base_legal', 'legitimo_interesse')
on conflict (chave) do update set valor = excluded.valor, atualizado_em = now();
