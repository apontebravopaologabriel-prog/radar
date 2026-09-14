# Auditoría de competencias del mercado

## Alcance

La auditoría revisa las competencias persistidas en `skills` y su evidencia en `job_skills`. La demanda se cuenta por ofertas distintas y respeta la ventana de antigüedad elegida en Radar. La clasificación visible se normaliza en `skill_overview` para no alterar los datos históricos.

## Hallazgos de la muestra actual

La base contiene 268 ofertas con antigüedad de hasta 365 días y 37 nombres de skill configurados. Las señales con mayor evidencia son Excel (137 ofertas), Power BI (52), English (50), SQL (41), SAP (39), Optimization (36), Inventory Management (30) y Python (28).

`5S` aparece en 3 descripciones reales: orden y limpieza en operaciones, conocimiento de 5S en PCP y una mención junto a Lean Manufacturing. No se elimina. Se clasifica como **metodología**, con menor prioridad que una herramienta técnica. `Six Sigma` aparece en 2 ofertas y recibe la misma lectura metodológica.

## Taxonomía aplicada

- **Técnica:** herramientas, lenguajes, plataformas y automatización: Excel, SQL, Python, PostgreSQL, Power BI, SAP, Tableau, RPA, Power Automate, OR-Tools, ETL, APIs y similares.
- **Dominio:** conocimiento funcional del trabajo: Supply Chain, Inventory Management, Demand Planning, Forecasting y Optimization.
- **Metodología:** formas de trabajo y mejora: Lean, 5S, Six Sigma, Kaizen, VSM, BPMN, Scrum y Project Management.
- **Idioma:** English. No se mezcla con soft skills ni con herramientas.
- **Blandas:** comunicación, trabajo en equipo, pensamiento analítico, resolución de problemas, liderazgo y adaptabilidad.

Las habilidades blandas se extraen con frases explícitas y se conserva el fragmento de evidencia. Tras reconstruir las relaciones de las 268 ofertas, las más frecuentes son Comunicación (72), Proactividad (45), Trabajo en equipo (42), Toma de decisiones (41), Liderazgo (38), Atención al detalle (32), Colaboración (29), Negociación (25), Resolución de problemas (23), Pensamiento analítico (19), Orientación al cliente (8) y Adaptabilidad (6). Estos conteos no deben interpretarse como requisitos obligatorios: la mayoría de las asociaciones son `unknown` porque la oferta menciona la competencia sin marcarla como requisito.

El extractor evita palabras demasiado genéricas como `responsable` u `organización`, que aparecen en descripciones corporativas y producirían falsos positivos. También reconoce `deseable/preferible` como `preferred` y expresiones como `requisito/indispensable/debe contar` como `required`, guardando siempre la evidencia textual.

## Uso en la vista Competencias

El grafo ahora es una red de demanda: las skills se conectan al mercado y, al seleccionar una skill, aparecen nodos de ofertas reales que la mencionan. Los nodos se pueden arrastrar como en Obsidian. El color distingue la taxonomía y el tamaño representa el número de ofertas. Ranking permite comparar todos los registros; Evolución conserva los snapshots disponibles.

La relación skill-oferta usa el endpoint filtrado por `job_skills`, por lo que cada oferta mostrada tiene una asociación persistida y no una coincidencia visual inventada. La vista Competencias conserva únicamente Ranking y Evolución; la antigua vista de grafo fue retirada.

## Límites conocidos

La extracción sigue siendo basada en alias y evidencia textual; no reemplaza una revisión semántica humana. Los snapshots históricos existentes provienen de capturas previas, así que la comparación solo es válida para las fechas disponibles. Para medir evolución mensual de forma consistente hay que programar una captura con la misma ventana de antigüedad y conservar su fecha.
