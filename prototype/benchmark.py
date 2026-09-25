#!/usr/bin/env python3
"""
benchmark.py - SPARQL latency across triple volumes, with statistical treatment.

Why this exists
---------------
Two pieces of feedback drive this module:
  (a) "query performance implications of the expected triple store size are not
       addressed" (peer review), and
  (b) "unclear expectation curve for the bigger and more complex datasets ...
       statistically worked through" (preliminary report feedback).

A single timing number answers neither. This benchmark therefore:
  * runs each query R times after W discarded warm-up runs;
  * reports median, mean, standard deviation, p95 and a 95% confidence interval
    (Student t, so small R is handled correctly);
  * repeats the whole battery at several graph magnitudes; and
  * fits a log-log regression per query to estimate the SCALING EXPONENT k in
    t ~ n^k, which is what actually characterises the expectation curve:
        k ~ 0  constant (index-backed lookup)
        k ~ 1  linear (full scan)
        k > 1  super-linear (a scaling risk to design around)

Engines: in-process rdflib always; Apache Jena Fuseki additionally when it is
running, so the two can be compared on identical SPARQL.

Usage:
    python3 benchmark.py                      # rdflib, factors 1,10,100
    python3 benchmark.py --factors 1 10 100 1000 --reps 30
    python3 benchmark.py --fuseki             # include Fuseki (must be loaded)
"""
import argparse
import csv
import json
import math
import os
import statistics as st
import time

from rdflib import Graph
from rdflib.namespace import RDF

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "out", "cnw_combined.ttl")
OUT_CSV = os.path.join(HERE, "out", "benchmark.csv")
OUT_JSON = os.path.join(HERE, "out", "benchmark_summary.json")
FUSEKI_QUERY_URL = os.environ.get("FUSEKI_QUERY_URL", "http://localhost:3030/cnw/query")

PREFIXES = """
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX cnw:     <https://cnw-ld.org/ontology#>
PREFIX frbr:    <http://purl.org/vocab/frbr/core#>
PREFIX foaf:    <http://xmlns.com/foaf/0.1/>
PREFIX owl:     <http://www.w3.org/2002/07/owl#>
"""

# Each query probes a different access pattern, so the exponents are comparable.
QUERIES = {
    "Q1_point_lookup": PREFIXES + """
        SELECT ?title WHERE { ?w cnw:cnwNumber "129" ; dcterms:title ?title }""",
    "Q2_selective_filter": PREFIXES + """
        SELECT ?cnw ?title WHERE {
          ?w cnw:cnwNumber ?cnw ; dcterms:title ?title ; frbr:realization ?e .
          ?e cnw:key "D major" . FILTER(lang(?title)="en") }""",
    "Q3_full_listing": PREFIXES + """
        SELECT ?cnw ?title ?key WHERE {
          ?w cnw:cnwNumber ?cnw ; dcterms:title ?title ; frbr:realization ?e .
          ?e cnw:key ?key . FILTER(lang(?title)="en") }""",
    "Q4_aggregate": PREFIXES + """
        SELECT ?key (COUNT(?w) AS ?n) WHERE {
          ?w frbr:realization ?e . ?e cnw:key ?key } GROUP BY ?key""",
    "Q5_join_incipit_page": PREFIXES + """
        SELECT ?cnw ?title ?inc WHERE {
          ?w cnw:cnwNumber ?cnw ; dcterms:title ?title ; frbr:realization ?e .
          ?e cnw:hasNotatedMusic true . OPTIONAL { ?e cnw:incipitText ?inc }
          FILTER(lang(?title)="en") }""",
}

T_CRIT = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 9: 2.262, 14: 2.145,
          19: 2.093, 29: 2.045, 49: 2.010, 99: 1.984}


def t_crit(df):
    for k in sorted(T_CRIT):
        if df <= k:
            return T_CRIT[k]
    return 1.96


def describe(samples):
    """Return the full statistical summary for one set of timings (ms)."""
    n = len(samples)
    mean = st.mean(samples)
    sd = st.stdev(samples) if n > 1 else 0.0
    ci = t_crit(n - 1) * sd / math.sqrt(n) if n > 1 else 0.0
    srt = sorted(samples)
    p95 = srt[min(n - 1, int(math.ceil(0.95 * n)) - 1)]
    return {"n": n, "median_ms": round(st.median(samples), 3),
            "mean_ms": round(mean, 3), "sd_ms": round(sd, 3),
            "ci95_ms": round(ci, 3), "p95_ms": round(p95, 3),
            "min_ms": round(min(samples), 3), "max_ms": round(max(samples), 3),
            "cv_pct": round(100 * sd / mean, 1) if mean else 0.0}


# ---------------------------------------------------------------- engines
class RdflibEngine:
    name = "rdflib"

    def __init__(self, graph):
        self.g = graph

    def run(self, q):
        t0 = time.perf_counter()
        n = len(list(self.g.query(q)))
        return (time.perf_counter() - t0) * 1000.0, n


class FusekiEngine:
    name = "fuseki"

    def __init__(self, url):
        import httpx
        self.httpx = httpx
        self.url = url

    def run(self, q):
        t0 = time.perf_counter()
        r = self.httpx.post(self.url, data={"query": q},
                            headers={"Accept": "application/sparql-results+json"},
                            timeout=120)
        r.raise_for_status()
        n = len(r.json()["results"]["bindings"])
        return (time.perf_counter() - t0) * 1000.0, n


def scale_in_memory(g, factor, seed=42):
    """Replicate real work structure into fresh IRIs, entirely in memory."""
    if factor == 1:
        return g
    import random
    from rdflib import Literal, Namespace, URIRef
    CNW = Namespace("https://cnw-ld.org/ontology#")
    FRBR = Namespace("http://purl.org/vocab/frbr/core#")
    KEYS = ["E major", "D major", "D major", "C major", "F major",
            "A minor", "G major", "B flat major"]
    rng = random.Random(seed)
    out = Graph()
    for t in g:
        out.add(t)
    tmpl = []
    for w in set(g.subjects(RDF.type, FRBR.Work)):
        tmpl.append((list(g.predicate_objects(w)),
                     [(e, list(g.predicate_objects(e)))
                      for e in g.objects(w, FRBR.realization)]))
    n = 0
    for rep in range(1, factor):
        for wt, exprs in tmpl:
            n += 1
            nw = URIRef(f"https://cnw-ld.org/work/SYN{rep:05d}_{n:06d}")
            for p, o in wt:
                if p == FRBR.realization:
                    continue
                if p == CNW.cnwNumber:
                    o = Literal(f"S{rep:05d}-{n:06d}")
                out.add((nw, p, o))
            for i, (e, et) in enumerate(exprs, 1):
                ne = URIRef(f"{nw}/expression/{i}")
                out.add((nw, FRBR.realization, ne))
                for p, o in et:
                    if p == CNW.key:
                        o = Literal(rng.choice(KEYS))
                    out.add((ne, p, o))
    return out


def loglog_slope(xs, ys):
    """Least-squares slope of log(y) on log(x): the scaling exponent k."""
    pts = [(math.log10(x), math.log10(y)) for x, y in zip(xs, ys) if x > 0 and y > 0]
    if len(pts) < 2:
        return None, None
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    num = sum((p[0] - mx) * (p[1] - my) for p in pts)
    den = sum((p[0] - mx) ** 2 for p in pts)
    if den == 0:
        return None, None
    k = num / den
    ss_res = sum((p[1] - (my + k * (p[0] - mx))) ** 2 for p in pts)
    ss_tot = sum((p[1] - my) ** 2 for p in pts)
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    return round(k, 3), round(r2, 3)


def interpret(k):
    if k is None:
        return "insufficient data"
    if k < 0.25:
        return "near-constant"
    if k < 0.75:
        return "sub-linear"
    if k < 1.25:
        return "linear"
    return "super-linear (scaling risk)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--factors", type=int, nargs="+", default=[1, 10, 100])
    ap.add_argument("--reps", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--fuseki", action="store_true")
    args = ap.parse_args()

    base = Graph().parse(SRC, format="turtle")
    rows, sizes = [], {}

    engines = []
    for f in args.factors:
        print(f"== scaling to {f}x ==")
        g = scale_in_memory(base, f)
        sizes[f] = len(g)
        print(f"   {len(g):,} triples")
        engines = [RdflibEngine(g)]
        if args.fuseki:
            try:
                engines.append(FusekiEngine(FUSEKI_QUERY_URL))
                print("   (Fuseki included - ensure the matching graph is loaded)")
            except Exception as e:
                print("   ! Fuseki unavailable:", e)

        for eng in engines:
            for qname, q in QUERIES.items():
                for _ in range(args.warmup):
                    try:
                        eng.run(q)
                    except Exception:
                        pass
                samples, nres = [], 0
                for _ in range(args.reps):
                    ms, nres = eng.run(q)
                    samples.append(ms)
                s = describe(samples)
                rows.append({"engine": eng.name, "factor": f, "triples": len(g),
                             "query": qname, "results": nres, **s})
                print(f"   {eng.name:8} {qname:22} "
                      f"median={s['median_ms']:8.2f}ms  p95={s['p95_ms']:8.2f}  "
                      f"CI95=+/-{s['ci95_ms']:.2f}  CV={s['cv_pct']}%")

    with open(OUT_CSV, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader(); wr.writerows(rows)

    # scaling exponents per engine+query
    print("\n== scaling analysis:  t ~ n^k ==")
    print(f"{'engine':9} {'query':22} {'k':>7} {'R^2':>7}  interpretation")
    analysis = {}
    for eng in sorted({r["engine"] for r in rows}):
        for qname in QUERIES:
            pts = [(r["triples"], r["median_ms"]) for r in rows
                   if r["engine"] == eng and r["query"] == qname]
            pts.sort()
            k, r2 = loglog_slope([p[0] for p in pts], [p[1] for p in pts])
            analysis[f"{eng}:{qname}"] = {"k": k, "r2": r2, "interpretation": interpret(k)}
            print(f"{eng:9} {qname:22} {str(k):>7} {str(r2):>7}  {interpret(k)}")

    json.dump({"sizes": sizes, "rows": rows, "scaling": analysis,
               "config": {"reps": args.reps, "warmup": args.warmup}},
              open(OUT_JSON, "w"), indent=2)
    print(f"\nwrote {OUT_CSV} and {OUT_JSON}")


if __name__ == "__main__":
    main()
