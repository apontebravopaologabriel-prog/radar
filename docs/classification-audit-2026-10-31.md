# Industrial and Systems classification audit — 2026-10-31

## Conclusion and scope

Both market projections contain confirmed false positives, and Industrial contains confirmed false
negatives. Independent projections work as a storage boundary, but keyword-based occupational relevance
does not establish academic eligibility or personal suitability. Those decisions must be separated.

This was a read-only inspection of the local SQLite database and the current classifier source. No
classification rules, stored projections, offers or personal state were changed for this audit.
Examples below were selected diagnostically, not randomly; they do not establish an overall error rate.

The database contained 8,275 canonical offers. The counting window below contains active canonical offers
published from 2026-10-01 through 2026-10-31 inclusive, excluding user-hidden offers. It follows the
existing SQL date convention for a 30-day lookback. It is deliberately broader than the UI's default
seven-day filter and does not exclude applied offers.

| Projection | Core | Adjacent | Out of focus | Total |
| --- | ---: | ---: | ---: | ---: |
| Industrial | 2,503 | 222 | 2,422 | 5,147 |
| Systems / Software | 549 | 480 | 4,118 | 5,147 |

372 offers are core in both markets. Overlap is not itself an error: some SAP implementation and business
systems roles explicitly accept both degrees and have genuinely shared responsibilities.

118 Industrial core offers have maintenance, facilities or general services in their titles; 60 of those
explicitly mention an Industrial Engineering degree in their descriptions. The remaining 58 are review
candidates, not proven errors. Degree abbreviations, missing requirements and related backgrounds make
absence of a phrase insufficient to reject an offer.

## Verified cases

Titles identify local records; descriptions are paraphrased rather than reproduced.

| Local job ID | Title | Stored result | Evidence and assessment |
| --- | --- | --- | --- |
| `dcc9217f-3964-4ec8-af3a-5b6e09c47f62` | ASISTENTE DE INVENTARIO | Systems core, DevOps / SRE | Maritime containers in the company introduction trigger DevOps. Duties concern warehouse inventories and WMS; requirements accept Industrial Engineering / Industrial Administration. Keep logistics relevance; remove the unsupported DevOps interpretation. |
| `e5b73129-8a66-4e54-a28f-a18b58eb1bdc` | Supervisor/a de Infraestructura (Servicios Generales) | Systems core, Infrastructure / cloud | Duties cover painting, welding, plumbing and building repairs. Requirements accept Industrial, Civil or Architecture. Physical infrastructure is not evidence of cloud work. |
| `c311de14-2a81-4807-a081-71ab4faac79e` | Responsable de mantenimiento | Industrial core, Facilities | The body actually advertises maintenance operators performing repairs, lubrication and component changes. The generic title bypasses title-only operational exclusions. Distinguish trade execution from engineering management. |
| `5fffee8e-6393-48af-ba8d-d29b9b87c88e` | Planificador de Mantenimiento | Industrial core, Facilities | Planning, budget, availability, OEE, MTBF and MTTR; explicitly accepts Industrial Engineering. This is a legitimate Industrial opportunity. A blanket maintenance exclusion would introduce another false negative. |
| `b864c0f9-e687-4e69-a5f0-ca7917b43979` | Analista de costos e inventarios | Systems core, Systems analysis / product; Industrial core | Repeated Dynamics 365 use creates Systems relevance. Duties are accounting, depreciation, reconciliation and closing; the stated degree is Accounting. ERP operation does not establish an IT implementation role, and Industrial relevance must not imply academic eligibility. |
| `e8a2baef-9054-4ee2-95f2-d8c08106ca35` | Analista de Laboratorio Clínico / Volante/ Tarde | Industrial core, Quality / reliability | Requires a qualified medical technologist and clinical sample processing. Quality and incidental stock management override the actual clinical occupation. Confirmed Industrial false positive. |
| `46cd112e-e8dc-4552-b65f-9f13b1f0ee18` | Supervisor de Producción Industrial | Industrial out of focus | The title is globally excluded as operational, although duties cover production planning, OEE and supervision and requirements explicitly accept Industrial. This is a market false negative; personal seniority or preferences are a separate decision. |
| `e90f4fec-62ce-46ce-9fba-7f28731c1b5f` | Líder de Proyectos - Proyecto SAP | Core in both | Accepts Systems or Industrial; duties include SAP implementation, integrations and architecture. Valid shared-market classification; this does not imply suitability for a junior candidate. |

## Why the engine produces these results

1. `classify._area_score()` scores every description section together. Strong description terms score
   0.8 per occurrence (up to three); the area threshold is 1.5. Two occurrences of one ambiguous term
   can therefore assign an area, including occurrences in the employer's marketing text.
2. The Systems pack treats generic `contenedores` and `infraestructura` as strong signals, without
   requiring digital responsibilities. Repeated ERP product names can similarly outweigh the actual
   accounting occupation.
3. `infer_relevance()` uses substring matching for context and title policies. Short context terms
   such as `ti` and `api` can match inside unrelated words. This context can strengthen an already
   assigned core area; it does not, by itself, create the initial area.
4. Any core secondary area promotes the offer to core, even when the primary occupation is adjacent.
   Target titles can also return core regardless of the assigned area. Conversely, operational title
   exclusions run first and can reject legitimate production supervision.
5. `education_only` detects mentions, not accepted qualifications. The engine does not extract
   degree alternatives, degree level, mandatory versus desirable conditions, or incompatible
   professional prerequisites. It cannot reliably state that an applicant's degree is accepted.
6. Broad career membership and personal target-job preferences are mixed in the built-in Industrial
   pack. Personal exclusions must not redefine the entire Industrial labor market.
7. Global legacy Industrial area sets remain as a compatibility fallback in `taxonomy.py`, outside
   the pack boundary. Also, out-of-focus rules are flattened and assigned the first out-of-focus area;
   this is a latent problem for packs with more than one such rule group.
8. Projection `pack_hash()` fingerprints pack data but not the classifier engine version. Changing
   Python logic alone can leave stored projections apparently current.

The stored relevance values such as 0.97 are rule weights, not calibrated probabilities. They should
not be described as a measured 97% classification accuracy or eligibility confidence.

## Proposed decision model

Keep the interface minimal; improve the evidence model rather than adding more compulsory filters.
Compute three independent results per offer:

| Result | Question | Suggested states |
| --- | --- | --- |
| Occupational market relationship | Are the actual responsibilities part of this market? | Core, adjacent, outside, insufficient evidence |
| Academic compatibility | What qualifications does the employer explicitly accept? | Explicitly accepted, possibly related, no compatible degree stated, incompatible mandatory prerequisite, unknown |
| Personal fit | Does the offer match this person's experience, level and preferences? | Separate explained dimensions; do not rewrite market membership |

An omitted degree is unknown. The phrase “related degrees” is not a guarantee. Administration alone
must not automatically mean Industrial: operations, procurement, logistics, process improvement and
control can be related, while sales or accounting roles need their own functional and academic evidence.
Likewise, a healthcare employer can hire an Industrial process analyst; employer sector alone is not
a clinical-occupation exclusion.

Parse title, responsibilities, requirements and employer introduction separately. Use role functions
as the main occupational evidence, requirements for academic compatibility and employer text only as
weak background. Preserve source spans and explicit uncertainty when section parsing is ambiguous.

Pack data should define degree aliases, digital/physical context groups, responsibility phrases and
occupation conflicts. Generic Python engines should interpret them; do not add career-specific Python
branches or silently use an LLM to decide validity or scores.

## Recommended implementation order

1. **Establish regression cases.** Turn the verified cases above into small paraphrased fixtures, plus
   positive software infrastructure, Docker/Kubernetes, functional ERP implementation, shared SAP,
   maintenance planning and genuine Industrial production cases. Do not version complete job postings.
2. **Fix ambiguous evidence.** Use word boundaries for context; separate employer text; require
   digital functions for cloud/containers and implementation/configuration functions for functional
   ERP roles. An isolated tool or secondary area must not override the main occupation.
3. **Separate market and profile policies.** Remove personal title preferences from global career
   acceptance. Distinguish hands-on maintenance from planning/reliability through responsibilities.
4. **Extract academic evidence.** Normalize degree alternatives and levels, mandatory/desirable
   wording and related-degree uncertainty. Store structured evidence; do not infer acceptance from
   a degree mentioned outside requirements.
5. **Version projections correctly.** Include engine and evidence-schema versions in invalidation.
   Preview old/new classifications in a report before applying a backed-up production rebuild.
6. **Measure quality.** Independently label a stratified sample containing core, adjacent and excluded
   records in both markets, including ambiguous and shared occupations. Keep a held-out subset;
   report precision, recall and unknown coverage per market and error family. The diagnostic examples
   in this document are regression cases, not an unbiased evaluation set.

Only after comparing the preview should new classifications replace stored projections. Historical
offers, favorites, hidden state and applications must be preserved.

## Reproducing the counting scope

Open SQLite with `mode=ro` and do not call the application's schema initializer for an audit.

```sql
SELECT m.market_id, m.relevance_tier, count(*)
FROM jobs j
JOIN job_market_classifications m ON m.job_id = j.id
WHERE j.is_active = 1
  AND j.duplicate_status = 'canonical'
  AND date(j.published_at) >= date('2026-10-31', '-30 days')
  AND date(j.published_at) < date('2026-10-31', '+1 day')
  AND NOT EXISTS (
    SELECT 1 FROM job_user_status u
    WHERE u.job_id = j.id AND u.status = 'hidden'
  )
GROUP BY m.market_id, m.relevance_tier;
```

Counts are a dated snapshot and will change with capture, liveness and user state. Inspect each selected
record's saved description, `areas` evidence and `relevance_evidence` to reproduce the case assessment.
