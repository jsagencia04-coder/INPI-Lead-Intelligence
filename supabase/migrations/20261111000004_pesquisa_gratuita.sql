-- Pesquisa gratuita de contatos: leitura dos sites oficiais (sem IA, sem buscador pago).
insert into schedules (nome, tipo, intervalo_minutos, ativo)
values ('pesquisa-gratuita', 'research.free_batch', 60, true)
on conflict (nome) do nothing;
