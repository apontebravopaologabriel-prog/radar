CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL CHECK (source_type IN ('mcp', 'library', 'api', 'manual')),
    base_url TEXT,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    website TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL,
    location TEXT,
    location_normalized TEXT,
    country TEXT NOT NULL DEFAULT 'PE',
    city TEXT,
    work_mode TEXT CHECK (work_mode IN ('onsite', 'hybrid', 'remote', 'unknown')) DEFAULT 'unknown',
    employment_type TEXT,
    seniority TEXT,
    description_raw TEXT,
    description_clean TEXT,
    salary_min NUMERIC,
    salary_max NUMERIC,
    salary_currency TEXT,
    salary_period TEXT,
    salary_source TEXT CHECK (salary_source IN ('direct_data', 'description', 'unknown')) DEFAULT 'unknown',
    published_at TIMESTAMPTZ,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    canonical_fingerprint TEXT NOT NULL,
    content_hash TEXT,
    duplicate_group_id UUID,
    duplicate_status TEXT NOT NULL DEFAULT 'canonical' CHECK (duplicate_status IN ('canonical', 'candidate', 'merged')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jobs_market_idx ON jobs (country, city, seniority, is_active);
CREATE INDEX IF NOT EXISTS jobs_published_idx ON jobs (published_at DESC);
CREATE INDEX IF NOT EXISTS jobs_fingerprint_idx ON jobs (canonical_fingerprint);

CREATE TABLE IF NOT EXISTS job_sources (
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES sources(id),
    external_id TEXT,
    source_url TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (source_id, source_url)
);
CREATE INDEX IF NOT EXISTS job_sources_external_idx ON job_sources (source_id, external_id);

CREATE TABLE IF NOT EXISTS industrial_areas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS job_areas (
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    area_id UUID NOT NULL REFERENCES industrial_areas(id),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    confidence NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence TEXT,
    PRIMARY KEY (job_id, area_id)
);

CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    normalized_name TEXT NOT NULL UNIQUE,
    category TEXT,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS job_skills (
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id),
    requirement_type TEXT NOT NULL DEFAULT 'unknown' CHECK (requirement_type IN ('required', 'preferred', 'desirable', 'unknown')),
    importance NUMERIC(4,3) CHECK (importance BETWEEN 0 AND 1),
    confidence NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence TEXT,
    PRIMARY KEY (job_id, skill_id)
);

CREATE TABLE IF NOT EXISTS job_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    requirement_type TEXT NOT NULL CHECK (requirement_type IN ('education', 'experience', 'language', 'other')),
    value TEXT NOT NULL,
    is_required BOOLEAN,
    confidence NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES sources(id),
    query TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    jobs_found INTEGER NOT NULL DEFAULT 0,
    jobs_created INTEGER NOT NULL DEFAULT 0,
    jobs_updated INTEGER NOT NULL DEFAULT 0,
    duplicates_detected INTEGER NOT NULL DEFAULT 0,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'partial', 'failed'))
);

CREATE TABLE IF NOT EXISTS user_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT,
    education TEXT,
    target_roles TEXT[] NOT NULL DEFAULT '{}',
    preferred_locations TEXT[] NOT NULL DEFAULT '{}',
    preferred_work_modes TEXT[] NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_skills (
    profile_id UUID NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id),
    level TEXT NOT NULL CHECK (level IN ('none', 'basic', 'intermediate', 'advanced')),
    evidence TEXT,
    interest TEXT CHECK (interest IN ('low', 'medium', 'high')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, skill_id)
);

CREATE TABLE IF NOT EXISTS job_scores (
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    profile_id UUID NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
    algorithm_version TEXT NOT NULL,
    total_score NUMERIC(5,2) NOT NULL CHECK (total_score BETWEEN 0 AND 100),
    area_score NUMERIC(5,2) NOT NULL,
    skills_score NUMERIC(5,2) NOT NULL,
    seniority_score NUMERIC(5,2) NOT NULL,
    education_score NUMERIC(5,2) NOT NULL,
    location_score NUMERIC(5,2) NOT NULL,
    preference_score NUMERIC(5,2) NOT NULL,
    strong_matches JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason TEXT,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, profile_id)
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date DATE NOT NULL,
    metric_name TEXT NOT NULL,
    dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
    metric_value NUMERIC NOT NULL,
    UNIQUE (snapshot_date, metric_name, dimensions)
);

CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewed', 'saved', 'ignored', 'applied', 'interview', 'offer', 'rejected', 'expired')),
    notes TEXT,
    applied_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id)
);

INSERT INTO sources (name, source_type, base_url) VALUES
    ('Computrabajo', 'mcp', 'https://www.computrabajo.com.pe'),
    ('JobSpy/Indeed', 'library', 'https://www.indeed.com')
ON CONFLICT (name) DO NOTHING;

INSERT INTO industrial_areas (name, slug) VALUES
    ('Operaciones', 'operaciones'), ('Producción', 'produccion'),
    ('Mejora continua', 'mejora-continua'), ('Procesos', 'procesos'),
    ('Supply Chain', 'supply-chain'), ('Logística', 'logistica'),
    ('Compras', 'compras'), ('Planeamiento', 'planeamiento'),
    ('Demand Planning', 'demand-planning'), ('Calidad', 'calidad'),
    ('Data / BI', 'data-bi'), ('Analytics', 'analytics'),
    ('Automatización', 'automatizacion'), ('Proyectos / PMO', 'proyectos-pmo'),
    ('Finanzas / Control de gestión', 'finanzas-control'),
    ('Seguridad y Salud en el Trabajo', 'sst'), ('Recursos Humanos / People Analytics', 'rrhh-people-analytics'),
    ('Otras', 'otras')
ON CONFLICT (name) DO NOTHING;

INSERT INTO skills (name, normalized_name, category) VALUES
    ('Excel', 'excel', 'herramienta'), ('Power BI', 'power-bi', 'bi'),
    ('SQL', 'sql', 'datos'), ('Python', 'python', 'datos'), ('PostgreSQL', 'postgresql', 'datos'),
    ('SAP', 'sap', 'erp'), ('Lean', 'lean', 'mejora'), ('Six Sigma', 'six-sigma', 'calidad'),
    ('Kaizen', 'kaizen', 'mejora'), ('VSM', 'vsm', 'mejora'), ('5S', '5s', 'mejora'),
    ('BPMN', 'bpmn', 'procesos'), ('RPA', 'rpa', 'automatizacion'), ('Power Automate', 'power-automate', 'automatizacion'),
    ('Tableau', 'tableau', 'bi'), ('Forecasting', 'forecasting', 'planeamiento'),
    ('Optimization', 'optimization', 'analitica'), ('OR-Tools', 'or-tools', 'analitica'),
    ('Supply Chain', 'supply-chain', 'supply-chain'), ('Inventory Management', 'inventory-management', 'supply-chain'),
    ('S&OP', 's-op', 'planeamiento'), ('Demand Planning', 'demand-planning', 'planeamiento'),
    ('Project Management', 'project-management', 'proyectos'), ('Scrum', 'scrum', 'proyectos'),
    ('English', 'english', 'idioma')
ON CONFLICT (name) DO NOTHING;

