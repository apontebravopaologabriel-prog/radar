CREATE TABLE IF NOT EXISTS job_user_favorites (
    job_id UUID PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS job_user_favorites_created_idx
    ON job_user_favorites (created_at DESC);
