# MEI → RDF Mapping Rules


---

## 1. Namespaces

| Prefix | IRI | Role |
|---|---|---|
| `frbr:` | `http://purl.org/vocab/frbr/core#` | Work / Expression separation |
| `mo:` | `http://purl.org/ontology/mo/` | Musical work typing |
| `dcterms:` | `http://purl.org/dc/terms/` | Titles, identifiers, creators, dates |
| `foaf:` | `http://xmlns.com/foaf/0.1/` | Agents |
| `owl:` | `http://www.w3.org/2002/07/owl#` | Verified identity links only |
| `cnw:` | `https://cnw-ld.org/ontology#` | Catalogue-specific extensions (18 terms) |

**Principle.** Established vocabularies are reused wherever they express the
concept. `cnw:` is minted **only** where no established term exists — 18 terms,
declared in `ontology/cnw.ttl`.

---

## 2. Identity and IRI minting

The single most consequential rule, because every other triple hangs off it.

| # | MEI source | Condition | RDF target | Ambiguity rule |
|---|---|---|---|---|
| R1 | `work/identifier[@label='CNW']` | non-empty | Work IRI `…/work/CNW{n}`; `cnw:cnwNumber` | **Absent** → fall back to a slug of the first title (`…/work/{slug}`). The work is still emitted but **fails the SHACL shape** requiring one CNW number. Deliberate: the failure surfaces a CNW-specific assumption. (**E04**) |
| R2 | same | value is not an integer | literal preserved verbatim | The collection record's value is the range `"126–131"`. Preserved as a string; **queries must not cast to `xsd:integer`** or they crash. (**E05**) |
| R3 | `work/identifier[@label='Opus']` | present | `cnw:opus` | Spacing normalised (`"10. 1"` → `"10.1"`). Absent → property omitted, never an empty literal. (**E06**, **E07**) |
| R4 | `work/identifier[@label='FS']` | present | `cnw:fsNumber` | Optional; older Fog-Schousboe numbering. |
| R5 | — | always | Expression IRI `{workIRI}/expression/{i}` | Derived, not sourced. Guarantees expression IRIs are unique and dereferenceable. |

> **Known weakness.** R1's fallback keys on the title, so two untitled or
> identically-titled works would collide. Not exercised by the corpus (**E25**,
> UNTESTED) and stated as a limitation rather than claimed safe.

---

## 3. Titles

| # | MEI source | Condition | RDF target | Ambiguity rule |
|---|---|---|---|---|
| R6 | `work/title` | first, not `@type='alternative'` | `dcterms:title` with `@xml:lang` → language tag | Language tag preserved; dropping it would break the `lang(?title)="en"` filters the competency questions rely on. |
| R7 | `work/title[@type='alternative']` | present | `dcterms:alternative` | Multiple alternatives all emitted. |
| R8 | `work/title` | **several in the same language** | first becomes `dcterms:title`, rest `dcterms:alternative` | **Selection is arbitrary** — document order decides. CNW 2 carries both *"Masquerade"* and *"Comic Opera in Three Acts"* as English titles, so which string reaches the reconciler is not principled. Affects RQ3 match quality. 9 of 11 records are affected. (**E17**) |
| R9 | `title` containing `<rend>` | any | flattened with `string()` | Formatting markup is stripped, text content kept — a literal must not carry XML markup. (**E12**) |

---

## 4. Agents (composer, text author)

| # | MEI source | Condition | RDF target | Ambiguity rule |
|---|---|---|---|---|
| R10 | `persName[@role='composer']` | `@auth='VIAF'` and `@codedval` | Agent IRI `…/agent/viaf/{codedval}`; `dcterms:creator`; `owl:sameAs <viaf.org/viaf/{codedval}>` | Authority-keyed IRI is the **preferred** form: it makes identity resolvable. |
| R11 | same | **no `@codedval`** | Agent IRI `…/agent/{name-slug}` | Produces a *second node for the same person* when some records carry VIAF and others do not. Observed: `agent/viaf/197250` **and** `agent/carl_nielsen` both denote Carl Nielsen. Identity resolution is required future work. (**E16**) |
| R12 | same | name is bracketed, e.g. `[Carl Nielsen]` | brackets retained in `foaf:name`, slug strips them | Brackets are the editorial convention for an *attributed* (uncertain) ascription. Retaining them preserves scholarly meaning but compounds R11's duplication. (**E15**) |
| R13 | `persName[@role='author']` | present | `cnw:textAuthor` → `foaf:Agent` | Kept **distinct** from `dcterms:creator`: the poet is not the composer. |

> `owl:sameAs` is used **only** at R10, where an authority identifier licenses an
> identity claim. See §8.

---

## 5. Expression-level musical attributes

| # | MEI source | Condition | RDF target | Ambiguity rule |
|---|---|---|---|---|
| R14 | `expression/key` | `@pname` + `@mode` | `cnw:key` as `"E major"` | Assembled into a human-readable literal so `?e cnw:key "D major"` works without a lookup table. |
| R15 | `expression/meter` | `@count` and `@unit` | `cnw:meter` `"count/unit"` | Direct. (**E01**) |
| R16 | `expression/meter` | **`@sym`** | `common` → `"4/4"`; `cut` → `"2/2"` | The first stylesheet handled only R15 and **silently dropped meter** for records using `@sym`. Any other `@sym` value is omitted rather than guessed. (**E02**) |
| R17 | `expression/meter` | absent | property omitted | No empty literal. Guarded by `test_meter_never_empty_when_present`. (**E03**) |
| R18 | `expression/tempo` | present | `cnw:tempo` | Verbatim; tempo terms are not normalised to a vocabulary. |
| R19 | `perfMedium//perfRes` | present | `cnw:performingForce`, one triple per resource | Element text preferred over `@codedval`, which is an abbreviation (`"vn"`). |
| R20 | `work//expression` | **more than one** | **only the first is mapped** | **Known limitation.** *Maskarade* carries many expressions; its coverage falls to 78.6%. A modelling gap, not a parse failure: the mapping must iterate. Guarded by `test_multi_expression_work_limitation_is_visible`, which fails when fixed, forcing the report to be updated. (**E08**) |

---

## 6. Incipits and notation

The distinction here was a genuine finding, not a design decision made up front.

| # | MEI source | Condition | RDF target | Ambiguity rule |
|---|---|---|---|---|
| R21 | `incip/incipText/p` | present | `cnw:incipitText` (language-tagged) | Text incipit — the sung opening words. |
| R22 | `incip//graphic` | present | `cnw:incipitImage` | A *pointer to a pre-rendered image*, not encoded notation. |
| R23 | `incip//score` | present | `cnw:hasNotatedIncipit true` | Notation **inside** the incipit element. |
| R24 | `music/body//score` | present | `cnw:hasNotatedMusic true` | Renderable notation **anywhere** in the record. CNW 129's notation sits here, *not* in `<incip>` — so "has a notated incipit" and "has renderable notation" are different questions and need different predicates. |
| R25 | `score` present, **`body` absent** | — | neither flag set | `incipit_demo.xml` contains `<score>` markup but no `<body>`; Verovio rejects it (*"No `<body>` element found"*). **Markup presence ≠ renderability.** The bulk renderer skips such records without aborting. (**E10**) |

---

## 7. Editorial and contextual layers

| # | MEI source | Condition | RDF target | Ambiguity rule |
|---|---|---|---|---|
| R26 | `work//annot` | non-empty, general | `cnw:editorialNote` | Nested `<rend>` flattened via `string()`. (**E12**) |
| R27 | `annot[@type='source_description']` | — | `cnw:sourceDescription` | **Sits outside `<work>`** in the source, so a work-scoped selector misses it. Currently DEGRADED. (**E13**) |
| R28 | `physLoc/repository` | present | `cnw:manuscriptLocation` | Emitted as a **raw RISM siglum** (`"S-Skma"`), not resolved to an institution name or IRI. Honest limitation. (**E14**) |
| R29 | `relationList/relation[@rel='isPartOf']` | present | `dcterms:isPartOf` → collection IRI | Enables the collection competency question. (**E18**) |
| R30 | `history/eventList/event` | present | `cnw:performanceCount` (integer) | **Counted only**; premiere date, venue and performers are not modelled. Deliberate scope boundary. (**E19**) |
| R31 | `biblList/bibl` | present | *(nothing)* | **UNHANDLED** — related documents (letters, diary entries) are out of scope for the current model. Present in 9 of 11 records. (**E20**) |

---

## 8. Reconciliation (`reconcile.py`, not the XSLT)

| # | Condition | RDF target | Rule |
|---|---|---|---|
| R32 | Match via a shared authority identifier (e.g. VIAF) | `owl:sameAs` | Identity is **asserted** only when an identifier licenses it. |
| R33 | Match via string similarity ≥ 0.90 | `cnw:reconciledTo` + `cnw:matchConfidence` + `cnw:matchSource` | `owl:sameAs` is **deliberately not used**: a similarity score does not license an identity claim, and a wrong `sameAs` propagates through inference. |
| R34 | Similarity 0.60–0.90 | *(no triple)* | Written to the review queue for manual adjudication. |
| R35 | Cross-language titles | *(usually no match)* | *"Apple Blossom"* vs *"Æbleblomst"* scores far below threshold — a true match the system misses. A **recall** limitation, honestly reported rather than hidden by lowering the threshold. |

---

## 9. Rules by verdict

| Verdict | Rules | Meaning |
|---|---|---|
| **HANDLED** | R1–R3, R5–R10, R13–R19, R21–R26, R29, R32–R34 | Specified, implemented, test-guarded |
| **DEGRADED** | R11, R12, R20, R27, R28, R30, R35 | Works, but with a documented loss |
| **UNHANDLED** | R31 | Deliberately out of scope |
| **UNTESTED** | R1 collision case | No corpus fixture exists |

**Reading the ratio honestly:** roughly two-thirds of rules are fully handled;
the degraded third concentrates in *identity* (R11/R12/R35) and *depth of
context* (R27/R28/R30). Neither blocks the core claim that scholarly work-level
content survives the transformation — but both bound how far that claim reaches,
and both are named rather than smoothed over.
