#!/usr/bin/env python3
"""
load_fuseki.py - load the transformed RDF into Apache Jena Fuseki and verify.

This closes the gap between the prototype (in-process rdflib) and the design's
committed Expose layer (Fuseki). Because SPARQL is engine-agnostic, the SAME
competency questions from run_pipeline.py are re-run against Fuseki here; if the
results match, the engine substitution is evidenced rather than asserted.

Usage:
    docker compose up -d          # start Fuseki first
    python3 load_fuseki.py
"""
import os
import sys
import json
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
TTL = os.path.join(HERE, "out", "cnw_combined.ttl")

FUSEKI = os.environ.get("FUSEKI_URL", "http://localhost:3030")
DATASET = os.environ.get("FUSEKI_DATASET", "cnw")
USER = os.environ.get("FUSEKI_USER", "admin")
PASSWORD = os.environ.get("FUSEKI_PASSWORD", "cnwadmin")

DATA_URL = f"{FUSEKI}/{DATASET}/data"
QUERY_URL = f"{FUSEKI}/{DATASET}/query"

# The same five competency questions used in run_pipeline.py.
PREFIXES = """
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX cnw:     <https://cnw-ld.org/ontology#>
PREFIX frbr:    <http://purl.org/vocab/frbr/core#>
PREFIX foaf:    <http://xmlns.com/foaf/0.1/>
PREFIX owl:     <http://www.w3.org/2002/07/owl#>
"""

CQ = {
    "CQ1 All works: CNW number, title (en), key": PREFIXES + """
        SELECT ?cnw ?title ?key WHERE {
          ?w cnw:cnwNumber ?cnw ; dcterms:title ?title ; frbr:realization ?e .
          ?e cnw:key ?key . FILTER(lang(?title)="en")
        } ORDER BY ?cnw""",
    "CQ2 Works in D major [cross-cutting]": PREFIXES + """
        SELECT ?cnw ?title WHERE {
          ?w cnw:cnwNumber ?cnw ; dcterms:title ?title ; frbr:realization ?e .
          ?e cnw:key "D major" . FILTER(lang(?title)="en")
        } ORDER BY ?cnw""",
    "CQ3 Works in the same collection": PREFIXES + """
        SELECT ?cnw ?collection WHERE {
          ?w cnw:cnwNumber ?cnw ; dcterms:isPartOf ?collection .
        } ORDER BY ?cnw""",
    "CQ4 Composer external authority links": PREFIXES + """
        SELECT ?name ?ext WHERE {
          ?a a foaf:Agent ; foaf:name ?name ; owl:sameAs ?ext .
        } ORDER BY ?ext""",
    "CQ5 Incipit type per work": PREFIXES + """
        SELECT ?cnw ?ni ?nm WHERE {
          ?w cnw:cnwNumber ?cnw ; frbr:realization ?e .
          ?e cnw:hasNotatedIncipit ?ni ; cnw:hasNotatedMusic ?nm .
        } ORDER BY ?cnw""",
}


def wait_for_fuseki(timeout=60):
    """Fuseki takes a few seconds to come up after `docker compose up`."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(f"{FUSEKI}/$/ping", timeout=3)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def load():
    """Upload the Turtle file into the dataset's default graph."""
    with open(TTL, "rb") as fh:
        data = fh.read()
    r = httpx.post(
        DATA_URL,
        content=data,
        headers={"Content-Type": "text/turtle;charset=utf-8"},
        auth=(USER, PASSWORD),
        timeout=60,
    )
    r.raise_for_status()
    print(f"   loaded {len(data)} bytes -> {DATA_URL}")


def count_triples():
    r = httpx.post(QUERY_URL,
                   data={"query": "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"},
                   headers={"Accept": "application/sparql-results+json"},
                   timeout=30)
    r.raise_for_status()
    return int(r.json()["results"]["bindings"][0]["n"]["value"])


def run_query(q):
    r = httpx.post(QUERY_URL, data={"query": q},
                   headers={"Accept": "application/sparql-results+json"},
                   timeout=30)
    r.raise_for_status()
    res = r.json()
    cols = res["head"]["vars"]
    return [[b.get(c, {}).get("value", "") for c in cols] for b in res["results"]["bindings"]]


def main():
    print("== Fuseki load ==")
    if not wait_for_fuseki():
        sys.exit("Fuseki not reachable at %s - run `docker compose up -d` first." % FUSEKI)
    load()
    n = count_triples()
    print(f"   dataset '{DATASET}' now holds {n} triples")

    print("== Competency questions re-run against Fuseki ==")
    summary = {"engine": "fuseki", "triples": n, "results": {}}
    for name, q in CQ.items():
        rows = run_query(q)
        summary["results"][name] = rows
        print(f"   [{name}] -> {len(rows)} rows")
        for row in rows[:4]:
            print("      " + " | ".join(row))
        if len(rows) > 4:
            print(f"      ... and {len(rows)-4} more")

    out = os.path.join(HERE, "out", "fuseki_results.json")
    json.dump(summary, open(out, "w"), indent=2, ensure_ascii=False)
    print("   wrote", out)
    print("\nCompare with out/results_summary.json - identical rows demonstrate that "
          "the SPARQL is engine-agnostic, as claimed in the design.")


if __name__ == "__main__":
    main()
