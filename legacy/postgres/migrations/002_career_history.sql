-- Radar V2: historial temporal y evolución profesional.
-- Las tablas son append-only por diseño; no se borran ofertas ni estados históricos.
CREATE TABLE IF NOT EXISTS job_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    source_id UUID REFERENCES sources(id),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS job_observations_job_time_idx ON job_observations (job_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS job_observations_time_idx ON job_observations (observed_at DESC);

CREATE TABLE IF NOT EXISTS profile_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    snapshot JSONB NOT NULL,
    change_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (profile_id, version_number)
);

CREATE TABLE IF NOT EXISTS career_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID REFERENCES user_profile(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('employment', 'education', 'course', 'certification', 'project', 'interview', 'achievement', 'skill_update', 'goal_update', 'note')),
    title TEXT NOT NULL,
    description TEXT,
    started_on DATE,
    ended_on DATE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS career_events_time_idx ON career_events (profile_id, started_on DESC NULLS LAST, created_at DESC);

CREATE TABLE IF NOT EXISTS application_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    notes TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS application_events_time_idx ON application_events (application_id, occurred_at DESC);

ALTER TABLE skills ADD COLUMN IF NOT EXISTS skill_type TEXT NOT NULL DEFAULT 'technical';
ALTER TABLE user_skills ADD COLUMN IF NOT EXISTS confidence NUMERIC(4,3) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1);
ALTER TABLE user_skills ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ;

INSERT INTO skills (name, normalized_name, category, skill_type) VALUES
    ('Comunicación', 'comunicacion', 'habilidad', 'soft'),
    ('Trabajo en equipo', 'trabajo-en-equipo', 'habilidad', 'soft'),
    ('Pensamiento analítico', 'pensamiento-analitico', 'habilidad', 'soft'),
    ('Resolución de problemas', 'resolucion-de-problemas', 'habilidad', 'soft'),
    ('Liderazgo', 'liderazgo', 'habilidad', 'soft'),
    ('Adaptabilidad', 'adaptabilidad', 'habilidad', 'soft')
ON CONFLICT (name) DO UPDATE SET skill_type = EXCLUDED.skill_type;
