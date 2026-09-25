# Gold-standard reconciliation set

`reconciliation_gold.csv` is the **manually verified** ground truth used to
compute precision/recall for work-level reconciliation (RQ3).

## Columns
| column | meaning |
|---|---|
| `cnw` | CNW catalogue number (blank if the work has none) |
| `work_iri` | must match the IRI in `out/cnw_combined.ttl` exactly |
| `title` | work title, for human readability only |
| `source` | `wikidata` or `musicbrainz` |
| `target_id` | the external IRI |
| `target_label` | label of the external item |
| `is_match` | `true` if this really is the same work, `false` otherwise |
| `note` | why (especially for hard negatives) |

## How to build it credibly
1. For each work, look the target up **by hand** on Wikidata / MusicBrainz and
   record the correct IRI with `is_match=true`.
2. **Include hard negatives** — plausible but wrong targets (same or near-miss
   title, different work). Without them precision is trivially 1.0 and the
   metric says nothing.
3. Include known **false negatives** — true matches you expect the system to
   miss (e.g. cross-language titles like "Apple Blossom" / "Æbleblomst").
   These make recall meaningful.

The rows currently in the file are a **TEMPLATE**: the Wikidata QIDs and
MusicBrainz MBIDs are placeholders. Replace them with real, manually verified
identifiers before quoting any figure in the report.
