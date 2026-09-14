PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL CHECK (source_type IN ('mcp', 'library', 'api', 'manual')),
    base_url TEXT,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    website TEXT,
    created_at TEXT NOT NULL DEFAULT (now()),
    updated_at TEXT NOT NULL DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    company_id TEXT REFERENCES companies(id),
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
    salary_min REAL,
    salary_max REAL,
    salary_currency TEXT,
    salary_period TEXT,
    salary_source TEXT CHECK (salary_source IN ('direct_data', 'description', 'unknown')) DEFAULT 'unknown',
    published_at TEXT,
    detected_at TEXT NOT NULL DEFAULT (now()),
    expires_at TEXT,
    canonical_fingerprint TEXT NOT NULL,
    content_hash TEXT,
    duplicate_group_id TEXT,
    duplicate_status TEXT NOT NULL DEFAULT 'canonical' CHECK (duplicate_status IN ('canonical', 'candidate', 'merged')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (now()),
    updated_at TEXT NOT NULL DEFAULT (now()),
    sector TEXT,
    sector_confidence REAL,
    hours_per_week REAL,
    schedule_text TEXT,
    application_status TEXT NOT NULL DEFAULT 'unknown' CHECK (application_status IN ('unknown', 'open', 'closed', 'expired')),
    application_checked_at TEXT,
    application_status_source TEXT NOT NULL DEFAULT 'unknown' CHECK (application_status_source IN ('unknown', 'source_page', 'source_payload', 'manual'))
);

CREATE INDEX IF NOT EXISTS jobs_market_idx ON jobs (country, city, seniority, is_active);
CREATE INDEX IF NOT EXISTS jobs_published_idx ON jobs (published_at DESC);
CREATE INDEX IF NOT EXISTS jobs_fingerprint_idx ON jobs (canonical_fingerprint);
CREATE INDEX IF NOT EXISTS jobs_sector_idx ON jobs (sector, is_active);
CREATE INDEX IF NOT EXISTS jobs_application_status_idx ON jobs (application_status, published_at DESC);

CREATE TABLE IF NOT EXISTS job_sources (
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(id),
    external_id TEXT,
    source_url TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT (now()),
    last_seen_at TEXT NOT NULL DEFAULT (now()),
    raw_payload TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (source_id, source_url)
);
CREATE INDEX IF NOT EXISTS job_sources_external_idx ON job_sources (source_id, external_id);

CREATE TABLE IF NOT EXISTS industrial_areas (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    is_enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS job_areas (
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    area_id TEXT NOT NULL REFERENCES industrial_areas(id),
    is_primary INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence TEXT,
    PRIMARY KEY (job_id, area_id)
);

CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    name TEXT NOT NULL UNIQUE,
    normalized_name TEXT NOT NULL UNIQUE,
    category TEXT,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    skill_type TEXT NOT NULL DEFAULT 'technical'
);

CREATE TABLE IF NOT EXISTS job_skills (
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    requirement_type TEXT NOT NULL DEFAULT 'unknown' CHECK (requirement_type IN ('required', 'preferred', 'desirable', 'unknown')),
    importance REAL CHECK (importance BETWEEN 0 AND 1),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence TEXT,
    PRIMARY KEY (job_id, skill_id)
);

CREATE TABLE IF NOT EXISTS user_profile (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    name TEXT,
    education TEXT,
    target_roles TEXT NOT NULL DEFAULT '[]',
    preferred_locations TEXT NOT NULL DEFAULT '[]',
    preferred_work_modes TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS user_skills (
    profile_id TEXT NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    level TEXT NOT NULL,
    evidence TEXT,
    interest TEXT,
    updated_at TEXT NOT NULL DEFAULT (now()),
    confidence REAL,
    last_verified_at TEXT,
    PRIMARY KEY (profile_id, skill_id)
);

CREATE TABLE IF NOT EXISTS job_scores (
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
    algorithm_version TEXT NOT NULL,
    total_score REAL NOT NULL,
    area_score REAL NOT NULL,
    skills_score REAL NOT NULL,
    seniority_score REAL NOT NULL,
    education_score REAL NOT NULL,
    location_score REAL NOT NULL,
    preference_score REAL NOT NULL,
    strong_matches TEXT NOT NULL DEFAULT '[]',
    missing_skills TEXT NOT NULL DEFAULT '[]',
    reason TEXT,
    computed_at TEXT NOT NULL DEFAULT (now()),
    PRIMARY KEY (job_id, profile_id)
);

CREATE TABLE IF NOT EXISTS job_observations (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    source_id TEXT REFERENCES sources(id),
    observed_at TEXT NOT NULL DEFAULT (now()),
    content_hash TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    snapshot TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS job_observations_job_time_idx ON job_observations (job_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS job_observations_time_idx ON job_observations (observed_at DESC);

CREATE TABLE IF NOT EXISTS profile_versions (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    profile_id TEXT NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    change_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (now()),
    UNIQUE (profile_id, version_number)
);

CREATE TABLE IF NOT EXISTS career_events (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    profile_id TEXT REFERENCES user_profile(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('employment', 'education', 'course', 'certification', 'project', 'interview', 'achievement', 'skill_update', 'goal_update', 'note')),
    title TEXT NOT NULL,
    description TEXT,
    started_on TEXT,
    ended_on TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (now())
);
CREATE INDEX IF NOT EXISTS career_events_time_idx ON career_events (profile_id, started_on DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    notes TEXT,
    applied_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS application_events (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    notes TEXT,
    occurred_at TEXT NOT NULL DEFAULT (now())
);
CREATE INDEX IF NOT EXISTS application_events_time_idx ON application_events (application_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS job_user_status (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'hidden' CHECK (status IN ('visible', 'hidden')),
    reason TEXT CHECK (reason IN ('closed', 'not_interested', 'applied', 'duplicate', 'other')),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (now()),
    updated_at TEXT NOT NULL DEFAULT (now()),
    CHECK (status = 'visible' OR reason IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS job_user_status_hidden_idx ON job_user_status (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS job_user_favorites (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (now())
);
CREATE INDEX IF NOT EXISTS job_user_favorites_created_idx ON job_user_favorites (created_at DESC);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    snapshot_date TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    dimensions TEXT NOT NULL DEFAULT '{}',
    metric_value REAL NOT NULL,
    UNIQUE (snapshot_date, metric_name, dimensions)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    source_id TEXT REFERENCES sources(id),
    query TEXT,
    started_at TEXT NOT NULL DEFAULT (now()),
    finished_at TEXT,
    jobs_found INTEGER NOT NULL DEFAULT 0,
    jobs_created INTEGER NOT NULL DEFAULT 0,
    jobs_updated INTEGER NOT NULL DEFAULT 0,
    duplicates_detected INTEGER NOT NULL DEFAULT 0,
    errors TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS job_requirements (
    id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()),
    job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE,
    requirement_type TEXT NOT NULL,
    value TEXT NOT NULL,
    is_required INTEGER,
    confidence REAL,
    evidence TEXT
);
