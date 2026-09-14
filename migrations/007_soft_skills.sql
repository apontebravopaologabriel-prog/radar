-- Expand the market competency catalog with explicit human skills.
-- The classifier only attaches these when it finds contextual language.
INSERT INTO skills (name, normalized_name, category, skill_type) VALUES
    ('Negociación', 'negociacion', 'habilidad', 'soft'),
    ('Proactividad', 'proactividad', 'habilidad', 'soft'),
    ('Atención al detalle', 'atencion-al-detalle', 'habilidad', 'soft'),
    ('Orientación al cliente', 'orientacion-al-cliente', 'habilidad', 'soft'),
    ('Toma de decisiones', 'toma-de-decisiones', 'habilidad', 'soft'),
    ('Colaboración', 'colaboracion', 'habilidad', 'soft')
ON CONFLICT (name) DO UPDATE SET skill_type = EXCLUDED.skill_type;

UPDATE skills SET skill_type = 'language' WHERE name = 'English';
UPDATE skills SET skill_type = 'methodology'
WHERE name IN ('Lean', 'Six Sigma', 'Kaizen', 'VSM', '5S', 'BPMN', 'Scrum', 'Project Management');
UPDATE skills SET skill_type = 'domain'
WHERE name IN ('Supply Chain', 'Inventory Management', 'Demand Planning', 'Forecasting', 'Optimization');
