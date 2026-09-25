#!/usr/bin/env python3
"""
scale_generator.py 
Usage:
    python3 scale_generator.py --factor 10 --out out/scaled_10x.ttl
    python3 scale_generator.py --all          # 1x,10x,100x,1000x
"""
import argparse
import os
import random
import time

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "out", "cnw_combined.ttl")
OUTDIR = os.path.join(HERE, "out", "scaled")

CNW = Namespace("https://cnw-ld.org/ontology#")
FRBR = Namespace("http://purl.org/vocab/frbr/core#")
BASE = "https://cnw-ld.org/"

# Observed distribution in the real CNW slice; preserved so selectivity is realistic.
KEYS = ["E major", "D major", "D major", "C major", "F major", "D major",
        "A minor", "B flat major", "G major", "E flat major"]
METERS = ["4/4", "3/4", "2/4", "6/8", "2/2", "4/4", "3/8"]
TEMPI = ["Allegro", "Andante", "Allegro moderato", "Adagio", "Vivace", "Largo"]


def load_template(g):
    """Extract every real work with its full triple neighbourhood."""
    works = []
    for w in set(g.subjects(RDF.type, FRBR.Work)):
        wt = list(g.predicate_objects(w))
        exprs = []
        for e in g.objects(w, FRBR.realization):
            exprs.append((e, list(g.predicate_objects(e))))
        works.append((w, wt, exprs))
    return works


def synthesise(g_src, factor, seed=42):
    """Return a new graph containing the original plus (factor-1) replications."""
    rng = random.Random(seed)
    out = Graph()
    for pfx, ns in g_src.namespaces():
        out.bind(pfx, ns)
    for t in g_src:
        out.add(t)                      # keep the real data intact

    template = load_template(g_src)
    if not template:
        raise SystemExit("No frbr:Work found in source graph.")

    n = 0
    for rep in range(1, factor):
        for (w, wt, exprs) in template:
            n += 1
            new_w = URIRef(f"{BASE}work/SYN{rep:05d}_{n:06d}")
            for p, o in wt:
                if p == FRBR.realization:
                    continue
                if p == CNW.cnwNumber:
                    o = Literal(f"S{rep:05d}-{n:06d}")
                out.add((new_w, p, o))
            for idx, (e, et) in enumerate(exprs, start=1):
                new_e = URIRef(f"{new_w}/expression/{idx}")
                out.add((new_w, FRBR.realization, new_e))
                for p, o in et:
                    if p == CNW.key:
                        o = Literal(rng.choice(KEYS))
                    elif p == CNW.meter:
                        o = Literal(rng.choice(METERS))
                    elif p == CNW.tempo:
                        o = Literal(rng.choice(TEMPI))
                    out.add((new_e, p, o))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--factor", type=int, default=10)
    ap.add_argument("--all", action="store_true", help="generate 1x,10x,100x,1000x")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    os.makedirs(OUTDIR, exist_ok=True)
    g = Graph().parse(SRC, format="turtle")
    base_works = len(set(g.subjects(RDF.type, FRBR.Work)))
    print(f"source: {len(g)} triples, {base_works} works")

    factors = [1, 10, 100, 1000] if args.all else [args.factor]
    manifest = []
    for f in factors:
        t0 = time.time()
        out = g if f == 1 else synthesise(g, f)
        path = args.out or os.path.join(OUTDIR, f"scaled_{f}x.ttl")
        out.serialize(destination=path, format="turtle")
        works = len(set(out.subjects(RDF.type, FRBR.Work)))
        manifest.append({"factor": f, "triples": len(out), "works": works, "path": path})
        print(f"  {f:5}x -> {len(out):9,} triples, {works:7,} works "
              f"({time.time()-t0:.1f}s) -> {os.path.basename(path)}")

    import json
    json.dump(manifest, open(os.path.join(OUTDIR, "manifest.json"), "w"), indent=2)
    print("wrote manifest.json")


if __name__ == "__main__":
    main()
