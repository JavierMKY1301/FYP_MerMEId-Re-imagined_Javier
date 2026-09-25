#!/usr/bin/env python3
"""
make_gold_template.py - generate the gold-standard CSV from the last run.

The gold standard is the manually verified ground truth used to compute
precision and recall for work-level reconciliation (RQ3). Hand-typing external
identifiers is error-prone, so this script pre-fills every link the system
proposed - with its REAL target IRI - and leaves you two jobs:

    1. VERIFY each pre-filled row by opening its target IRI. If the target is
       genuinely the same work, leave is_match=true. If not, change it to false.
    2. ADD false negatives: true matches the system MISSED. Search the authority
       by hand; if the work exists there, add a row with is_match=true. Without
       these, recall is trivially 1.0 and says nothing.

Hard negatives (plausible but wrong targets) are added automatically from the
review queue when available, and can be supplemented by hand.

Usage:
    python3 make_gold_template.py
    python3 make_gold_template.py --out gold/reconciliation_gold.csv --force
"""
import argparse
import csv
import os

from rdflib import Graph, Namespace
from rdflib.namespace import RDFS

HERE = os.path.dirname(os.path.abspath(__file__))
TTL = os.path.join(HERE, "out", "reconciliation.ttl")
QUEUE = os.path.join(HERE, "out", "reconciliation_review_queue.csv")
COMBINED = os.path.join(HERE, "out", "cnw_combined.ttl")
DEFAULT_OUT = os.path.join(HERE, "gold", "reconciliation_gold.csv")

CNW = Namespace("https://cnw-ld.org/ontology#")
DCTERMS = Namespace("http://purl.org/dc/terms/")

FIELDS = ["cnw", "work_iri", "title", "source", "target_id",
          "target_label", "is_match", "note"]


def work_titles():
    """Map work IRI -> a readable title, for the human filling in the sheet."""
    if not os.path.exists(COMBINED):
        return {}
    g = Graph().parse(COMBINED, format="turtle")
    out = {}
    for s, _, o in g.triples((None, DCTERMS.title, None)):
        out.setdefault(str(s), str(o))
    return out


def cnw_numbers():
    if not os.path.exists(COMBINED):
        return {}
    g = Graph().parse(COMBINED, format="turtle")
    return {str(s): str(o) for s, _, o in g.triples((None, CNW.cnwNumber, None))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing gold file")
    args = ap.parse_args()

    if not os.path.exists(TTL):
        raise SystemExit("No out/reconciliation.ttl - run reconcile.py first.")
    if os.path.exists(args.out) and not args.force:
        raise SystemExit(f"{args.out} exists. Re-run with --force to overwrite "
                         f"(back it up first if you have already verified rows).")

    g = Graph().parse(TTL, format="turtle")
    titles, numbers = work_titles(), cnw_numbers()

    labels, sources = {}, {}
    for t, _, o in g.triples((None, RDFS.label, None)):
        labels[str(t)] = str(o)
    for t, _, o in g.triples((None, CNW.matchSource, None)):
        sources[str(t)] = str(o)

    rows = []
    for s, _, o in g.triples((None, CNW.reconciledTo, None)):
        w, t = str(s), str(o)
        rows.append({
            "cnw": numbers.get(w, ""),
            "work_iri": w,
            "title": titles.get(w, ""),
            "source": sources.get(t, ""),
            "target_id": t,
            "target_label": labels.get(t, ""),
            "is_match": "true",
            "note": "VERIFY: open target_id and confirm it is the same work",
        })
    rows.sort(key=lambda r: (r["cnw"], r["source"]))
    n_auto = len(rows)

    # Hard negatives from the review queue, if any survived the threshold cut.
    n_queue = 0
    if os.path.exists(QUEUE):
        with open(QUEUE, encoding="utf-8") as fh:
            for q in csv.DictReader(fh):
                if not q.get("target_id"):
                    continue
                rows.append({
                    "cnw": q.get("cnw", ""), "work_iri": q.get("work_iri", ""),
                    "title": q.get("title", ""), "source": q.get("source", ""),
                    "target_id": q.get("target_id", ""),
                    "target_label": q.get("target_label", ""),
                    "is_match": "false",
                    "note": f"below threshold (conf={q.get('confidence','')}) "
                            f"- VERIFY: set true if it really is the same work",
                })
                n_queue += 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=FIELDS)
        wr.writeheader()
        wr.writerows(rows)

    print(f"wrote {args.out}")
    print(f"  {n_auto} accepted link(s) pre-filled as is_match=true  <- VERIFY EACH")
    print(f"  {n_queue} below-threshold candidate(s) as is_match=false")
    print()
    print("NOW DO THIS BY HAND:")
    print("  1. Open each target_id in a browser and confirm the match.")
    print("     Wrong? change is_match to false and say why in note.")
    print("  2. Add HARD NEGATIVES: plausible but wrong targets, is_match=false.")
    print("     Without them precision is trivially 1.0 and means nothing.")
    print("  3. Add FALSE NEGATIVES: true matches the system missed,")
    print("     is_match=true. Without them recall is trivially 1.0.")
    print()
    print("Then: python3 evaluate_reconciliation.py")


if __name__ == "__main__":
    main()
