-- Classinus: limite de 10 serveurs MCP par compte, garantie par la base.
-- Sans cela, deux ajouts envoyés en même temps passaient tous les deux la vérification
-- du backend (qui compte puis insère) et dépassaient la limite.

create or replace function public.mcp_personnalises_limiter()
returns trigger
language plpgsql
as $$
begin
    -- Verrou propre à ce compte : deux ajouts simultanés passent l'un après l'autre.
    perform pg_advisory_xact_lock(hashtextextended('mcp_personnalises:' || new.user_id::text, 0));
    if (select count(*) from public.mcp_personnalises where user_id = new.user_id) >= 10 then
        raise exception 'MCP_LIMITE_ATTEINTE' using errcode = 'P0001';
    end if;
    return new;
end;
$$;

drop trigger if exists mcp_personnalises_limiter_avant_ajout on public.mcp_personnalises;
create trigger mcp_personnalises_limiter_avant_ajout
    before insert on public.mcp_personnalises
    for each row execute function public.mcp_personnalises_limiter();
