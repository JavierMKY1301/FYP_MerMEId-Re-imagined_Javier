#!/usr/bin/env python3
"""
run_pipeline.py

Vertical slice of the project pipeline:
  MEI XML  --(Saxon XSLT 3.0)-->  RDF/Turtle  -->  reconciliation
           -->  SHACL validation  -->  triplestore (rdflib)
           -->  SPARQL competency questions  +  coverage metrics.

The transformation itself is XSLT 3.0 (xslt/mei2rdf.xsl) run by Saxon-HE.
Python only orchestrates: invoking Saxon, merging graphs, validation,
querying, and measuring. SPARQL is engine-agnostic; the production system
serves the identical queries from Apache Jena Fuseki.
"""
import glob, json, os, sys
from lxml import etree
from saxonche import PySaxonProcessor
import rdflib
from rdflib import Graph
from pyshacl import validate
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = sorted(glob.glob(os.path.join(HERE, "data", "*.xml")))
XSLT = os.path.join(HERE, "xslt", "mei2rdf.xsl")
OUT  = os.path.join(HERE, "out")
MEI  = "{http://www.music-encoding.org/ns/mei}"
os.makedirs(OUT, exist_ok=True)

CNW = rdflib.Namespace("https://cnw-ld.org/ontology#")
DCT = rdflib.Namespace("http://purl.org/dc/terms/")
OWL = rdflib.Namespace("http://www.w3.org/2002/07/owl#")

# Verified external identifiers for Carl Nielsen (composer-level reconciliation).
NIELSEN_AGENT = rdflib.URIRef("https://cnw-ld.org/agent/viaf/197250")
# Verified external identifiers, keyed by composer surname. Nielsen's were
# confirmed by hand against VIAF, Wikidata, MusicBrainz and IMSLP. The other
# three composers deliberately carry no composer-level identifiers here rather
# than invented ones. Work-level reconciliation in reconcile.py performs live
# lookups that cover them.
RECON = {
    "nielsen": [
        "http://www.wikidata.org/entity/Q205139",
        "https://musicbrainz.org/artist/1be1367d-119f-4b08-bdfe-50b95043e544",
        "https://imslp.org/wiki/Category:Nielsen,_Carl",
    ],
}

def transform_all():
    """Run Saxon XSLT 3.0 on each MEI file; return list of (path, ttl)."""
    results = []
    with PySaxonProcessor(license=False) as proc:
        xp = proc.new_xslt30_processor()
        exe = xp.compile_stylesheet(stylesheet_file=XSLT)
        for f in DATA:
            ttl = exe.transform_to_string(source_file=f)
            base = os.path.splitext(os.path.basename(f))[0]
            with open(os.path.join(OUT, base + ".ttl"), "w", encoding="utf-8") as fh:
                fh.write(ttl)
            results.append((f, ttl))
    return results

def build_graph(transformed):
    g = Graph()
    for _, ttl in transformed:
        g.parse(data=ttl, format="turtle")
    return g

COMPOSER_TTL = os.path.join(OUT, "composer_reconciliation.ttl")

def add_reconciliation(g):
    """Attach verified external sameAs links to composer agents present in the
    graph. Agent IRIs depend on whether a record encodes a VIAF @codedval, which
    most of the full catalogue does not, so targets are resolved from the data."""
    FOAF = rdflib.Namespace("http://xmlns.com/foaf/0.1/")
    added = 0

    # Prefer links produced by reconcile.py --composers, which resolves every
    # composer agent live against Wikidata, MusicBrainz and VIAF and asserts
    # owl:sameAs only above its confidence threshold. The hardcoded RECON table
    # is the fallback for when that pass has not been run.
    if os.path.exists(COMPOSER_TTL):
        cg = Graph().parse(COMPOSER_TTL, format="turtle")
        before = len(g)
        g += cg
        added = sum(1 for _ in cg.triples((None, OWL.sameAs, None)))
        print(f"   merged {added} composer links from composer_reconciliation.ttl "
              f"({len(g) - before} triples)")
        return added
    agents = {o for _, _, o in g.triples((None, DCT.creator, None))
              if isinstance(o, rdflib.URIRef)}
    added = 0
    for a in sorted(agents, key=str):
        names = " ".join(str(n).lower() for n in g.objects(a, FOAF.name))
        for surname, uris in RECON.items():
            if surname in names:
                for uri in uris:
                    g.add((a, OWL.sameAs, rdflib.URIRef(uri)))
                    added += 1
    return added

# ---------- coverage / losslessness ----------
# Scholarly data points we expect a thematic-catalogue entry to carry, and the
# RDF predicate each should map to. Coverage = represented / present-in-source.
def coverage(transformed, g):
    """Field-level losslessness check.

    For every source field that is present in the MEI, confirm that a
    corresponding triple exists in the graph. Presence means the element
    carries an actual value, not merely that the element exists. the
    catalogue contains many empty <key/>, <tempo/> and <p/> shells, and
    counting those as losses understated coverage by several points.

    The work IRI is rebuilt here the same way the XSLT builds it, from the
    catalogue code plus number, so that all four DCM catalogues resolve.
    """
    CAT_CODES = ("CNW", "NWGW", "HartW", "SchW")
    rows = []
    for f, _ in transformed:
        tree = etree.parse(f)
        work = tree.find(f".//{MEI}work")
        present, mapped = 0, 0
        detail = {}

        def has_src(xpath):
            return work.xpath(xpath, namespaces={"m": MEI[1:-1]})

        def _slug(s):
            return re.sub(r'^_+|_+$', '', re.sub(r'[^a-z0-9]+', '_', (s or '').lower().strip()))

        def _idpart(s):
            return re.sub(r'^-+|-+$', '', re.sub(r'[^A-Za-z0-9]+', '-', (s or '').strip()))

        # Primary catalogue identifier: the first of the four known codes that
        # this record carries. Numbering restarts per catalogue, so the code is
        # part of the IRI.
        cat_el = None
        for code in CAT_CODES:
            found_el = has_src(f"m:identifier[normalize-space(@label)='{code}']")
            if found_el and (found_el[0].text or "").strip():
                cat_el = found_el[0]
                break
        cnw_num = (cat_el.text or "").strip() if cat_el is not None else None
        cat_code = (cat_el.get("label") or "").strip() if cat_el is not None else None

        if cnw_num:
            wuri = rdflib.URIRef(
                f"https://cnw-ld.org/work/{_idpart(cat_code)}{_idpart(cnw_num)}")
        else:
            _t = has_src("m:title[1]")
            xid = (work.get("{http://www.w3.org/XML/1998/namespace}id") or "")[:12]
            wuri = rdflib.URIRef(
                "https://cnw-ld.org/work/" + _slug("".join(_t[0].itertext())) + "_" + xid
            ) if _t else None

        checks = {
            "title":          ("m:title[not(@type='alternative')]", DCT.title),
            "alt_title":      ("m:title[@type='alternative']",      DCT.alternative),
            "identifiers":    ("m:identifier",                      DCT.identifier),
            "composer":       ("m:contributor/m:persName[@role='composer']", DCT.creator),
            "text_author":    ("m:contributor/m:persName[@role='author']",   CNW.textAuthor),
            "creation_date":  ("m:creation/m:date",                 DCT.created),
            "language":       ("m:langUsage/m:language",            DCT.language),
            "genre":          (".//m:classification//m:term",       DCT.subject),
            "key":            (".//m:expression/m:key[@pname]",     CNW.key),
            "tempo":          (".//m:expression/m:tempo[normalize-space(.)!='']", CNW.tempo),
            "meter":          (".//m:expression/m:meter[@count or @sym]", CNW.meter),
            "scoring":        (".//m:perfMedium//m:perfRes",        CNW.performingForce),
            "incipit_text":   (".//m:incip/m:incipText/m:p[normalize-space(.)!='']", CNW.incipitText),
            "relation":       ("m:relationList/m:relation[@rel='isPartOf']", DCT.isPartOf),
            "editorial_note":      (".//m:annot[normalize-space(.)!='']", CNW.editorialNote),
            "manuscript_location": (".//m:physLoc/m:repository",          CNW.manuscriptLocation),
        }
        for name, (xpath, pred) in checks.items():
            src = bool(has_src(xpath))
            if not src:
                detail[name] = "n/a"
                continue
            present += 1
            # represented if the work IRI (or its expression) has at least one such predicate
            found = False
            if wuri is not None:
                found = (wuri, pred, None) in g
                if not found:
                    # expression-level predicates
                    expr = rdflib.URIRef(str(wuri) + "/expression/1")
                    found = (expr, pred, None) in g
            detail[name] = "ok" if found else "MISSING"
            if found:
                mapped += 1
        rows.append({
            "file": os.path.basename(f), "cnw": cnw_num, "catalogue": cat_code,
            "present": present, "mapped": mapped,
            "coverage_pct": round(100 * mapped / present, 1) if present else None,
            "detail": detail,
        })
    return rows

# Source element types inside <work> that the prototype does NOT yet map
# (honest record of current losses).
UNMAPPED_NOTE = [
    "biblList/bibl (related documents: letters, diary entries)",
    "history/eventList/event sub-structure (only counted, not detailed)",
]

# ---------- competency questions ----------
CQ = {
 "CQ1  All works: CNW number, title (en), key  [cross-work listing]": """
   PREFIX dcterms: <http://purl.org/dc/terms/>
   PREFIX cnw: <https://cnw-ld.org/ontology#>
   PREFIX frbr: <http://purl.org/vocab/frbr/core#>
   SELECT ?cnw ?title ?key WHERE {
     ?w cnw:cnwNumber ?cnw ; dcterms:title ?title ; frbr:realization ?e .
     ?e cnw:key ?key . FILTER(lang(?title)="en")
   } ORDER BY ?cnw""",

 "CQ2  Works in D major  [cross-cutting filter impossible per-file]": """
   PREFIX dcterms: <http://purl.org/dc/terms/>
   PREFIX cnw: <https://cnw-ld.org/ontology#>
   PREFIX frbr: <http://purl.org/vocab/frbr/core#>
   SELECT ?cnw ?title WHERE {
     ?w cnw:cnwNumber ?cnw ; dcterms:title ?title ; frbr:realization ?e .
     ?e cnw:key "D major" . FILTER(lang(?title)="en")
   } ORDER BY ?cnw""",

 "CQ3  Works belonging to the same collection": """
   PREFIX dcterms: <http://purl.org/dc/terms/>
   PREFIX cnw: <https://cnw-ld.org/ontology#>
   SELECT ?cnw ?collection WHERE {
     ?w cnw:cnwNumber ?cnw ; dcterms:isPartOf ?collection .
   } ORDER BY ?cnw""",

 "CQ4  Composer external authority links  [reconciliation]": """
   PREFIX dcterms: <http://purl.org/dc/terms/>
   PREFIX owl: <http://www.w3.org/2002/07/owl#>
   PREFIX foaf: <http://xmlns.com/foaf/0.1/>
   SELECT DISTINCT ?name ?link WHERE {
     ?w dcterms:creator ?a . ?a foaf:name ?name ; owl:sameAs ?link .
   } ORDER BY ?link""",

 "CQ5  Incipit type per work: notated incipit vs renderable notation": """
   PREFIX dcterms: <http://purl.org/dc/terms/>
   PREFIX cnw: <https://cnw-ld.org/ontology#>
   PREFIX frbr: <http://purl.org/vocab/frbr/core#>
   SELECT ?cnw ?notatedIncipit ?renderableMusic WHERE {
     ?w cnw:cnwNumber ?cnw ; frbr:realization ?e .
     ?e cnw:hasNotatedIncipit ?notatedIncipit ; cnw:hasNotatedMusic ?renderableMusic .
   } ORDER BY ?cnw""",
}

def run_queries(g):
    out = {}
    for label, q in CQ.items():
        res = list(g.query(q))
        out[label] = [tuple(str(x) for x in row) for row in res]
    return out

def main():
    print("== 1. Transform (Saxon XSLT 3.0) ==")
    transformed = transform_all()
    print(f"   transformed {len(transformed)} MEI records")

    g = build_graph(transformed)
    print(f"   merged graph: {len(g)} triples (pre-reconciliation)")

    print("== 2. Reconciliation ==")
    n = add_reconciliation(g)
    print(f"   added {n} verified owl:sameAs links to composer")
    g.serialize(os.path.join(OUT, "cnw_combined.ttl"), format="turtle")
    print(f"   total graph: {len(g)} triples -> out/cnw_combined.ttl")

    print("== 3. SHACL validation ==")
    shapes = Graph().parse(os.path.join(HERE, "shapes", "cnw-shapes.ttl"), format="turtle")
    conforms, _, text = validate(g, shacl_graph=shapes, inference="none", abort_on_first=False)
    print(f"   conforms: {conforms}")
    viol = text.count("Constraint Violation")
    print(f"   constraint violations: {viol}")

    print("== 4. Coverage / losslessness ==")
    cov = coverage(transformed, g)
    tot_present = sum(r["present"] for r in cov)
    tot_mapped  = sum(r["mapped"]  for r in cov)
    overall = round(100 * tot_mapped / tot_present, 1)
    for r in cov:
        print(f"   {r['catalogue'] or '(no catalogue)'} {r['cnw'] or '-'}: "f"{r['mapped']}/{r['present']} data points = {r['coverage_pct']}%")
    print(f"   OVERALL field coverage: {tot_mapped}/{tot_present} = {overall}%")

    print("== 5. SPARQL competency questions ==")
    qres = run_queries(g)
    for label, rows in qres.items():
        print(f"\n   [{label}]  -> {len(rows)} rows")
        for row in rows:
            print("      " + " | ".join(row))

    # persist a machine-readable summary for the report
    summary = {
        "records": len(transformed),
        "triples_total": len(g),
        "shacl_conforms": bool(conforms),
        "shacl_violations": viol,
        "coverage_overall_pct": overall,
        "coverage_present": tot_present,
        "coverage_mapped": tot_mapped,
        "per_work": cov,
        "unmapped_source_elements": UNMAPPED_NOTE,
        "competency_questions": {k: v for k, v in qres.items()},
    }
    with open(os.path.join(OUT, "results_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    print(f"\n   wrote out/results_summary.json")

if __name__ == "__main__":
    main()
