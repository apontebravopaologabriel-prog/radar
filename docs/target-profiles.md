# CVs objetivo (perfiles hipotéticos)

Estado: **V0 de solo lectura implementada** (API + vista `CVs`); herramientas MCP y comparación en columnas implementadas.

## Propósito

Para cada oferta, un agente redacta el **candidato ideal** que esa empresa parece buscar. No es el
CV del usuario ni un borrador para enviar: es una herramienta para ver el objetivo exacto de cada
puesto, medir la brecha contra el perfil real y decidir qué aprender o demostrar.

```text
oferta → candidato ideal (hipotético) → brecha contra perfil real → acciones → evidencia → cierre
```

Esto extiende la cadena de `docs/product-direction.md` (mercado → competencia → evidencia →
proyecto). Reemplaza la idea de "adaptar el CV real a cada oferta", que aporta poco porque solo
reordena lo que ya existe; esa adaptación queda como fase posterior y mínima (ver más abajo).

## Principios

1. **Hipotético nunca es oficial.** Todo CV objetivo se muestra con la marca fija
   `HIPOTÉTICO — no enviar` y no se puede exportar a PDF ni Word.
2. **Cada ítem declara su origen.**
   - `explicito`: la oferta lo dice; se guarda la cita textual.
   - `inferido`: no se dice, pero el puesto lo implica; se guarda la razón.
   - `tipico`: relleno probable del rubro; menor confianza.
3. **La brecha la calcula código, no el LLM.** El LLM redacta el ideal y propone acciones; la
   comparación oferta/perfil real se hace por reglas trazables.
4. **El plan de cierre es honesto.** Cada brecha se clasifica por lo que cuesta cerrarla:

   | Tipo | Ejemplo | Cierre |
   | --- | --- | --- |
   | `dias` | Certificación de Python, herramienta nueva | Curso corto |
   | `semanas` | Dashboard Power BI, análisis con SQL | Proyecto con evidencia |
   | `no_cerrable_rapido` | "2 años de experiencia" | Un curso no lo reemplaza: prácticas, freelance, proyectos reales o apuntar a ofertas de menor nivel |

5. **Distrito por reglas.** Si la oferta pide una zona ("cerca de Miraflores"), el MCP calcula el
   distrito más cercano con las coordenadas de distrito y Haversine que Radar ya tiene; el LLM
   solo lo escribe. Además se muestra la distancia desde el distrito real del usuario, que es lo
   relevante para postular. Las coordenadas siguen siendo aproximadas.
6. **Datos personales locales.** La foto y el perfil real quedan en la máquina, como el resto de
   Radar.

## Formato

Cada CV objetivo se guarda como **JSON estructurado** (no como Markdown libre) para poder renderizar
columnas, marcar cubierto/falta y armar la matriz de brechas. El `.md` legible para el agente se
genera desde el JSON.

```json
{
  "job_id": "...",
  "generated_at": "2026-09-19",
  "hypothetical": true,
  "location": { "district": "Surquillo", "reason": "zona cercana a Miraflores", "method": "haversine" },
  "sections": {
    "summary": [{ "text": "...", "origin": "inferido", "reason": "..." }],
    "experience": [{ "text": "2 años en mejora de procesos", "origin": "explicito", "quote": "..." }],
    "tools": [{ "text": "Python", "origin": "explicito", "quote": "...", "status": "falta" }],
    "education": [],
    "certifications": []
  },
  "gaps": [
    { "item": "Python", "kind": "dias", "action": "Curso corto + script de ejemplo", "estimate_days": 5,
      "evidence_to_produce": "Repositorio con automatización de un reporte" }
  ]
}
```

`status` (`cubierto`, `parcial`, `falta`) lo asigna el código al comparar contra el perfil real.

## Herramientas MCP previstas

Deterministas; el LLM del agente hace la redacción.

- `get_target_context(job_ids)`: requisitos con evidencia por oferta y perfil real.
- `save_target_profile(job_id, profile)`: valida el esquema (orígenes, marca hipotética) y lo guarda.
- `get_target_gaps(job_ids)`: brecha por reglas contra el perfil real.
- `aggregate_targets(job_ids)`: brechas repetidas entre puestos, ordenadas por cuántos desbloquean.
- `resolve_nearest_district(reference)`: distrito más cercano a una zona mencionada en la oferta.

Almacenamiento: tabla SQLite `target_profiles` (`job_id`, JSON, fecha, versión del perfil real
usado) siguiendo la regla de `AGENTS.md` sobre el esquema. Sin escritura sobre `jobs`.

## Interfaz prevista

Nueva herramienta flotante **CVs**, junto a Filtros, Radar y Competencias. Abre un panel grande
sobre el mapa (sin barras ni páginas nuevas, según los contratos de `AGENTS.md`):

1. **Matriz de brechas** (primera): filas = requisitos, columnas = puestos objetivo. Muestra qué se
   repite en todos y qué es específico de uno.
2. **Comparar**: de 2 a 4 CVs ideales junto al perfil real, con scroll sincronizado por sección y
   estado cubierto/parcial/falta.
3. **Render con foto**: plantilla visual del CV ideal, siempre con la marca hipotética.
4. **Plan de cierre agregado**: acciones fusionadas y ordenadas por cuántos puestos desbloquean;
   completar una registra un evento de carrera y cierra la brecha.
5. **Vínculo con el mapa**: abrir un CV resalta su oferta y muestra la distancia desde el distrito
   real.

El contenido se renderiza con el renderer Markdown local; no se usa `dangerouslySetInnerHTML`.

## Prototipo mínimo (V0)

Solo lectura, sin herramientas MCP nuevas todavía. Los datos de prueba están como archivos locales
(fuera de Git):

- `~/.local/share/radar/cv_master.json`: perfil real.
- `~/.local/share/radar/targets/*.json`: un CV objetivo por oferta (3 de prueba: EXPERTIS, AUNA,
  Core Capital).

Implementado: los pasos 1 y 2 (`src/radar/cv_targets.py`, endpoints `/api/cv/*`, `frontend/components/CvView.tsx`). La vista incluye cabecera con foto, Matriz de brechas y el CV ideal de cada puesto; `Comparar` pone tu perfil real junto a hasta 3 puestos, con las secciones alineadas por fila (sin scroll sincronizado: una sola cuadrícula). La matriz cruza solo ítems con `key` en `experience` y `tools`.

Pasos:

1. API: `GET /api/cv/profile`, `GET /api/cv/targets`, `GET /api/cv/photo`. La foto se copia una vez a
   `~/.local/share/radar/photo.jpg`; la API sirve solo esa ruta fija, nunca una ruta recibida.
2. Herramienta flotante **CVs** con el panel: cabecera con foto, nombre y distrito; debajo,
   pestañas `Matriz` y `Comparar`; al elegir una columna se abre el CV objetivo.
3. Herramientas MCP (`get_target_context`, `save_target_profile`, `get_target_matrix`,
   `resolve_nearest_districts`) para que el agente escriba los archivos. Implementadas; ver `docs/mcp.md`.
   El cálculo de estado contra el perfil real sigue a cargo del agente, con `reason` obligatorio para `cubierto`.

## Perfil real

Las brechas requieren un perfil real estructurado (experiencia, formación, cursos, herramientas).
Hoy el perfil solo guarda skills y eventos. Se puede empezar generando los CVs objetivo sin él y
añadir el cálculo de brechas cuando el perfil esté cargado. La fuente puede ser un texto redactado
por el usuario o el PDF exportado desde LinkedIn (`Más > Guardar como PDF`); Radar no automatiza
sesiones ni lee perfiles de LinkedIn.

## Fases

1. Perfil real estructurado y esquema JSON del CV objetivo.
2. Herramientas MCP y tabla `target_profiles`.
3. Prototipo con 3 ofertas reales generadas por el agente.
4. Matriz de brechas.
5. Vista Comparar.
6. Render con foto y plan de cierre agregado.
7. (Posterior, mínima) Ayuda para destacar en el CV real lo que el usuario ya cerró como brecha.
   Solo reordena y resalta; no inventa.
