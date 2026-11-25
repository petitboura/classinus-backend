-- Classinus: la limite de serveurs MCP par compte passe de 10 à 1000 (demande du 25/11/2026).
-- Même mécanisme que la migration du 23/10 : la base garantit la limite même si deux ajouts arrivent en même temps.
-- La valeur doit rester identique à NOMBRE_MAX_SERVEURS_PAR_COMPTE dans connexions/mcp_personnalises.py.

create or replace function public.mcp_personnalises_limiter()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    -- Verrou propre à ce compte : deux ajouts simultanés passent l'un après l'autre.
    perform pg_advisory_xact_lock(hashtextextended('mcp_personnalises:' || new.user_id::text, 0));
    if (select count(*) from public.mcp_personnalises where user_id = new.user_id) >= 1000 then
        raise exception 'MCP_LIMITE_ATTEINTE' using errcode = 'P0001';
    end if;
    return new;
end;
$$;
