/*
Outil d'exécution de code Classinus avec E2B.
Appliquer cette migration sur Supabase avant d'activer l'outil.
Seul le service-role du backend peut utiliser ces tables et RPC. Pas de policy côté client.
*/
CREATE TABLE IF NOT EXISTS public.execution_code_configuration (
    id boolean PRIMARY KEY DEFAULT true CHECK (id = true),
    minutes_per_day integer NOT NULL DEFAULT 10 CHECK (minutes_per_day > 0),
    minutes_per_month integer NOT NULL DEFAULT 60 CHECK (minutes_per_month > 0),
    max_command_seconds integer NOT NULL DEFAULT 60 CHECK (max_command_seconds BETWEEN 1 AND 60),
    max_download_seconds integer NOT NULL DEFAULT 60 CHECK (max_download_seconds BETWEEN 1 AND 60),
    file_operation_reserve_seconds integer NOT NULL DEFAULT 10 CHECK (file_operation_reserve_seconds > 0),
    inactivity_seconds integer NOT NULL DEFAULT 300 CHECK (inactivity_seconds > 0),
    monthly_budget_usd numeric(12,4) NOT NULL DEFAULT 100.00 CHECK (monthly_budget_usd > 0 AND monthly_budget_usd <= 100.00),
    estimated_cost_per_second_usd numeric(14,10) NOT NULL DEFAULT 0.000100 CHECK (estimated_cost_per_second_usd >= 0.000100),
    startup_reserve_seconds integer NOT NULL DEFAULT 60 CHECK (startup_reserve_seconds >= 0),
    max_output_chars integer NOT NULL DEFAULT 20000 CHECK (max_output_chars >= 1000),
    max_file_bytes bigint NOT NULL DEFAULT 1048576 CHECK (max_file_bytes >= 1024),
    max_files_per_download integer NOT NULL DEFAULT 50 CHECK (max_files_per_download > 0),
    max_download_bytes bigint NOT NULL DEFAULT 5000000 CHECK (max_download_bytes >= 1024),
    max_command_chars integer NOT NULL DEFAULT 10000 CHECK (max_command_chars >= 256),
    sandbox_timeout_seconds integer NOT NULL DEFAULT 3600 CHECK (sandbox_timeout_seconds >= 60),
    e2b_template text NOT NULL DEFAULT 'base',
    allowed_domains text[] NOT NULL DEFAULT ARRAY[
        'pypi.org', 'files.pythonhosted.org', 'pythonhosted.org',
        'registry.npmjs.org', 'npmjs.com', 'npmjs.org', 'www.npmjs.com', 'www.npmjs.org',
        'registry.yarnpkg.com', 'yarnpkg.com',
        'index.crates.io', 'static.crates.io', 'crates.io',
        'github.com', 'api.github.com', 'codeload.github.com',
        'raw.githubusercontent.com', 'release-assets.githubusercontent.com',
        'archive.ubuntu.com', 'security.ubuntu.com', 'conda.anaconda.org',
        'api.anthropic.com'
    ]::text[],
    updated_at timestamptz NOT NULL DEFAULT now()
);
-- La migration reste réexécutable si la table a été créée par une révision de test antérieure.
ALTER TABLE public.execution_code_configuration
    ADD COLUMN IF NOT EXISTS max_download_seconds integer NOT NULL DEFAULT 60 CHECK (max_download_seconds > 0);
INSERT INTO public.execution_code_configuration (id) VALUES (true) ON CONFLICT (id) DO NOTHING;
-- Coût estimé conservateur, à relever si les ressources du template augmentent.
UPDATE public.execution_code_configuration
SET estimated_cost_per_second_usd = GREATEST(estimated_cost_per_second_usd, 0.000100),
    monthly_budget_usd = LEAST(100.00, GREATEST(0.01, monthly_budget_usd)),
    max_command_seconds = LEAST(60, GREATEST(1, max_command_seconds)),
    max_download_seconds = LEAST(60, GREATEST(1, max_download_seconds)),
    updated_at = now()
WHERE id = true;
ALTER TABLE public.execution_code_configuration
    DROP CONSTRAINT IF EXISTS execution_code_configuration_monthly_budget_usd_check;
ALTER TABLE public.execution_code_configuration
    DROP CONSTRAINT IF EXISTS execution_code_configuration_monthly_budget_usd_100_check;
ALTER TABLE public.execution_code_configuration
    ADD CONSTRAINT execution_code_configuration_monthly_budget_usd_100_check
    CHECK (monthly_budget_usd > 0 AND monthly_budget_usd <= 100.00);
ALTER TABLE public.execution_code_configuration
    DROP CONSTRAINT IF EXISTS execution_code_configuration_estimated_cost_per_second_usd_check;
ALTER TABLE public.execution_code_configuration
    DROP CONSTRAINT IF EXISTS execution_code_configuration_estimated_cost_per_second_usd_floor_check;
ALTER TABLE public.execution_code_configuration
    ADD CONSTRAINT execution_code_configuration_estimated_cost_per_second_usd_floor_check
    CHECK (estimated_cost_per_second_usd >= 0.000100);
ALTER TABLE public.execution_code_configuration
    DROP COLUMN IF EXISTS max_concurrent_sandboxes;
ALTER TABLE public.execution_code_configuration
    DROP CONSTRAINT IF EXISTS execution_code_configuration_max_command_seconds_check;
ALTER TABLE public.execution_code_configuration
    DROP CONSTRAINT IF EXISTS execution_code_configuration_max_command_seconds_60_check;
ALTER TABLE public.execution_code_configuration
    ADD CONSTRAINT execution_code_configuration_max_command_seconds_60_check
    CHECK (max_command_seconds BETWEEN 1 AND 60);
ALTER TABLE public.execution_code_configuration
    DROP CONSTRAINT IF EXISTS execution_code_configuration_max_download_seconds_check;
ALTER TABLE public.execution_code_configuration
    DROP CONSTRAINT IF EXISTS execution_code_configuration_max_download_seconds_60_check;
ALTER TABLE public.execution_code_configuration
    ADD CONSTRAINT execution_code_configuration_max_download_seconds_60_check
    CHECK (max_download_seconds BETWEEN 1 AND 60);

CREATE TABLE IF NOT EXISTS public.execution_code_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id text NOT NULL,
    sandbox_id text,
    status text NOT NULL DEFAULT 'closed' CHECK (status IN ('starting', 'active', 'pausing', 'paused', 'closed')),
    busy boolean NOT NULL DEFAULT false,
    busy_until timestamptz,
    pending_event_id uuid,
    last_usage_event_id uuid,
    last_activity_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, conversation_id)
);

CREATE TABLE IF NOT EXISTS public.execution_code_usage_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id uuid REFERENCES public.execution_code_sessions(id) ON DELETE SET NULL,
    conversation_id text NOT NULL,
    event_type text NOT NULL,
    status text NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved', 'completed', 'failed')),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    active_seconds integer NOT NULL DEFAULT 0 CHECK (active_seconds >= 0),
    reserved_seconds integer NOT NULL DEFAULT 0 CHECK (reserved_seconds >= 0),
    unit_cost_usd numeric(14,10) NOT NULL DEFAULT 0 CHECK (unit_cost_usd >= 0),
    actual_cost_usd numeric(14,8) NOT NULL DEFAULT 0 CHECK (actual_cost_usd >= 0),
    reserved_cost_usd numeric(14,8) NOT NULL DEFAULT 0 CHECK (reserved_cost_usd >= 0),
    reserved_idle_seconds integer NOT NULL DEFAULT 0 CHECK (reserved_idle_seconds >= 0),
    reservation_expires_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_execution_code_sessions_status_activity
    ON public.execution_code_sessions(status, last_activity_at);
CREATE INDEX IF NOT EXISTS idx_execution_code_sessions_user
    ON public.execution_code_sessions(user_id, conversation_id);
CREATE INDEX IF NOT EXISTS idx_execution_code_usage_user_started
    ON public.execution_code_usage_events(user_id, started_at);
CREATE INDEX IF NOT EXISTS idx_execution_code_usage_started
    ON public.execution_code_usage_events(started_at);
CREATE INDEX IF NOT EXISTS idx_execution_code_usage_reservations
    ON public.execution_code_usage_events(status, reservation_expires_at) WHERE reserved_cost_usd > 0;
CREATE INDEX IF NOT EXISTS idx_execution_code_usage_expiry
    ON public.execution_code_usage_events(reservation_expires_at) WHERE reserved_seconds > 0;

ALTER TABLE public.execution_code_configuration ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.execution_code_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.execution_code_usage_events ENABLE ROW LEVEL SECURITY;
GRANT ALL ON TABLE public.execution_code_configuration TO service_role;
GRANT ALL ON TABLE public.execution_code_sessions TO service_role;
GRANT ALL ON TABLE public.execution_code_usage_events TO service_role;

CREATE OR REPLACE FUNCTION public.execution_code_reserver(p_user_id uuid, p_conversation_id text, p_action text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    c public.execution_code_configuration%ROWTYPE;
    s public.execution_code_sessions%ROWTYPE;
    prev public.execution_code_usage_events%ROWTYPE;
    n timestamptz := now();
    idle integer := 0;
    op_reserve integer;
    reserve_secs integer;
    quota_reserve integer;
    reserve_cost numeric(14,8);
    day_used bigint := 0;
    month_used bigint := 0;
    month_cost numeric(14,8) := 0;
    is_new boolean := false;
    event_id uuid;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('classinus-execution-code')::bigint);

    -- Libérer les réservations dont le processus appelant n'a pas pu finaliser.
    UPDATE public.execution_code_usage_events
    SET active_seconds = active_seconds + GREATEST(
            0,
            LEAST(
                reserved_seconds - reserved_idle_seconds,
                FLOOR(EXTRACT(EPOCH FROM (n - started_at)))::integer
            )
        ),
        actual_cost_usd = actual_cost_usd + reserved_cost_usd,
        reserved_seconds = 0, reserved_cost_usd = 0, reserved_idle_seconds = 0,
        reservation_expires_at = NULL,
        status = CASE WHEN status = 'reserved' THEN 'failed' ELSE status END,
        finished_at = COALESCE(finished_at, n)
    WHERE reserved_seconds > 0 AND reservation_expires_at <= n;

    SELECT * INTO c FROM public.execution_code_configuration WHERE id = true;
    IF NOT FOUND OR p_user_id IS NULL OR p_conversation_id IS NULL OR length(trim(p_conversation_id)) = 0 THEN
        RETURN jsonb_build_object('allowed', false, 'reason', 'config_unavailable');
    END IF;
    IF p_action NOT IN ('run_code', 'run_command', 'write_file', 'read_file', 'list_files', 'download_files', 'close') THEN
        RETURN jsonb_build_object('allowed', false, 'reason', 'invalid_action');
    END IF;

    INSERT INTO public.execution_code_sessions(user_id, conversation_id, status)
    VALUES (p_user_id, p_conversation_id, 'closed')
    ON CONFLICT(user_id, conversation_id) DO NOTHING;
    SELECT * INTO s FROM public.execution_code_sessions
    WHERE user_id = p_user_id AND conversation_id = p_conversation_id FOR UPDATE;

    IF s.busy AND s.busy_until IS NOT NULL AND s.busy_until <= n THEN
        event_id := s.pending_event_id;
        UPDATE public.execution_code_usage_events
        SET status = 'failed',
            finished_at = n,
            active_seconds = active_seconds + LEAST(
                GREATEST(0, reserved_seconds - reserved_idle_seconds),
                GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (n - started_at)))::integer)
            ),
            actual_cost_usd = actual_cost_usd + CASE
                WHEN s.sandbox_id IS NOT NULL
                THEN GREATEST(0, reserved_cost_usd - (reserved_idle_seconds * unit_cost_usd))
                ELSE 0
            END,
            reserved_seconds = CASE WHEN s.sandbox_id IS NOT NULL THEN reserved_idle_seconds ELSE 0 END,
            reserved_cost_usd = CASE WHEN s.sandbox_id IS NOT NULL THEN reserved_idle_seconds * unit_cost_usd ELSE 0 END,
            reserved_idle_seconds = CASE WHEN s.sandbox_id IS NOT NULL THEN reserved_idle_seconds ELSE 0 END,
            reservation_expires_at = CASE
                WHEN s.sandbox_id IS NOT NULL AND reserved_idle_seconds > 0
                THEN n + make_interval(secs => reserved_idle_seconds)
                ELSE NULL
            END
        WHERE id = s.pending_event_id AND status = 'reserved';
        UPDATE public.execution_code_sessions
        SET busy = CASE WHEN status = 'pausing' THEN true ELSE false END,
            busy_until = CASE WHEN status = 'pausing' THEN n + interval '2 minutes' ELSE NULL END,
            pending_event_id = NULL,
            last_usage_event_id = CASE WHEN sandbox_id IS NOT NULL THEN event_id ELSE last_usage_event_id END,
            last_activity_at = CASE
                WHEN sandbox_id IS NOT NULL AND status <> 'pausing' THEN n
                ELSE last_activity_at
            END,
            status = CASE
                WHEN status = 'pausing' THEN 'pausing'
                WHEN sandbox_id IS NULL THEN 'closed'
                ELSE 'active'
            END,
            updated_at = n
        WHERE id = s.id;
        SELECT * INTO s FROM public.execution_code_sessions WHERE id = s.id FOR UPDATE;
    END IF;
    IF s.busy THEN
        RETURN jsonb_build_object('allowed', false, 'reason', 'busy');
    END IF;

    -- Solder la consommation inactive depuis la dernière action.
    IF s.last_usage_event_id IS NOT NULL AND s.last_activity_at IS NOT NULL THEN
        SELECT * INTO prev FROM public.execution_code_usage_events WHERE id = s.last_usage_event_id FOR UPDATE;
        IF FOUND AND prev.reserved_idle_seconds > 0 THEN
            idle := LEAST(prev.reserved_idle_seconds, GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (n - s.last_activity_at)))::integer));
            UPDATE public.execution_code_usage_events
            SET reserved_seconds = 0, reserved_cost_usd = 0, reserved_idle_seconds = 0,
                reservation_expires_at = NULL, status = 'completed', finished_at = COALESCE(finished_at, n)
            WHERE id = prev.id;
            IF idle > 0 THEN
                INSERT INTO public.execution_code_usage_events(
                    user_id, session_id, conversation_id, event_type, status, started_at, finished_at,
                    active_seconds, reserved_seconds, unit_cost_usd, actual_cost_usd
                ) VALUES (p_user_id, s.id, p_conversation_id, 'idle', 'completed', s.last_activity_at, n,
                    0, 0, prev.unit_cost_usd, idle * prev.unit_cost_usd);
            END IF;
        END IF;
    END IF;

    IF p_action = 'close' THEN
        UPDATE public.execution_code_sessions
        SET status = CASE WHEN sandbox_id IS NULL THEN 'closed' ELSE 'pausing' END,
            busy = sandbox_id IS NOT NULL,
            busy_until = CASE WHEN sandbox_id IS NULL THEN NULL ELSE n + interval '2 minutes' END,
            updated_at = n
        WHERE id = s.id;
        RETURN jsonb_build_object('allowed', true, 'reason', NULL, 'action', 'close',
            'session_id', s.id, 'event_id', NULL, 'sandbox_id', s.sandbox_id,
            'needs_new_sandbox', false, 'configuration', to_jsonb(c));
    END IF;

    is_new := s.sandbox_id IS NULL OR s.status = 'closed';
    IF p_action IN ('run_code', 'run_command') THEN
        op_reserve := LEAST(c.max_command_seconds, 60);
    ELSIF p_action = 'download_files' THEN
        op_reserve := c.max_download_seconds;
    ELSE
        op_reserve := c.file_operation_reserve_seconds;
    END IF;
    -- Réserver aussi la marge de transport MCP, plafonnée à 180 s côté appelant.
    reserve_secs := op_reserve + c.inactivity_seconds + 120;
    IF is_new THEN reserve_secs := reserve_secs + c.startup_reserve_seconds; END IF;
    quota_reserve := GREATEST(0, reserve_secs - c.inactivity_seconds);
    reserve_cost := reserve_secs * c.estimated_cost_per_second_usd;

    SELECT COALESCE(SUM(active_seconds + GREATEST(0, reserved_seconds - reserved_idle_seconds)), 0)::bigint INTO day_used
    FROM public.execution_code_usage_events
    WHERE user_id = p_user_id AND started_at >= date_trunc('day', n);
    SELECT COALESCE(SUM(active_seconds + GREATEST(0, reserved_seconds - reserved_idle_seconds)), 0)::bigint INTO month_used
    FROM public.execution_code_usage_events
    WHERE user_id = p_user_id AND started_at >= date_trunc('month', n);
    IF day_used + quota_reserve > c.minutes_per_day * 60 THEN
        RETURN jsonb_build_object('allowed', false, 'reason', 'daily_limit',
            'used_seconds', day_used, 'limit_seconds', c.minutes_per_day * 60);
    END IF;
    IF month_used + quota_reserve > c.minutes_per_month * 60 THEN
        RETURN jsonb_build_object('allowed', false, 'reason', 'monthly_limit',
            'used_seconds', month_used, 'limit_seconds', c.minutes_per_month * 60);
    END IF;

    SELECT COALESCE(SUM(actual_cost_usd), 0) + COALESCE(SUM(reserved_cost_usd), 0)
    INTO month_cost
    FROM public.execution_code_usage_events
    WHERE started_at >= date_trunc('month', n);
    IF month_cost + reserve_cost > c.monthly_budget_usd THEN
        RETURN jsonb_build_object('allowed', false, 'reason', 'budget_limit',
            'spent_usd', month_cost, 'limit_usd', c.monthly_budget_usd);
    END IF;

    INSERT INTO public.execution_code_usage_events(
        user_id, session_id, conversation_id, event_type, status, started_at,
        active_seconds, reserved_seconds, unit_cost_usd, actual_cost_usd, reserved_cost_usd,
        reserved_idle_seconds, reservation_expires_at
    ) VALUES (p_user_id, s.id, p_conversation_id, p_action, 'reserved', n, 0, reserve_secs,
        c.estimated_cost_per_second_usd, 0, reserve_cost, c.inactivity_seconds,
        n + make_interval(secs => op_reserve + c.startup_reserve_seconds + c.inactivity_seconds + 120))
    RETURNING id INTO event_id;

    UPDATE public.execution_code_sessions
    SET status = CASE WHEN is_new THEN 'starting' ELSE 'active' END,
        busy = true,
        busy_until = n + make_interval(secs => op_reserve + c.startup_reserve_seconds + 120),
        pending_event_id = event_id, updated_at = n
    WHERE id = s.id;

    RETURN jsonb_build_object('allowed', true, 'reason', NULL, 'session_id', s.id, 'event_id', event_id,
        'sandbox_id', s.sandbox_id, 'needs_new_sandbox', is_new, 'configuration', to_jsonb(c));
END;
$$;

CREATE OR REPLACE FUNCTION public.execution_code_attacher_sandbox(
    p_user_id uuid, p_conversation_id text, p_event_id uuid, p_sandbox_id text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE affected integer;
BEGIN
    UPDATE public.execution_code_sessions
    SET sandbox_id = p_sandbox_id, status = 'starting', updated_at = now()
    WHERE user_id = p_user_id AND conversation_id = p_conversation_id
      AND pending_event_id = p_event_id AND busy = true;
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN jsonb_build_object('success', affected = 1);
END;
$$;

CREATE OR REPLACE FUNCTION public.execution_code_finaliser(
    p_user_id uuid, p_conversation_id text, p_event_id uuid, p_sandbox_id text,
    p_active_seconds integer, p_conserver_sandbox boolean
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    c public.execution_code_configuration%ROWTYPE;
    s public.execution_code_sessions%ROWTYPE;
    e public.execution_code_usage_events%ROWTYPE;
    actual integer := 0;
    cap_seconds integer;
    keep boolean := COALESCE(p_conserver_sandbox, false) AND p_sandbox_id IS NOT NULL;
    idle integer := 0;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('classinus-execution-code')::bigint);
    SELECT * INTO c FROM public.execution_code_configuration WHERE id = true;
    SELECT * INTO s FROM public.execution_code_sessions
    WHERE user_id = p_user_id AND conversation_id = p_conversation_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('success', false, 'reason', 'session_missing'); END IF;

    IF p_event_id IS NULL THEN
        IF keep AND s.status = 'pausing' THEN
            UPDATE public.execution_code_sessions SET status = 'pausing', sandbox_id = p_sandbox_id,
                busy = true, busy_until = now() + interval '2 minutes', pending_event_id = NULL, updated_at = now()
            WHERE id = s.id;
        ELSE
            UPDATE public.execution_code_sessions SET
                status = CASE WHEN keep THEN 'active' ELSE 'closed' END,
                sandbox_id = CASE WHEN keep THEN p_sandbox_id ELSE NULL END,
                busy = false, busy_until = NULL, pending_event_id = NULL,
                last_activity_at = now(), updated_at = now()
            WHERE id = s.id;
        END IF;
        RETURN jsonb_build_object('success', true, 'closed', NOT keep);
    END IF;

    SELECT * INTO e FROM public.execution_code_usage_events
    WHERE id = p_event_id AND user_id = p_user_id FOR UPDATE;
    IF NOT FOUND OR s.pending_event_id IS DISTINCT FROM p_event_id THEN
        RETURN jsonb_build_object('success', false, 'reason', 'reservation_mismatch');
    END IF;
    -- La réservation contient la vraie marge pour cette session (y compris le démarrage si nouveau),
    -- sans compter le créneau de 5 minutes réservé séparément pour l'inactivité.
    cap_seconds := GREATEST(0, e.reserved_seconds - e.reserved_idle_seconds);
    actual := LEAST(GREATEST(COALESCE(p_active_seconds, 0), 0), cap_seconds);
    IF keep THEN idle := c.inactivity_seconds; END IF;

    UPDATE public.execution_code_usage_events SET
        status = 'completed', finished_at = now(),
        active_seconds = active_seconds + actual,
        actual_cost_usd = actual_cost_usd + (actual * unit_cost_usd),
        reserved_seconds = idle,
        reserved_cost_usd = idle * unit_cost_usd,
        reserved_idle_seconds = idle,
        reservation_expires_at = CASE WHEN idle > 0 THEN now() + make_interval(secs => idle) ELSE NULL END
    WHERE id = p_event_id;
    UPDATE public.execution_code_sessions SET
        status = CASE WHEN keep THEN 'active' ELSE 'closed' END,
        sandbox_id = CASE WHEN keep THEN p_sandbox_id ELSE NULL END,
        busy = false, busy_until = NULL, pending_event_id = NULL,
        last_usage_event_id = p_event_id, last_activity_at = now(), updated_at = now()
    WHERE id = s.id;
    RETURN jsonb_build_object('success', true, 'active_seconds', actual, 'kept', keep);
END;
$$;

CREATE OR REPLACE FUNCTION public.execution_code_lister_inactifs(p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE c public.execution_code_configuration%ROWTYPE; items jsonb; n timestamptz := now();
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('classinus-execution-code')::bigint);
        -- Libérer les réservations dont le processus appelant n'a pas pu finaliser.
    UPDATE public.execution_code_usage_events
    SET active_seconds = active_seconds + GREATEST(
            0,
            LEAST(
                GREATEST(0, reserved_seconds - reserved_idle_seconds),
                GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (n - started_at)))::integer)
            )
        ),
        actual_cost_usd = actual_cost_usd + reserved_cost_usd,
        reserved_seconds = 0, reserved_cost_usd = 0, reserved_idle_seconds = 0,
        reservation_expires_at = NULL,
        status = CASE WHEN status = 'reserved' THEN 'failed' ELSE status END,
        finished_at = COALESCE(finished_at, n)
    WHERE reserved_seconds > 0 AND reservation_expires_at <= n;

    SELECT * INTO c FROM public.execution_code_configuration WHERE id = true;
    IF NOT FOUND THEN RETURN jsonb_build_object('items', '[]'::jsonb); END IF;
    SELECT COALESCE(jsonb_agg(jsonb_build_object('session_id', id, 'sandbox_id', sandbox_id, 'status', status)), '[]'::jsonb)
    INTO items FROM (
        SELECT id, sandbox_id, status FROM public.execution_code_sessions
        WHERE status IN ('active', 'starting', 'pausing') AND sandbox_id IS NOT NULL
          AND (status = 'pausing' OR COALESCE(last_activity_at, created_at) <= n - make_interval(secs => c.inactivity_seconds))
          AND (NOT busy OR busy_until IS NULL OR busy_until <= n)
        ORDER BY COALESCE(last_activity_at, created_at)
        LIMIT GREATEST(1, LEAST(COALESCE(p_limit, 20), 100))
    ) inactifs;
    RETURN jsonb_build_object('items', items);
END;
$$;

CREATE OR REPLACE FUNCTION public.execution_code_reclamer_pause(p_session_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    c public.execution_code_configuration%ROWTYPE;
    s public.execution_code_sessions%ROWTYPE;
    e public.execution_code_usage_events%ROWTYPE;
    n timestamptz := now();
    idle integer := 0;
    forced_active integer := 0;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('classinus-execution-code')::bigint);
    SELECT * INTO c FROM public.execution_code_configuration WHERE id = true;
    SELECT * INTO s FROM public.execution_code_sessions WHERE id = p_session_id FOR UPDATE;
    IF NOT FOUND OR s.sandbox_id IS NULL OR s.status NOT IN ('active', 'starting', 'pausing') THEN
        RETURN jsonb_build_object('should_pause', false);
    END IF;
    IF s.busy AND (s.busy_until IS NULL OR s.busy_until > n) THEN
        RETURN jsonb_build_object('should_pause', false);
    END IF;
    IF s.status <> 'pausing' AND COALESCE(s.last_activity_at, s.created_at) > n - make_interval(secs => c.inactivity_seconds) THEN
        RETURN jsonb_build_object('should_pause', false);
    END IF;

    IF s.busy AND s.pending_event_id IS NOT NULL THEN
        SELECT * INTO e FROM public.execution_code_usage_events WHERE id = s.pending_event_id FOR UPDATE;
        IF FOUND AND e.status = 'reserved' THEN
            forced_active := GREATEST(0, e.reserved_seconds - e.reserved_idle_seconds);
            idle := LEAST(e.reserved_idle_seconds,
                GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (n - COALESCE(s.busy_until, n))))::integer));
            UPDATE public.execution_code_usage_events SET
                status = 'completed', finished_at = n,
                active_seconds = active_seconds + forced_active,
                actual_cost_usd = actual_cost_usd + ((forced_active + idle) * unit_cost_usd),
                reserved_seconds = 0, reserved_cost_usd = 0, reserved_idle_seconds = 0,
                reservation_expires_at = NULL
            WHERE id = e.id;
            s.last_usage_event_id := e.id;
        END IF;
    END IF;

    IF s.last_usage_event_id IS NOT NULL AND s.last_activity_at IS NOT NULL THEN
        SELECT * INTO e FROM public.execution_code_usage_events WHERE id = s.last_usage_event_id FOR UPDATE;
        IF FOUND AND e.reserved_idle_seconds > 0 THEN
            idle := LEAST(e.reserved_idle_seconds,
                GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (n - s.last_activity_at)))::integer));
            UPDATE public.execution_code_usage_events SET
                reserved_seconds = 0, reserved_cost_usd = 0, reserved_idle_seconds = 0,
                reservation_expires_at = NULL, status = 'completed', finished_at = COALESCE(finished_at, n)
            WHERE id = e.id;
            IF idle > 0 THEN
                INSERT INTO public.execution_code_usage_events(
                    user_id, session_id, conversation_id, event_type, status, started_at, finished_at,
                    active_seconds, reserved_seconds, unit_cost_usd, actual_cost_usd
                ) VALUES (s.user_id, s.id, s.conversation_id, 'idle', 'completed',
                    s.last_activity_at, n, 0, 0, e.unit_cost_usd, idle * e.unit_cost_usd);
            END IF;
        END IF;
    END IF;
    UPDATE public.execution_code_sessions SET
        status = 'pausing', busy = true, busy_until = n + interval '2 minutes',
        pending_event_id = NULL, last_usage_event_id = s.last_usage_event_id, updated_at = n
    WHERE id = s.id;
    RETURN jsonb_build_object('should_pause', true, 'session_id', s.id, 'sandbox_id', s.sandbox_id, 'status', s.status);
END;
$$;

CREATE OR REPLACE FUNCTION public.execution_code_confirmer_pause(
    p_session_id uuid, p_paused boolean, p_killed boolean
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE c public.execution_code_configuration%ROWTYPE; s public.execution_code_sessions%ROWTYPE; event_id uuid;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('classinus-execution-code')::bigint);
    SELECT * INTO c FROM public.execution_code_configuration WHERE id = true;
    SELECT * INTO s FROM public.execution_code_sessions WHERE id = p_session_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('success', false); END IF;

    IF COALESCE(p_paused, false) THEN
        UPDATE public.execution_code_sessions SET status = 'paused', busy = false,
            busy_until = NULL, pending_event_id = NULL, last_activity_at = now(), updated_at = now()
        WHERE id = s.id;
    ELSIF COALESCE(p_killed, false) THEN
        UPDATE public.execution_code_sessions SET status = 'closed', sandbox_id = NULL,
            busy = false, busy_until = NULL, pending_event_id = NULL, last_activity_at = now(), updated_at = now()
        WHERE id = s.id;
    ELSE
        IF s.status = 'pausing' THEN
            UPDATE public.execution_code_sessions SET status = 'pausing', busy = true,
                busy_until = now() + interval '1 minute', pending_event_id = NULL, updated_at = now()
            WHERE id = s.id;
        ELSE
            INSERT INTO public.execution_code_usage_events(
                user_id, session_id, conversation_id, event_type, status, started_at, active_seconds,
                reserved_seconds, unit_cost_usd, actual_cost_usd, reserved_cost_usd,
                reserved_idle_seconds, reservation_expires_at
            ) VALUES (s.user_id, s.id, s.conversation_id, 'idle_hold', 'completed', now(), 0,
                c.inactivity_seconds, c.estimated_cost_per_second_usd, 0,
                c.inactivity_seconds * c.estimated_cost_per_second_usd, c.inactivity_seconds,
                now() + make_interval(secs => c.inactivity_seconds))
            RETURNING id INTO event_id;
            UPDATE public.execution_code_sessions SET status = 'active', busy = false,
                busy_until = NULL, pending_event_id = NULL, last_usage_event_id = event_id,
                last_activity_at = now(), updated_at = now()
            WHERE id = s.id;
        END IF;
    END IF;
    RETURN jsonb_build_object('success', true);
END;
$$;

REVOKE ALL ON FUNCTION public.execution_code_reserver(uuid, text, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.execution_code_attacher_sandbox(uuid, text, uuid, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.execution_code_finaliser(uuid, text, uuid, text, integer, boolean) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.execution_code_lister_inactifs(integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.execution_code_reclamer_pause(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.execution_code_confirmer_pause(uuid, boolean, boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.execution_code_reserver(uuid, text, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.execution_code_attacher_sandbox(uuid, text, uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.execution_code_finaliser(uuid, text, uuid, text, integer, boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.execution_code_lister_inactifs(integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.execution_code_reclamer_pause(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.execution_code_confirmer_pause(uuid, boolean, boolean) TO service_role;

INSERT INTO public.registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
VALUES ('gerer_execution_code', 1, 'execution_code', true, now())
ON CONFLICT (nom_outil) DO UPDATE SET
    categorie = EXCLUDED.categorie,
    nom_serveur = EXCLUDED.nom_serveur,
    disponible = true,
    updated_at = now();
