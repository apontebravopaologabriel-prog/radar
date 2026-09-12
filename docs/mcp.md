# MCP de Radar para Hermes

## Configuración

```json
{
  "mcpServers": {
    "radar": {
      "command": "/home/paolo/Projects/Radar/.venv/bin/radar-mcp"
    }
  }
}
```

El proceso necesita acceso a `DATABASE_URL` y al PostgreSQL local.

## Antigravity

Radar también está registrado en la configuración global de Antigravity:

`~/.gemini/config/mcp_config.json`

La entrada usa `/home/paolo/Projects/Radar/.venv/bin/radar-mcp`, define el directorio de trabajo del proyecto y mantiene habilitados los demás servidores. Después de cambiar esta configuración, reinicia Antigravity o recarga sus servidores MCP desde `Additional Options (...) > MCP Servers`.

## Herramientas

- `health()`: comprueba disponibilidad; no cambia datos.
- `ingest_jobs(source, query, location="Lima", limit=25, max_age_days=14)`: busca, clasifica, deduplica y guarda únicamente ofertas fechadas dentro del rango reciente. El límite operativo es 100. Usa `max_age_days=7` para una búsqueda de la última semana.
- `search_saved_jobs(limit=20, seniority=null, area=null, max_age_days=14)`: consulta ofertas recientes guardadas y excluye las ocultadas en la instalación local; máximo 100. Devuelve modalidad, sector, horario y estado de postulación cuando están disponibles.
- `get_market_summary()`: total activo, áreas primarias y skills frecuentes.
- `get_user_profile()`: devuelve el perfil separado; puede devolver `profile: null`.
- `list_recommended_jobs(limit=10, max_age_days=14)`: devuelve solo recomendaciones activas y fechadas dentro del rango, con enlace directo, fecha de publicación, modalidad, sector, salario y horas cuando existen; requiere perfil configurado.
- Las ofertas sin fecha o antiguas se conservan como historial, pero no se recomiendan.
- En recomendaciones de LinkedIn, `application_status=open` y una verificación reciente son requisitos de calidad. La vista web general usa la antigüedad y el estado personal de ocultamiento, sin un filtro especial por fuente.
- `get_job_history(job_id, limit=20)`: devuelve las observaciones temporales de una oferta.
- `get_career_timeline(limit=50)`: devuelve versiones del perfil y eventos profesionales.
- `record_career_event(event_type, title, description=null, started_on=null, ended_on=null)`: registra un evento profesional con confirmación explícita.
- `capture_market_history(snapshot_date=null)`: guarda métricas del mercado para comparar periodos.
- `get_market_history(limit=90)`: consulta snapshots históricos.
- `track_job_application(job_id, status="saved", notes=null)`: registra o actualiza una postulación.
- `list_job_applications(limit=50)`: lista postulaciones y enlaces.

LinkedIn, Bumeran, Laborum y Empleos Perú se incorporan inicialmente mediante archivos CSV/JSON preparados por el usuario; Radar no automatiza sesiones ni cuentas personales.

## Política de Hermes

Hermes debe declarar fuente y filtros, distinguir `NULL` de datos confirmados, respetar scores/evidencias y pedir confirmación antes de futuras escrituras del perfil. V1 no tiene herramientas de postulación.
