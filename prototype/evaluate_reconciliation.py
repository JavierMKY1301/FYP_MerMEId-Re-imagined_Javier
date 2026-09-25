#!/usr/bin/env python3
"""
evaluate_reconciliation.py - precision / recall / F1 for work-level reconciliation.

Compares the links the pipeline produced (out/reconciliation.ttl) against a
manually verified gold standard (gold/reconciliation_gold.csv), reporting per
source and overall. This operationalises the "manually verified gold-standard
set" that the design chapter commits to for RQ3.

The gold set MUST contain hard negatives (plausible but wrong targets), or
precision is trivially 1.0 and the metric is meaningless.

Usage:
    python3 evaluate_reconciliation.py
"""
import csv
import json
import os
from collections import defaultdict

from rdflib import Graph, Namespace

HERE = os.path.dirname(os.path.abspath(__file__))
TTL = os.path.join(HERE, "out", "reconciliation.ttl")
GOLD = os.path.join(HERE, "gold", "reconciliation_gold.csv")
SUMMARY = os.path.join(HERE, "out", "reconciliation_eval.json")

CNW = Namespace("https://cnw-ld.org/ontology#")


def load_predicted():
    """Set of (work_iri, target_id) the system asserted, plus their source."""
    if not os.path.exists(TTL):
        raise SystemExit("No reconciliation.ttl - run reconcile.py first.")
    g = Graph().parse(TTL, format="turtle")
    pred, src = set(), {}
    for s, _, o in g.triples((None, CNW.reconciledTo, None)):
        pred.add((str(s), str(o)))
    for t, _, o in g.triples((None, CNW.matchSource, None)):
        src[str(t)] = str(o)
    return pred, src


def load_gold():
    """(work_iri, target_id) -> is_match (bool), plus source per row."""
    if not os.path.exists(GOLD):
        raise SystemExit(f"No gold file at {GOLD} - see gold/README for the format.")
    gold, gsrc = {}, {}
    with open(GOLD, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not row.get("work_iri") or not row.get("target_id"):
                continue
            key = (row["work_iri"].strip(), row["target_id"].strip())
            gold[key] = str(row.get("is_match", "")).strip().lower() in ("true", "1", "yes")
            gsrc[key] = row.get("source", "").strip()
    return gold, gsrc


def prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def main():
    pred, psrc = load_predicted()
    gold, gsrc = load_gold()

    buckets = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    # True/false positives: everything the system asserted.
    for key in pred:
        source = psrc.get(key[1]) or gsrc.get(key) or "unknown"
        if gold.get(key) is True:
            buckets[source]["tp"] += 1
        else:
            # Either gold says it's wrong (hard negative) or it isn't in gold.
            buckets[source]["fp"] += 1

    # False negatives: true links in gold the system failed to assert.
    for key, is_match in gold.items():
        if is_match and key not in pred:
            buckets[gsrc.get(key, "unknown")]["fn"] += 1

    print("== Reconciliation evaluation ==")
    print(f"{'source':14} {'TP':>4} {'FP':>4} {'FN':>4}  {'P':>6} {'R':>6} {'F1':>6}")
    out = {}
    tot = {"tp": 0, "fp": 0, "fn": 0}
    for source in sorted(buckets):
        b = buckets[source]
        p, r, f = prf(b["tp"], b["fp"], b["fn"])
        out[source] = {**b, "precision": p, "recall": r, "f1": f}
        print(f"{source:14} {b['tp']:4} {b['fp']:4} {b['fn']:4}  {p:6} {r:6} {f:6}")
        for k in tot:
            tot[k] += b[k]

    p, r, f = prf(tot["tp"], tot["fp"], tot["fn"])
    out["OVERALL"] = {**tot, "precision": p, "recall": r, "f1": f}
    print(f"{'OVERALL':14} {tot['tp']:4} {tot['fp']:4} {tot['fn']:4}  {p:6} {r:6} {f:6}")

    n_neg = sum(1 for v in gold.values() if not v)
    print(f"\ngold rows: {len(gold)} ({n_neg} hard negatives)")
    if n_neg == 0:
        print("WARNING: no hard negatives in the gold set - precision is not meaningful.")

    json.dump(out, open(SUMMARY, "w"), indent=2)
    print("wrote", SUMMARY)


if __name__ == "__main__":
    main()
