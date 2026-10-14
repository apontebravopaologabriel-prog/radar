-- Enrichment fields used to repair incomplete source metadata.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS sector TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS sector_confidence NUMERIC(4,3);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS hours_per_week NUMERIC(5,2);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS schedule_text TEXT;
CREATE INDEX IF NOT EXISTS jobs_sector_idx ON jobs (sector, is_active);
