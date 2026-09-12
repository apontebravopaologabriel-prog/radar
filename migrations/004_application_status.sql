-- Estado de aceptación verificado por fuente, especialmente importante en LinkedIn.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS application_status TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS application_checked_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS application_status_source TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_application_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_application_status_check CHECK (application_status IN ('unknown', 'open', 'closed', 'expired'));
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_application_status_source_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_application_status_source_check CHECK (application_status_source IN ('unknown', 'source_page', 'source_payload', 'manual'));
CREATE INDEX IF NOT EXISTS jobs_application_status_idx ON jobs (application_status, published_at DESC);
