| ID | Category | Status | Records | Note |
|---|---|---|---|---|
| E01 | Meter as @count/@unit | HANDLED | 6 | Mapped directly to 'count/unit'. |
| E02 | Meter as @sym (common/cut) | HANDLED | 5 | common->4/4, cut->2/2. Silently dropped before the fix. |
| E03 | Meter absent entirely | HANDLED | 2 | Field omitted; no empty literal emitted. |
| E04 | No CNW catalogue number | DEGRADED | 2 | Falls back to title-slug IRI; fails the CNW SHACL shape. |
| E05 | Non-integer catalogue value (range) | HANDLED | 1 | Ordering must avoid xsd:integer casts. |
| E06 | Opus absent | HANDLED | 4 | Tolerated without failure. |
| E07 | Opus with irregular spacing | HANDLED | 0 | Normalised on output. |
| E08 | Multiple expressions per work | DEGRADED | 4 | Only the first expression is mapped (known limitation). |
| E09 | Renderable notation present (<score> + <body>) | HANDLED | 1 | Flagged cnw:hasNotatedMusic; Verovio renders it. |
| E10 | <score> present but no <body> (unrenderable) | HANDLED | 1 | Detected during bulk render; skipped without aborting. |
| E11 | Text incipit with image pointer only | HANDLED | 10 | Image reference captured; not engraved. |
| E12 | Editorial annotation inside <work> | HANDLED | 11 | Mapped to cnw:editorialNote; nested <rend> flattened. |
| E13 | Source description outside <work> | DEGRADED | 4 | Present in source; work-scoped selector may miss it. |
| E14 | Manuscript location (RISM siglum) | DEGRADED | 10 | Emitted as raw siglum; not resolved to an institution. |
| E15 | Bracketed / uncertain composer name | DEGRADED | 1 | Creates a second agent node; identity resolution needed. |
| E16 | Composer without authority identifier | DEGRADED | 2 | No VIAF IRI; agent keyed on name slug instead. |
| E17 | Multiple titles in the same language | DEGRADED | 9 | Arbitrary title reaches the matcher; affects reconciliation. |
| E18 | Relations to other works (isPartOf) | HANDLED | 6 | Mapped to dcterms:isPartOf. |
| E19 | Performance events recorded | DEGRADED | 8 | Counted only; internal detail unmapped. |
| E20 | Related bibliography (biblList) | UNHANDLED | 9 | Deliberately out of scope for the current model. |
| E21 | Non-Latin / diacritic-heavy titles | HANDLED | 5 | UTF-8 preserved; affects string-similarity matching. |
| E22 | Work from a non-CNW catalogue | DEGRADED | 2 | Exposes CNW-specific assumptions in shapes and IRIs. |
| E23 | Empty <work> element | UNTESTED | 0 | No such record available; behaviour unverified. |
| E24 | Malformed / invalid MEI | UNTESTED | 0 | Would fail at parse; no fixture available. |
| E25 | Duplicate catalogue numbers across records | UNTESTED | 0 | Would collide on work IRI; not exercised by the corpus. |
