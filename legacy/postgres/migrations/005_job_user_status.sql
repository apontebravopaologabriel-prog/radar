CREATE TABLE IF NOT EXISTS job_user_status (
    job_id UUID PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'hidden' CHECK (status IN ('visible', 'hidden')),
    reason TEXT CHECK (reason IN ('closed', 'not_interested', 'applied', 'duplicate', 'other')),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status = 'visible' OR reason IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS job_user_status_hidden_idx
    ON job_user_status (status, updated_at DESC);
