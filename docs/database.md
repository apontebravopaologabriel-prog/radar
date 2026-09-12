# Modelo de datos PostgreSQL

Las migraciones están en [`migrations/001_initial.sql`](../migrations/001_initial.sql), [`migrations/002_career_history.sql`](../migrations/002_career_history.sql), [`migrations/003_job_quality.sql`](../migrations/003_job_quality.sql) y [`migrations/004_application_status.sql`](../migrations/004_application_status.sql).

| Tabla | Propósito |
|---|---|
| `sources` | Fuentes y tipo de conector |
| `companies` | Empresas normalizadas |
| `jobs` | Oferta canónica independiente de la fuente; incluye modalidad, sector, salario, horario y estado de postulación cuando hay evidencia |
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

## Duplicados

V1 detecta duplicados exactos por fingerprint y conserva las apariciones de cada fuente. No fusiona automáticamente casos ambiguos por similitud de descripción.

## Mercado y usuario

Las métricas de mercado se calculan desde `jobs`, `job_areas` y `job_skills`. Las preferencias y skills del usuario viven en `user_profile` y `user_skills`; no modifican las estadísticas de mercado. Cada actualización explícita crea una fila en `profile_versions`, para que el perfil evolucione sin borrar estados anteriores. Las postulaciones se registran en `applications` y cada transición se conserva en `application_events`. `application_status` describe si la oferta fuente acepta solicitudes; es distinto del estado personal de `applications`.

Docker ejecuta los SQL de `migrations/` solo cuando el volumen se crea por primera vez. Cambios posteriores deben ser migraciones nuevas o aplicarse explícitamente.
