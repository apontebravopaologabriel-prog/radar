-- Quality guarantees for canonical jobs and deterministic area classification.
CREATE UNIQUE INDEX IF NOT EXISTS jobs_fingerprint_unique_idx ON jobs (canonical_fingerprint);
CREATE UNIQUE INDEX IF NOT EXISTS job_areas_one_primary_idx ON job_areas (job_id) WHERE is_primary = TRUE;
INSERT INTO industrial_areas (name, slug) VALUES ('Ventas / Comercial', 'ventas-comercial')
ON CONFLICT (name) DO NOTHING;
