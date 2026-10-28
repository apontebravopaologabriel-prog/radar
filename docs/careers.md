# Career packs

A career pack is a JSON file with everything career-specific: areas, classification rules, skills and score
weights. The engines (`careers/__init__.py`, `classify.py`, `taxonomy.py`, `scoring.py`) are generic, so
adding a career means adding a JSON file, not Python.

## Where packs live

| Location | Use |
| --- | --- |
| `src/radar/careers/packs/*.json` | Built-in packs (versioned). Today: `industrial_engineering` (default) and `sistemas_software` |
| `<database folder>/careers/*.json` | Packs created by the user (onboarding form, `create_career_pack` tool, or by hand). Not versioned |

The active career is chosen in this order: the setting stored in the database (Settings or
`set_career_track`), then `RADAR_CAREER`, then `industrial_engineering`. Each person works with one career at
a time on their own local database.

## Format

```jsonc
{
  "id": "sistemas_software",                  // required; equals the file name
  "name": "Contabilidad y Finanzas",          // required
  "country": "PE", "language": "es",
  "areas": {                                  // required
    "core": ["Contabilidad", "Auditoría"],
    "adjacent": ["Data / BI"],
    "out_of_focus": ["Ventas / Comercial", "Otras"]
  },
  "area_slugs": { "Contabilidad": "contabilidad" },
  "area_rules": {                             // required; keys must exist in `areas`
    "Contabilidad": ["contabilidad", "contador", "niif"]   // accent-free, lowercase terms
  },
  "out_of_focus_rules": { "Ventas / Comercial": ["vendedor", "ejecutivo comercial"] },
  "skills": {                                 // required
    "Excel": { "aliases": ["excel"], "category": "herramienta", "type": "technical" }
    // type: technical | domain | methodology | language | soft
  },
  "excluded_title_signals": ["auxiliar de limpieza"],  // titles that are never this career
  "education_only": ["contador publico"],              // terms that describe a degree, not an area
  "context_terms": ["contab", "tribut"],               // roots that mark an offer as in-context
  "weak_terms": ["proyectos", "sql"],                  // generic terms; score 0.25 instead of 0.8
  "target_titles": ["analista de control de gestion"], // title contains it: core ("Cargo objetivo"), whatever the area
  "operational_titles": ["operario", "almacenero"],    // title contains it: out of focus, unless a target title matches
  "adjacent_title_signals": ["ingenieria industrial"], // title contains it: at least adjacent
  "scoring": {                                // required; exactly these 6 keys, summing to 1
    "area": 0.30, "skills": 0.25, "seniority": 0.15,
    "education": 0.10, "location": 0.10, "preference": 0.10
  },
  "queries": ["practicante contable"],        // short searches: in-app refresh and extra cities
  "market_queries": ["desarrollador Python"]  // broad searches for the weekly capture of Lima (defaults to queries)
}
```

Validation (`parse_pack`): missing required keys, `scoring` keys other than the six, weights not summing to 1,
or rules for undeclared areas raise `CareerPackError`. A broken user pack is skipped, never breaks the app.
Custom packs created from the UI are limited to 20 areas, 60 skills and 12 keywords per area.

## How the engines use a pack

- **Areas:** `classify.py` scores each area (title match 3, strong description mention 0.8 up to 3, weak term
  0.25). Under 1.5 the offer is `Otras`. See [database.md](database.md#classification).
- **Relevance:** `taxonomy.py` maps the primary area to `core`, `adjacent` or `out_of_focus`.
- **Skills:** alias matching in title and description, with evidence kept per offer.
- **Score:** `scoring.py` combines the six weighted dimensions; the user can change weights
  (`set_score_weights`) and the breakdown is always shown.
- **Rules fingerprint:** changing a pack changes the classification-rules hash, so the agent prompts for an
  audit (`audit_classification`) and a reclassification (`reclassify_jobs`) of stored offers.

## Adding a career (checklist)

1. Copy the closest pack and change `id`, `name`, areas, rules, skills, `queries` and `market_queries`.
2. Write accent-free lowercase terms; prefer specific phrases over generic words; put generic words in
   `weak_terms`.
3. Validate it: `radar career validate <path-to-json or id>` (errors block use; warnings list areas without slug or
   rules, skills without aliases, missing queries). `radar career list` shows what is loaded.
4. Ingest a sample (`radar ingest --query ... --limit 25`), then review the area distribution with
   `get_market_breakdown(by="area")` and `audit_classification`. Offers piling into `Otras` mean missing
   terms; offers in a wrong area mean terms that are too generic.
5. Add real titles with their expected area to `SAMPLES` in `tests/test_careers.py` (the parametrized regression test
   and the completeness test then cover the new pack automatically).
6. Update `help.md` if the career list shown to users changes.

## Known limitations

- The area catalog table is still named `industrial_areas` (it stores areas for every pack); renaming it is cosmetic and
  deferred because it touches many queries.
- Keyword classification degrades on careers with ambiguous vocabulary; measure the share of `Otras` after every new
  pack. Short, generic terms (for example `ui`, `qa`, `sql`) belong in `weak_terms`.
- A user pack can only be created from the form/tool with simplified fields; the full format above needs a JSON file in
  `<database folder>/careers/`.
