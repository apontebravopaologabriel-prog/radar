## inicio
Radar cubre todo el Perú: ordena las ofertas de empleo por lo bien que encajan contigo y te dice qué te falta para cerrar la brecha. Flujo: 1) elige tu carrera, 2) declara tu perfil y skills (solo lo cierto), 3) revisa "Hoy", 4) guarda lo que te interesa y sigue tu proceso en "Seguimiento". Radar nunca postula ni escribe a empresas por ti.

## hoy
La pestaña Hoy muestra pocas ofertas frescas que encajan, con el motivo en una línea (skills que coinciden y las que te faltan). Acciones: Guardar (pasa a Seguimiento), ★ (favorita), No me interesa (la oculta) y Abrir (enlace original). Abajo, "Qué aprender primero" simula cuánto sube tu encaje al dominar cada skill faltante. Sin perfil no hay puntaje: configúralo primero.

## seguimiento
Seguimiento lleva cada oferta por: Guardadas, Postulé, Entrevista, Oferta y Descartadas. Los botones mueven la oferta al siguiente estado y conservan el historial. Si llevas 7 días o más en "Postulé" sin novedad, Radar sugiere hacer seguimiento. Radar solo registra: la postulación la haces tú en el portal.

## perfil
El perfil tiene nombre, formación, áreas que buscas, ubicaciones, modalidad y skills con nivel (ninguno, básico, medio, alto). Declara solo lo que es cierto: el puntaje y las brechas se calculan con eso y nunca se inventan niveles. Se edita desde Onboarding o pidiéndoselo al agente, que siempre te pide confirmar.

## carrera
La carrera activa define las áreas, competencias, señales de título y pesos con que se clasifican las ofertas nuevas (hoy: Ingeniería Industrial y Contabilidad). Cambiarla afecta a las ofertas que se ingesten desde ese momento; las ya guardadas conservan su clasificación. Se cambia en Ajustes.

## pesos
En Ajustes → "Qué pesa más en el encaje" ajustas la importancia de área, skills, nivel, formación, ubicación y modalidad. Los pesos se normalizan para sumar 100 % y al aplicar se recalcula el puntaje de todas las ofertas.

## agente
El agente responde preguntas y hace consultas con las mismas herramientas del MCP. Usa tu propia clave de API (Ajustes → Agente); pagas al proveedor por lo que uses y hay un tope mensual de tokens. Consulta libremente, pero toda acción que modifica datos (favoritos, seguimiento, perfil, carrera) aparece como tarjeta y solo se ejecuta si la apruebas. No envía mensajes ni postula.

## mapa
La pestaña Mapa muestra un punto por lugar del Perú (distritos de Lima y Callao, y ciudades del resto del país) con la cantidad de ofertas. Toca un punto o elige un lugar de referencia y un radio (2, 5, 10, 25 o 100 km, o Todo Perú): abajo verás las ofertas de la más cercana a la más lejana. La distancia es entre centroides de distrito o ciudad, así que es aproximada; un punto punteado y "dpto." significan que la oferta solo indica el departamento y se ubica en su capital. El mapa carga los mosaicos de un servidor externo (OpenStreetMap), que ve qué zona miras. El mapa completo de escritorio (distritos y radar) está en Ajustes → modo avanzado, y ahí también Análisis (consultas SQL de solo lectura) y CVs (tus brechas contra los puestos con ★).

## actualizar
Las ofertas se actualizan desde tu PC (no desde el celular) con el refresco de Radar o el comando `radar ingest`. El agente no busca en portales por ti. Si "Hoy" está vacío, actualiza el mercado.

## acceso-remoto
Para usar Radar en el celular fuera de casa hace falta llegar a tu PC (Tailscale o un túnel) y definir RADAR_ACCESS_TOKEN. Sin esa clave no expongas la API fuera de localhost. Los pasos están en docs/operations.md.

## privacidad
Tus datos viven en tu equipo (SQLite). Al usar el agente, tu perfil y las ofertas consultadas se envían al proveedor de IA que elijas; con Ollama local no salen de tu equipo. La clave de API se guarda en un archivo privado, no en la base ni en el navegador.
