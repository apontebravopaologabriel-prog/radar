# Dirección de producto de Radar

## Propósito

Radar es un sistema personal de **Career Intelligence**. Convierte ofertas
laborales reales en señales de mercado, competencias requeridas, brechas
personales y proyectos de desarrollo profesional.

```text
Mercado → demanda → competencia → evidencia → proyecto → progreso
```

Radar no es el dashboard global de MCPs ni reemplaza T, IAI, Obsidian o Plane.
Su especialidad es ayudar a responder qué pide el mercado y qué conviene
aprender, practicar o demostrar.

## Límites de responsabilidad

| Sistema | Fuente de verdad |
| --- | --- |
| Radar | Ofertas, empresas, fuentes, demanda y perfil laboral |
| T Knowledge | Documentos y conocimiento recuperable |
| IAI | Memoria episódica de conversaciones y decisiones |
| Obsidian | Fuentes y pensamiento original |
| Plane | Proyectos, work items y entregables |
| Antigravity | Interfaz principal para trabajar con IA |

Radar puede consultar T y Plane en el futuro, preferiblemente mediante
proyecciones de solo lectura. No debe duplicar sus almacenes.

## Diferencia entre skill, competencia y capacidad de IA

- **Skill de mercado:** término detectado en una oferta, como SQL o Excel.
- **Competencia humana:** lo que la persona debe comprender, decidir, ejecutar y
  verificar.
- **Asistencia de IA:** tareas que el agente puede acelerar, proponer o
  automatizar bajo supervisión.
- **Evidencia:** proyecto, archivo, presentación, resultado o feedback que
  demuestra la competencia.

La relación principal es:

```text
job_skill → competencia humana → evidencia → proyecto
                         ↘ asistencia de IA
```

El progreso no se calcula por cantidad de cursos, MCPs o prompts. Se calcula
por práctica, proyectos y evidencia verificable.

## Producto previsto

### Mercado

Resumen de ofertas nuevas, roles, empresas, salarios, modalidades, fuentes y
variación temporal.

### Distritos

Concentración de oportunidades por distrito y área profesional.

### Radar

Centro geográfico fijo por distrito, radios de búsqueda y ofertas cercanas.
Las coordenadas aproximadas deben mostrar su nivel de precisión.

### Competencias

Cruce entre demanda, nivel declarado, brecha, evidencia y siguiente acción.
Esta vista evolucionaba la antigua vista `Skills`, ya retirada; hoy la demanda de skills se
consulta desde `Análisis` y la brecha contra el perfil desde `CVs`.

### CVs objetivo

Candidato ideal hipotético por oferta, comparable hasta 3 a la vez contra el perfil real,
con matriz de brechas y plan de cierre. No es un CV enviable. Ver
[CVs objetivo](target-profiles.md).

### Favoritos y postulaciones

Seguimiento de ofertas guardadas, ocultas, postuladas, entrevistadas,
descartadas o cerradas.

### Historial

Comparación semanal y mensual de roles, skills, empresas, salarios y áreas.

## Modelo de desarrollo

La oferta laboral no debe convertirse automáticamente en un nivel personal.
El motor debe conservar la evidencia de la fuente y utilizar reglas trazables.
El LLM puede ayudar a clasificar o resumir, pero no debe decidir sin explicación
el score, el nivel de una competencia o si una oferta está vigente.

## Carreras

El primer foco es Ingeniería Industrial y áreas adyacentes: operaciones,
procesos, supply chain, logística, producción, calidad, planeamiento, Data/BI,
automatización y mejora continua.

El modelo debe permitir añadir otros `career_tracks` más adelante, pero la UI no
debe intentar cubrir todas las carreras desde el inicio.

## Roadmap

1. Consolidar frescura, fuentes, deduplicación, paginación y calidad de datos.
2. Crear snapshots y tendencias del mercado.
3. Convertir skills de ofertas en competencias humanas.
4. Registrar evidencias y vincularlas con proyectos.
5. Comparar demanda, perfil y brechas.
6. Integrar T y Plane mediante consultas de solo lectura.
7. CVs objetivo hipotéticos y comparación de brechas entre puestos (`target-profiles.md`).
8. Añadir nuevos career tracks cuando el modelo inicial esté validado.

## No objetivos

- Postular automáticamente.
- Enviar mensajes a empresas.
- Automatizar cuentas personales de LinkedIn ni leer perfiles de LinkedIn.
- Exportar o enviar un CV hipotético como si fuera real; los CVs objetivo llevan marca fija y no se exportan.
- Reemplazar Plane, Obsidian, T o IAI.
- Inventar niveles de competencia sin evidencia.
- Crear un grafo visual sin una acción útil detrás.
