# MCP de Radar

Radar expone un servidor MCP estándar por stdio (`radar-mcp`, FastMCP). No depende de un cliente
concreto: sirve con cualquier agente compatible con MCP. El cliente predeterminado es **Antigravity**;
también funciona con Claude Code, Hermes o cualquier otro cliente con la misma configuración.

## Configuración

Comando del servidor, igual para todos los clientes:

```text
/home/paolo/Projects/Radar/.venv/bin/radar-mcp
```

Bloque JSON estándar (`mcpServers`), que acepta la mayoría de clientes:

```json
{
  "mcpServers": {
    "radar": {
      "command": "/home/paolo/Projects/Radar/.venv/bin/radar-mcp",
      "cwd": "/home/paolo/Projects/Radar"
    }
  }
}
```

El proceso necesita acceso de lectura/escritura al archivo SQLite local (por defecto
`~/.local/share/radar/radar.db`, configurable con `RADAR_DB_PATH`) y, para los CVs objetivo, al mismo
directorio de datos.

### Antigravity (predeterminado)

Radar está registrado en la configuración global de Antigravity, `~/.gemini/config/mcp_config.json`,
con el bloque anterior (`disabled: false`) junto a los demás servidores. Después de cambiar esta
configuración, reinicia Antigravity o recarga sus servidores MCP desde
`Additional Options (...) > MCP Servers`.

### Otros clientes

- **Claude Code:** `claude mcp add radar -- /home/paolo/Projects/Radar/.venv/bin/radar-mcp`.
- **Hermes u otro cliente MCP:** pega el bloque JSON en su configuración de servidores.

Un cliente nuevo no requiere cambios en Radar. Tras añadir herramientas al servidor, hay que recargar
el servidor MCP del cliente para que las vea.

## Herramientas

> La lista completa y siempre al día está en la **skill de agente** generada: `radar skill export --out docs/skills`
> produce `docs/skills/radar/SKILL.md` (copiable a Antigravity o Claude Code) a partir del mismo registro que usa
> el servidor y el chat de la app. Además del listado de abajo hay: `get_today_feed`, `find_jobs_near(place, radius_km)`
> (distritos de Lima o ciudades del Perú), `get_job_details`, `explain_job_fit`, `compare_jobs`, `get_skill_demand`,
> `get_market_breakdown(by)`, `get_place_profile(place)`, `get_salary_stats`, `plan_learning`, `get_data_schema` y `run_readonly_sql` (solo SELECT/WITH,
> máx. 50 filas), `get_setup_status`, `get_help`, `update_profile`, `favorite_job`, `list_career_tracks`,
> `set_career_track` y `create_career_pack`. Las que escriben piden confirmación a la persona.
>
> El servidor también publica **recursos** (`radar://topics`, `radar://help/{topic}`, `radar://schema`) y **prompts**
> (`configurar_radar`, `analizar_mercado`, `plan_de_aprendizaje`).

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

## CVs objetivo (hipotéticos)

Detalle y principios en `docs/target-profiles.md`. Los archivos viven junto a la base de datos
(`cv_master.json`, `targets/*.json`, `photo.jpg`), fuera de Git.

- `list_targets()`: los objetivos actuales (ofertas con ★ elegidas por el usuario en la interfaz),
  ordenados por cercanía al perfil real, con su brecha base calculada por código.
- `get_target_context(job_ids)`: ofertas (requisitos, skills, descripción, distancia desde el distrito
  real), su brecha base (`baseline`, con `key` y estado) y el perfil real. Máximo 10 ofertas.
- `save_target_profile(job_id, profile)`: valida y guarda un CV objetivo hipotético. Exige `quote` o
  `reason` en ítems explícitos, `reason` en inferidos y en `cubierto`, y valida `origin`, `status` y
  `kind`. Empresa, título, marca hipotética y distancia los fija Radar; si un ítem comparte `key` con la brecha
  base, el estado del código prevalece sobre el del agente. Devuelve `errors` si no valida.
- `get_target_matrix()`: matriz de brechas entre los CVs guardados.
- `resolve_nearest_districts(reference, limit=3)`: distritos más cercanos a una zona (km aproximados).

El estado de los requisitos detectados por Radar (skills, años de experiencia, estudios) lo calcula
el código. El agente solo asigna estado a lo demás, citando el perfil real, y esos ítems se marcan
como asignados por el agente en la matriz.

## Política para el agente

Cualquier agente conectado (Antigravity, Claude Code, Hermes u otro) debe declarar fuente y filtros, distinguir `NULL` de datos confirmados, respetar scores/evidencias y pedir confirmación antes de futuras escrituras del perfil. V1 no tiene herramientas de postulación.
