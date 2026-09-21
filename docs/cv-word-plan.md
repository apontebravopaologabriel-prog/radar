# CV en Word: viabilidad y plan detallado

Estado: **implementado (v1)**. Existen la vista `CVs`, la brecha base y el CV descargable en DOCX y PDF.
Lo que sigue pendiente está en «Pendiente» al final.

## Lo construido (v1) y en qué se aparta del diseño original

- **Sin dependencias nuevas.** El DOCX lo escribe `src/radar/cv_docx.py` con la biblioteca estándar (zip + XML):
  una columna, sin tablas ni imágenes, encabezados estándar y viñetas reales. El PDF sale de LibreOffice (`soffice`)
  si está instalado; si no, se entrega solo el DOCX y se avisa. Los chequeos usan `pdfinfo` y `pdftotext` si existen.
- **Ids derivados, sin migrar el archivo.** Cada línea se identifica con un hash de su contenido
  (`exp:1a2b3c4d`), así que `cv_master.json` no cambia de formato y la trazabilidad funciona igual.
- **Selección por código** (`src/radar/cv_build.py`): puntúa cada viñeta, proyecto y certificado por las skills de la
  oferta (mismos alias que el cruce del CV), respeta un presupuesto de página (1 página con menos de 36 meses de
  experiencia o en ofertas de práctica/trainee/junior; 2 en los demás casos) y anota qué deja fuera y por qué.
- **Solo hechos reales.** Las skills en `falta` nunca se listan. El resumen es el tuyo. No se reformula.
- **Idioma** detectado de la oferta (español o inglés); los encabezados y meses cambian con él.
- **Cobertura honesta:** demostradas en el cuerpo, solo listadas (sin respaldo) y ausentes (no se añaden).
- **Avisos antes de enviar:** faltan datos de contacto, o tu CV contiene marcadores como «(nombre no indicado)».
- **Trazabilidad:** junto a cada archivo se guarda un `manifest.json` (oferta, plantilla, ids incluidos y omitidos,
  cobertura, hash del perfil). Los archivos van a `<datos>/cvs/<fecha>/CV_<Empresa>_<Puesto>.docx` y nunca se
  sobrescriben. La API solo sirve archivos de esa carpeta y con extensión `.docx` o `.pdf`.
- **Interfaz:** en el detalle de cada objetivo, «CV descargable»: vista previa, cobertura, qué queda fuera y descarga.
- **Herramientas del agente:** `preview_cv` y `build_cv` (esta última pide confirmación). Datos de contacto:
  `update_cv` con `section=contact`.
- **Foto:** apagada (no se incluye), por ser lo más seguro para los ATS.

## Pendiente

Reformulación asistida con marca «reformulado», plantillas adicionales (`moderno`, `compacto`), edición de un Word
propio y la importación de tu CV desde texto o PDF.

> **Lo que sigue es el diseño original.** Sirve como contexto y como hoja de ruta de lo pendiente; la v1 real es la
> descrita arriba (por ejemplo, no usa `python-docx` ni plantillas en carpetas, y los ids se derivan del contenido).

## Qué se quiere

Un CV real en Word por oferta, hecho con datos verdaderos del usuario, donde el agente decide qué
mostrar y en qué orden pero **no genera el archivo**: lo construye código determinista. Además, que
el diseño pueda variar según la empresa y que el sistema sea extensible.

## Análisis: ¿puede el agente adaptar el diseño por empresa?

| Enfoque | Viabilidad | Motivo |
| --- | --- | --- |
| El agente diseña el Word libremente (XML, estilos, columnas) | **No** | Frágil: documentos corruptos o ilegibles, imposible de validar, resultados distintos cada vez. |
| Imitar la marca de la empresa (colores, logo) | **No** | Un CV no es un documento de esa empresa; copiar logos o paletas parece suplantación y no aporta. |
| El agente **elige entre plantillas** predefinidas y ajusta parámetros acotados | **Sí** | Determinista, verificable y fácil de auditar. |
| El código verifica el resultado (páginas, texto extraíble) | **Sí** | LibreOffice está instalado (`soffice`): se convierte a PDF, se cuenta páginas y se extrae texto. |

Además, el diseño importa menos que el contenido. Los portales y los sistemas de filtrado (ATS)
leen mejor un documento de **una sola columna, con encabezados estándar y sin imágenes en el
cuerpo**. Un diseño llamativo puede empeorar el resultado. Por eso las plantillas deben ser
sobrias y "a prueba de ATS", y variar en tono, no en estructura: por ejemplo `clasico` (corporativo,
banca, retail), `moderno` (tecnología y datos) y `compacto` (una página, prácticas).

**Conclusión:** viable y útil si "adaptar el diseño" significa *elegir plantilla y ajustar parámetros
acotados*; no lo es si significa diseño libre. El agente elige con una regla explícita (sector,
seniority, largo del CV), no por gusto.

## Extensibilidad

Las plantillas son **datos, no código**:

```text
~/.local/share/radar/cv_templates/
├── clasico/
│   ├── template.docx      # Word con marcadores Jinja ({{ nombre }}, bucles de experiencia)
│   └── manifest.json      # nombre, descripción, mejor_para, máximo de páginas, secciones que admite
├── moderno/...
└── compacto/...
```

Añadir un diseño es dejar una carpeta nueva: no requiere tocar Radar. El agente descubre las
opciones con `list_cv_templates()`, que devuelve el manifiesto. Si el usuario ya tiene un Word propio,
se convierte en una plantilla más (con sus estilos intactos).

## Regla anti-invención

- Cada viñeta del CV debe rastrearse a un elemento de `cv_master.json` (por `id`).
- El agente puede **elegir, ordenar y omitir**. Si reformula, la línea queda marcada como
  `reformulado` con el original al lado, para revisión.
- Nada hipotético entra: el candidato ideal no se puede exportar. Solo se usan hechos reales.
- Cada archivo generado guarda un registro (qué se eligió, hash del perfil, plantilla, fecha).

## Herramientas MCP previstas

| Herramienta | Qué hace |
| --- | --- |
| `list_cv_templates()` | Plantillas disponibles y para qué sirve cada una. |
| `inspect_docx(ruta)` | Analiza un Word existente: encabezados, secciones, viñetas, tablas, marcadores y estilos, para saber dónde actuar. |
| `build_cv_docx(job_id, plantilla, seleccion)` | Rellena la plantilla con la selección (ids de viñetas, orden, resumen). Guarda una copia nueva; **nunca sobrescribe** el original. |
| `check_cv_docx(ruta)` | Verifica páginas, texto extraíble y que cada línea tenga origen en el perfil. |

## Plan por fases

**A. Selección desde la interfaz y brecha base — hecho.** Los objetivos son los favoritos (★). Radar
calcula por reglas el estado de cada requisito y una cercanía ponderada; con pocas señales muestra
"datos insuficientes" en lugar de una cifra engañosa.

**B. Vista CVs con ranking, matriz y comparación — hecho.**

**C. Perfil maestro con ids (1 día).** Añadir `id` a cada viñeta, logro y certificado de
`cv_master.json` y un modelo de logros medibles ("reduje X%") para que el agente tenga material real.
Sin esto, la trazabilidad de la regla anti-invención no es posible.

**D. Motor de plantillas (2 días).** Dependencias opcionales (`python-docx`, `docxtpl`) en
`pyproject.toml` como extra `cv`. Cargador de plantillas y manifiestos. Plantilla `clasico`
sobria. `build_cv_docx` con validación de origen y salida `CV_<Empresa>_<Puesto>.docx` en una
carpeta por fecha. Pruebas: el archivo abre, tiene las secciones esperadas y cada línea tiene origen.

**E. Verificación y edición de Word existente (2 días).** `check_cv_docx` (LibreOffice: PDF,
conteo de páginas, texto extraíble) e `inspect_docx`. Edición de un Word propio del usuario con
reemplazo a nivel de fragmento, para conservar el formato.

**F. Plantillas adicionales y selección guiada (1 día).** `moderno` y `compacto`, y una regla
documentada para elegir plantilla según la oferta.

**G. Vínculo con la interfaz (1 día).** Botón "Generar CV" en el detalle de un objetivo, que muestra
qué se eligió y qué línea fue reformulada; el archivo se abre desde la carpeta.

## Riesgos y decisiones abiertas

- **Un CV base propio.** Hoy no existe un Word del usuario; se parte de una plantilla sobria y
  puede estilizarse después en Word sin perder el funcionamiento.
- **Reformulación.** Es la parte más sensible; se recomienda empezar sin ella (solo elegir y
  ordenar) y activarla cuando el flujo esté probado.
- **Idioma.** Hay ofertas en inglés; las plantillas deben soportar secciones en ambos idiomas.
- **Dependencias.** `python-docx` y `docxtpl` no están instaladas; se declaran como extra opcional.
