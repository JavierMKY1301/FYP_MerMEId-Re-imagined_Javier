#!/usr/bin/env python3
"""
edge_case_matrix.py - systematic edge-case taxonomy and coverage matrix.

Why this exists
---------------
Edge cases were flagged in BOTH review rounds ("special focus should be given to
edge cases"). The preliminary report listed edge cases anecdotally - as things
that happened to be noticed. That is not a method.

This module makes edge-case handling systematic:
  1. A declared TAXONOMY of irregularity categories that a thematic-catalogue
     transformation must survive, derived from the MEI profile rather than from
     whatever the sample happened to contain.
  2. Automatic detection of which category each real record exercises.
  3. An explicit UNCOVERED list - categories the corpus does NOT exercise, which
     is exactly the "unclear expectation curve" the feedback identified. Naming
     untested categories is more defensible than implying full coverage.
  4. A per-category handling verdict: HANDLED / DEGRADED / UNHANDLED / UNTESTED.

Usage:
    python3 edge_case_matrix.py
    python3 edge_case_matrix.py --markdown     # table for the report
"""
import argparse
import json
import os

from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "out", "edge_case_matrix.json")
MEI = "http://www.music-encoding.org/ns/mei"
NS = {"m": MEI}

# --------------------------------------------------------------------------
# The taxonomy. Each entry: detector xpath/predicate + how the pipeline copes.
# 'status' is the DESIGNED verdict, verified by tests/test_pipeline.py.
# --------------------------------------------------------------------------
TAXONOMY = [
    dict(id="E01", category="Meter as @count/@unit",
         detect=lambda t: bool(t.xpath("//m:meter[@count]", namespaces=NS)),
         status="HANDLED", note="Mapped directly to 'count/unit'."),
    dict(id="E02", category="Meter as @sym (common/cut)",
         detect=lambda t: bool(t.xpath("//m:meter[@sym]", namespaces=NS)),
         status="HANDLED", note="common->4/4, cut->2/2. Silently dropped before the fix."),
    dict(id="E03", category="Meter absent entirely",
         detect=lambda t: not t.xpath("//m:meter", namespaces=NS),
         status="HANDLED", note="Field omitted; no empty literal emitted."),
    dict(id="E04", category="No CNW catalogue number",
         detect=lambda t: not _txt(t, "//m:work/m:identifier[@label='CNW']"),
         status="DEGRADED", note="Falls back to title-slug IRI; fails the CNW SHACL shape."),
    dict(id="E05", category="Non-integer catalogue value (range)",
         detect=lambda t: not (_txt(t, "//m:work/m:identifier[@label='CNW']") or "0").isdigit(),
         status="HANDLED", note="Ordering must avoid xsd:integer casts."),
    dict(id="E06", category="Opus absent",
         detect=lambda t: not _txt(t, "//m:work/m:identifier[@label='Opus']"),
         status="HANDLED", note="Tolerated without failure."),
    dict(id="E07", category="Opus with irregular spacing",
         detect=lambda t: "  " in (_txt(t, "//m:work/m:identifier[@label='Opus']") or "")
                          or (_txt(t, "//m:work/m:identifier[@label='Opus']") or "") !=
                             (_txt(t, "//m:work/m:identifier[@label='Opus']") or "").strip(),
         status="HANDLED", note="Normalised on output."),
    dict(id="E08", category="Multiple expressions per work",
         detect=lambda t: len(t.xpath("//m:work//m:expression", namespaces=NS)) > 2,
         status="DEGRADED", note="Only the first expression is mapped (known limitation)."),
    dict(id="E09", category="Renderable notation present (<score> + <body>)",
         detect=lambda t: bool(t.xpath("//m:score", namespaces=NS))
                          and bool(t.xpath("//m:body", namespaces=NS)),
         status="HANDLED", note="Flagged cnw:hasNotatedMusic; Verovio renders it."),
    dict(id="E10", category="<score> present but no <body> (unrenderable)",
         detect=lambda t: bool(t.xpath("//m:score", namespaces=NS))
                          and not t.xpath("//m:body", namespaces=NS),
         status="HANDLED", note="Detected during bulk render; skipped without aborting."),
    dict(id="E11", category="Text incipit with image pointer only",
         detect=lambda t: bool(t.xpath("//m:incip//m:graphic", namespaces=NS)),
         status="HANDLED", note="Image reference captured; not engraved."),
    dict(id="E12", category="Editorial annotation inside <work>",
         detect=lambda t: bool(t.xpath("//m:work//m:annot[normalize-space(.)!='']",
                                       namespaces=NS)),
         status="HANDLED", note="Mapped to cnw:editorialNote; nested <rend> flattened."),
    dict(id="E13", category="Source description outside <work>",
         detect=lambda t: bool(t.xpath("//m:annot[@type='source_description']",
                                       namespaces=NS)),
         status="DEGRADED", note="Present in source; work-scoped selector may miss it."),
    dict(id="E14", category="Manuscript location (RISM siglum)",
         detect=lambda t: bool(t.xpath("//m:physLoc/m:repository", namespaces=NS)),
         status="DEGRADED", note="Emitted as raw siglum; not resolved to an institution."),
    dict(id="E15", category="Bracketed / uncertain composer name",
         detect=lambda t: any("[" in (e.text or "") for e in
                              t.xpath("//m:persName[@role='composer']", namespaces=NS)),
         status="DEGRADED", note="Creates a second agent node; identity resolution needed."),
    dict(id="E16", category="Composer without authority identifier",
         detect=lambda t: any(not e.get("codedval") for e in
                              t.xpath("//m:persName[@role='composer']", namespaces=NS)),
         status="DEGRADED", note="No VIAF IRI; agent keyed on name slug instead."),
    dict(id="E17", category="Multiple titles in the same language",
         detect=lambda t: _multi_same_lang(t),
         status="DEGRADED", note="Arbitrary title reaches the matcher; affects reconciliation."),
    dict(id="E18", category="Relations to other works (isPartOf)",
         detect=lambda t: bool(t.xpath("//m:relationList/m:relation[@rel='isPartOf']",
                                       namespaces=NS)),
         status="HANDLED", note="Mapped to dcterms:isPartOf."),
    dict(id="E19", category="Performance events recorded",
         detect=lambda t: bool(t.xpath("//m:eventList//m:event", namespaces=NS)),
         status="DEGRADED", note="Counted only; internal detail unmapped."),
    dict(id="E20", category="Related bibliography (biblList)",
         detect=lambda t: bool(t.xpath("//m:biblList//m:bibl", namespaces=NS)),
         status="UNHANDLED", note="Deliberately out of scope for the current model."),
    dict(id="E21", category="Non-Latin / diacritic-heavy titles",
         detect=lambda t: any(any(ord(c) > 127 for c in ("".join(e.itertext())))
                              for e in t.xpath("//m:work/m:title", namespaces=NS)),
         status="HANDLED", note="UTF-8 preserved; affects string-similarity matching."),
    dict(id="E22", category="Work from a non-CNW catalogue",
         detect=lambda t: bool(t.xpath("//m:work/m:identifier[@label='Demo']", namespaces=NS))
                          and not _txt(t, "//m:work/m:identifier[@label='CNW']"),
         status="DEGRADED", note="Exposes CNW-specific assumptions in shapes and IRIs."),
    # Declared but NOT present in the openly available corpus:
    dict(id="E23", category="Empty <work> element", detect=lambda t: False,
         status="UNTESTED", note="No such record available; behaviour unverified."),
    dict(id="E24", category="Malformed / invalid MEI", detect=lambda t: False,
         status="UNTESTED", note="Would fail at parse; no fixture available."),
    dict(id="E25", category="Duplicate catalogue numbers across records",
         detect=lambda t: False, status="UNTESTED",
         note="Would collide on work IRI; not exercised by the corpus."),
]


def _txt(tree, xpath):
    r = tree.xpath(xpath, namespaces=NS)
    return (r[0].text or "").strip() if r and r[0].text else ""


def _multi_same_lang(tree):
    langs = [e.get("{http://www.w3.org/XML/1998/namespace}lang")
             for e in tree.xpath("//m:work/m:title", namespaces=NS)]
    langs = [l for l in langs if l]
    return len(langs) != len(set(langs))


def analyse():
    files = sorted(f for f in os.listdir(DATA) if f.endswith(".xml"))
    matrix, per_file = {}, {}
    trees = {f: etree.parse(os.path.join(DATA, f)) for f in files}

    for entry in TAXONOMY:
        hits = []
        for f, t in trees.items():
            try:
                if entry["detect"](t):
                    hits.append(f)
            except Exception:
                pass
        matrix[entry["id"]] = {"category": entry["category"], "status": entry["status"],
                               "note": entry["note"], "records": hits, "count": len(hits)}
        for f in hits:
            per_file.setdefault(f, []).append(entry["id"])
    return matrix, per_file, files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    matrix, per_file, files = analyse()
    covered = [k for k, v in matrix.items() if v["count"] > 0]
    uncovered = [k for k, v in matrix.items() if v["count"] == 0]

    if args.markdown:
        print("| ID | Category | Status | Records | Note |")
        print("|---|---|---|---|---|")
        for k, v in matrix.items():
            print(f"| {k} | {v['category']} | {v['status']} | {v['count']} | {v['note']} |")
    else:
        print("== Edge-case coverage matrix ==")
        print(f"   corpus: {len(files)} records; taxonomy: {len(TAXONOMY)} categories")
        print(f"   exercised by the corpus : {len(covered)}")
        print(f"   NOT exercised (untested): {len(uncovered)}  -> {', '.join(uncovered)}")
        print()
        for k, v in matrix.items():
            flag = " " if v["count"] else "!"
            print(f" {flag}{k} {v['status']:10} n={v['count']:2}  {v['category']}")
        print()
        by_status = {}
        for v in matrix.values():
            by_status[v["status"]] = by_status.get(v["status"], 0) + 1
        print("   verdicts:", ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())))

    json.dump({"corpus": files, "matrix": matrix, "per_file": per_file,
               "covered": covered, "uncovered": uncovered},
              open(OUT, "w"), indent=2)
    if not args.markdown:
        print("   wrote", OUT)


if __name__ == "__main__":
    main()
