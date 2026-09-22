# CVs objetivo (perfiles hipotéticos)

Estado: **implementado** (selección por favoritos, brecha base por código, vista `CVs`, herramientas MCP y CV descargable en DOCX/PDF, ver [cv-word-plan.md](cv-word-plan.md)).

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
3. **La brecha la calcula código, no el LLM.** `src/radar/cv_baseline.py` cruza los requisitos que
   Radar ya detectó en la oferta contra el perfil real, con evidencia: `cubierto` (certificado o
   experiencia), `parcial` (aptitud o autodeclaración sin respaldo) o `falta`; más años de experiencia
   y nivel de estudios extraídos de la descripción. El LLM solo redacta el ideal y propone acciones, y
   **no puede reasignar el estado** de lo que el código ya calculó: si un ítem del agente comparte
   `key` con la brecha base, prevalece el del código. Lo que el código no cubre queda marcado
   `estado: agente` (`ᵃ` en la matriz). Las habilidades blandas se listan pero no puntúan. La
   cercanía es ponderada y, con pocas señales, se muestra "datos insuficientes" en lugar de un
   porcentaje. Los años de experiencia se cuentan en total y por separado los de roles que mencionan las skills
   de la oferta: si solo llegas sumando todos, queda `parcial`. Las skills del CV se buscan con los mismos alias que la
   carrera activa usa para detectarlas en la oferta, y los proyectos cuentan como evidencia fuerte.
   **Cercanía y encaje no son lo mismo.** La cercanía mide si tu CV demuestra los requisitos de la oferta; el
   encaje (el puntaje del mapa) mide si la oferta calza con tus preferencias (área, ubicación, nivel). La vista
   muestra las dos y una frase que las reconcilia («encaja pero te falta evidencia», «cumples pero encaja poco»).
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

## Selección de objetivos

Los objetivos son las **ofertas con ★ (favoritos)**. No hay un mecanismo aparte: la estrella del mapa
añade el objetivo y la `✕` de la vista `CVs` la quita. Así el usuario decide qué ofertas analizar sin
depender del agente, y la brecha base aparece de inmediato para cualquiera de ellas. El agente
enriquece solo las que importan.

## Herramientas MCP

Deterministas; el LLM del agente hace la redacción.

- `list_targets()`: objetivos (favoritos) ordenados por cercanía, con su brecha base.
- `get_target_context(job_ids)`: requisitos con evidencia por oferta, brecha base y perfil real.
- `save_target_profile(job_id, profile)`: valida el esquema (orígenes, marca hipotética) y lo guarda.
- `get_target_gaps(job_ids)`: brecha por reglas contra el perfil real.
- `aggregate_targets(job_ids)`: brechas repetidas entre puestos, ordenadas por cuántos desbloquean.
- `resolve_nearest_district(reference)`: distrito más cercano a una zona mencionada en la oferta.

Almacenamiento: archivos JSON locales junto a la base de datos (`targets/<empresa>_<puesto>.json`), no
tablas SQLite. Es una decisión deliberada para el V0: no cambia el esquema, se puede editar a mano y
no toca `jobs`. Guardar de nuevo la misma oferta sobrescribe el archivo. Migrar a una tabla
`target_profiles` con versiones solo tiene sentido si se necesita historial de cambios.

## Interfaz prevista

Nueva herramienta flotante **CVs**, junto a Filtros, Radar y Análisis. Abre un panel grande
sobre el mapa (sin barras ni páginas nuevas, según los contratos de `AGENTS.md`):

1. **Matriz de brechas** (primera): filas = requisitos, columnas = puestos objetivo. Muestra qué se
   repite en todos y qué es específico de uno.
2. **Comparar**: hasta 3 CVs ideales junto al perfil real, con las secciones alineadas por fila y
   estado cubierto/parcial/falta.
3. **Render con foto**: plantilla visual del CV ideal, siempre con la marca hipotética.
4. **Plan de cierre agregado**: acciones fusionadas y ordenadas por cuántos puestos desbloquean;
   completar una registra un evento de carrera y cierra la brecha.
5. **Vínculo con el mapa**: abrir un CV resalta su oferta y muestra la distancia desde el distrito
   real.

El contenido se renderiza con el renderer Markdown local; no se usa `dangerouslySetInnerHTML`.

## Prototipo mínimo (V0)

Vista de solo lectura; el agente escribe los datos con las herramientas MCP. Los datos son archivos
locales (fuera de Git):

- `~/.local/share/radar/cv_master.json`: perfil real.
- `~/.local/share/radar/targets/*.json`: un CV objetivo por oferta (prueba inicial: EXPERTIS,
  AUNA, Core Capital).

Implementado: los pasos 1 y 2 (`src/radar/cv_targets.py`, endpoints `/api/cv/*`, `frontend/components/CvView.tsx`). La vista incluye cabecera con foto, Matriz de brechas y el CV ideal de cada puesto; `Comparar` pone tu perfil real junto a hasta 3 puestos, con las secciones alineadas por fila (sin scroll sincronizado: una sola cuadrícula). La matriz cruza solo ítems con `key` en `experience` y `tools`.

Pasos:

1. API: `GET /api/cv/profile`, `GET /api/cv/targets`, `GET /api/cv/photo`. La foto se sube desde Ajustes
   (`POST /api/me/photo`, `DELETE /api/me/photo`): se valida con Pillow, se limpia de metadatos EXIF (pueden
   llevar ubicación GPS), se redimensiona a 640 px de lado mayor y se guarda como `~/.local/share/radar/photo.jpg`;
   la API sirve solo esa ruta fija, nunca una recibida del cliente.
2. Herramienta flotante **CVs** con el panel: cabecera con foto, nombre y distrito; debajo,
   pestañas `Matriz` y `Comparar`; al elegir una columna se abre el CV objetivo.
3. Herramientas MCP (`get_target_context`, `save_target_profile`, `get_target_matrix`,
   `resolve_nearest_districts`) para que el agente escriba los archivos. Implementadas; ver `docs/mcp.md`.
   El cálculo de estado contra el perfil real sigue a cargo del agente, con `reason` obligatorio para `cubierto`.

## Perfil real

Las brechas requieren un perfil real estructurado (experiencia, formación, cursos, herramientas).
La tabla `user_profile` de SQLite solo guarda skills, objetivos y eventos. El perfil real completo
(experiencia, formación, certificados) vive en `cv_master.json`, cargado a partir del texto del usuario. La fuente puede ser un texto redactado
por el usuario o el PDF exportado desde LinkedIn (`Más > Guardar como PDF`); Radar no automatiza
sesiones ni lee perfiles de LinkedIn.

## Fases

1. Perfil real estructurado y esquema JSON del CV objetivo. **Hecho.**
2. Herramientas MCP con validación de evidencia. **Hecho** (archivos JSON, no tabla).
3. Prototipo con 3 ofertas reales. **Hecho** (generado a mano; falta probar la generación por el agente).
4. Matriz de brechas. **Hecho.**
5. Vista Comparar. **Hecho.**
6. Render con foto y marca hipotética. **Hecho.** Plan de cierre agregado entre puestos: **hecho** (pestaña `Plan`, `get_closure_plan`).
7. Vínculo con el mapa (resaltar la oferta del CV abierto): pendiente.
8. Cierre del ciclo: **hecho** (`close_gap` guarda certificado o proyecto en el CV real, anota el hito y recalcula).
9. (Posterior, mínima) Ayuda para destacar en el CV real lo que el usuario ya cerró como brecha.
   Solo reordena y resalta; no inventa.
