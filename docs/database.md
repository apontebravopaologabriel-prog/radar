# Modelo de datos

La base activa es SQLite. El esquema completo, incluido el catálogo de áreas y skills, vive en
[`src/radar/db/schema_sqlite.sql`](../src/radar/db/schema_sqlite.sql) y se aplica íntegro al crear
un archivo `.db` nuevo; `_ensure_runtime_schema()` en
[`src/radar/db/database.py`](../src/radar/db/database.py) reaplica de forma aditiva (`ON CONFLICT DO
NOTHING`) los índices y el catálogo en cada conexión, para que una base creada antes de un cambio de
esquema quede al día automáticamente.

El directorio [`migrations/`](../migrations/) conserva los `.sql` originales de la era PostgreSQL
del proyecto (sintaxis `UUID`, `JSONB`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). Ya no se
ejecutan contra SQLite ni contra ninguna base activa; quedan como referencia histórica del diseño y
para quien necesite levantar el `docker-compose.yml` heredado. Un cambio de esquema SQLite se hace
directamente en `schema_sqlite.sql` (y, si aplica a bases existentes, también en
`_ensure_runtime_schema()`), no agregando un archivo a `migrations/`.

| Tabla | Propósito |
|---|---|
| `sources` | Fuentes y tipo de conector |
| `companies` | Empresas normalizadas |
| `jobs` | Oferta canónica independiente de la fuente; incluye modalidad, sector, salario, horario, relevancia del perfil y estado de postulación cuando hay evidencia |
| `job_sources` | Aparición por fuente y `raw_payload` |
| `industrial_areas` | Catálogo de áreas |
| `job_areas` | Área primaria/secundaria, evidencia y confianza |
| `skills` | Catálogo normalizado de habilidades |
| `job_skills` | Skills, importancia, tipo y evidencia |
| `job_requirements` | Educación, experiencia, idiomas y otros requisitos |
| `ingestion_runs` | Auditoría de ejecuciones |
| `user_profile` | Perfil separado del mercado |
| `user_skills` | Nivel, evidencia e interés |
| `job_scores` | Resultado del Match Engine |
| `market_snapshots` | Base para histórico |
| `applications` | Estados de seguimiento; sin herramientas MCP en V1 |
| `job_observations` | Fotografías temporales de cada oferta por fuente |
| `profile_versions` | Versiones inmutables del perfil profesional |
| `career_events` | Empleo, estudios, proyectos, cursos, logros y metas |
| `application_events` | Historial de cambios de cada postulación |
| `job_user_status` | Estado personal visible/oculta, motivo y nota opcional por oferta |
| `job_user_favorites` | Ofertas guardadas por el usuario con fecha de guardado |

## Persistencia

1. Se busca una oferta.
2. Se crea o reutiliza la empresa mediante `normalized_name`.
3. Se calcula `canonical_fingerprint` con empresa, título y ubicación normalizados.
4. Si existe el fingerprint, se actualiza la oferta canónica.
5. Se registra URL, identificador externo y respuesta original en `job_sources`.
6. Las ofertas nuevas se clasifican y relacionan con áreas y skills.
7. Cada aparición se registra en `job_observations`; la oferta canónica se marca activa/inactiva, nunca se borra.
8. `capture_market_history` guarda el total, áreas y skills del mercado con fecha para comparar periodos.

Los campos `sector`, `sector_confidence`, `hours_per_week` y `schedule_text` se enriquecen durante la ingesta. `repair-data` los puede recalcular junto con modalidad y salario para ofertas capturadas antes de estas mejoras.

`relevance_tier`, `relevance_score` y `relevance_evidence` separan el mercado en núcleo de Ingeniería Industrial, áreas adyacentes y fuera de foco. No usan el salario como criterio de entrada y no eliminan ofertas; sirven para priorizar la vista y auditar la clasificación.

## Duplicados y calidad

Radar detecta duplicados exactos por fingerprint y conserva las apariciones de cada fuente en
`job_sources`; una misma oferta puede tener varias URLs de Indeed sin aparecer varias veces como
`jobs`. La base impone un fingerprint único y una sola área primaria por oferta. Los casos que
coinciden en empresa y título pero difieren en ubicación se reportan para revisión, no se fusionan
automáticamente porque podrían ser vacantes legítimas.

`duplicate_status` permite mantener una oferta canónica y separar candidatos o registros fusionados
sin borrar históricos. Las consultas normales muestran solo registros canónicos y activos.

`radar audit-data` genera un informe reproducible con grupos repetidos, enlaces por fuente,
integridad de áreas y posibles títulos comerciales dentro de áreas objetivo.

## Clasificación profesional

`Ventas / Comercial` es un área explícita. Las señales comerciales presentes en el título tienen
prioridad sobre palabras genéricas de la descripción (`operaciones`, `planning` o `procesos`), de
modo que un puesto como `Ejecutivo Comercial` no se presenta como una oferta de Ingeniería
Industrial. La clasificación sigue siendo determinista y conserva la evidencia textual.

## Mercado y usuario

Las métricas de mercado se calculan desde `jobs`, `job_areas` y `job_skills`. Las preferencias y skills del usuario viven en `user_profile` y `user_skills`; no modifican las estadísticas de mercado. Cada actualización explícita crea una fila en `profile_versions`, para que el perfil evolucione sin borrar estados anteriores. Las postulaciones se registran en `applications` y cada transición se conserva en `application_events`. `application_status` describe si la oferta fuente acepta solicitudes; es distinto del estado personal de `applications`.

`job_user_status` registra el estado local de cada oferta. Al ocultarla se guarda un motivo y las
consultas normales la excluyen; al restaurarla vuelve a `visible`. No modifica ni elimina `jobs`.
La tabla representa actualmente una sola instalación local y no contiene `user_id`.

`job_user_favorites` registra la estrella de cada oferta y es independiente de `job_user_status`.
Una oferta puede estar guardada y ocultada sin perderse de Favoritos.

La vista `Skills` calcula la demanda desde las ofertas filtradas por antigüedad,
área, seniority y modalidad, agrupando `job_skills`. El perfil se cruza desde
`user_skills` y la evidencia disponible; no se altera el mercado ni se inventa un
nivel cuando el usuario no lo declaró. La API expone este agregado mediante
`GET /api/skills/overview`.

Ver la sección inicial de este documento para cómo se aplica y actualiza el esquema SQLite.
