-- Correção da busca de WhatsApp (diagnóstico com dados reais em 11/11/2026).
-- 1) Celulares da Receita no formato antigo (DDD + 8 dígitos) eram descartados: o agente cnpj.recontatos
--    regrava os contatos a partir da base local já baixada (sem novo download). Roda agora e depois 1x por dia.
-- 2) A pesquisa gratuita passa a ser refeita com o método novo (controle por research_runs.modelo).
insert into schedules (nome, tipo, intervalo_minutos, proximo_em)
values ('receita-contatos', 'cnpj.recontatos', 1440, now())
on conflict (nome) do nothing;

-- a pesquisa gratuita melhorada roda já na próxima passada do agendador
update schedules set proximo_em = now() where nome = 'pesquisa-gratuita';
