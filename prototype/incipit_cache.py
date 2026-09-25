#!/usr/bin/env python3
"""
incipit_cache.py - lazy + cached Verovio rendering, with a scaling measurement.

Why this exists
---------------
The literature review flagged Verovio's cost at scale (Section 2.3) and peer
feedback repeated it ("Verovio is hard to scale"). The preliminary report could
only say the concern "remains open". This module closes it with a measurement.

Two mitigations, both measured:
  * LAZY   - only works flagged cnw:hasNotatedMusic are engraved. A results page
             listing N works does not pay for N renders; it pays for the subset
             that actually carries renderable notation.
  * CACHE  - rendered SVG is keyed by sha1(MEI notation + verovio version +
             options) so identical input never re-renders. Cold vs warm timings
             quantify the saving.

Usage:
    python3 incipit_cache.py --benchmark          # cold vs warm over the corpus
    python3 incipit_cache.py --benchmark --repeat 50   # simulate a bulk page
"""
import argparse
import hashlib
import json
import os
import shutil
import statistics as st
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(HERE, "out", "incipit_cache")
REPORT = os.path.join(HERE, "out", "incipit_benchmark.json")

DEFAULT_OPTS = {"pageWidth": 2200, "pageHeight": 800, "scale": 45,
                "adjustPageHeight": True, "footer": "none", "header": "none"}


def _key(mei_bytes, options):
    h = hashlib.sha1()
    h.update(mei_bytes)
    h.update(json.dumps(options, sort_keys=True).encode())
    try:
        import verovio
        h.update(str(getattr(verovio, "__version__", "unknown")).encode())
    except Exception:
        pass
    return h.hexdigest()


def render_cached(path, options=None, cache_dir=CACHE):
    """Return (svg, was_cache_hit, elapsed_ms) for one MEI file."""
    options = options or DEFAULT_OPTS
    os.makedirs(cache_dir, exist_ok=True)
    raw = open(path, "rb").read()
    key = _key(raw, options)
    dest = os.path.join(cache_dir, f"{key}.svg")

    t0 = time.perf_counter()
    if os.path.exists(dest):
        svg = open(dest, encoding="utf-8").read()
        return svg, True, (time.perf_counter() - t0) * 1000

    import verovio
    tk = verovio.toolkit()
    if not tk.loadFile(path):
        raise RuntimeError(f"Verovio could not load {path}")
    tk.setOptions(options)
    tk.redoLayout()
    svg = tk.renderToSVG(1)
    open(dest, "w", encoding="utf-8").write(svg)
    return svg, False, (time.perf_counter() - t0) * 1000


def renderable_records():
    """
    LAZY selection: only records Verovio can actually engrave.

    NOTE (finding): the obvious test - "does the file contain <score>?" - is
    WRONG. data/incipit_demo.xml contains <score> markup but no <body>, and
    Verovio rejects it ("No <body> element found"). Renderability therefore
    requires <score> AND a <body>; the naive test would schedule a render that
    always fails. This mirrors the hasNotatedIncipit / hasNotatedMusic
    distinction already drawn in the data model.
    """
    out = []
    for f in sorted(os.listdir(DATA)):
        if not f.endswith(".xml"):
            continue
        p = os.path.join(DATA, f)
        txt = open(p, encoding="utf-8", errors="ignore").read()
        out.append((p, ("<score" in txt) and ("<body" in txt)))
    return out


def benchmark(repeat=1):
    recs = renderable_records()
    renderable = [p for p, has in recs if has]
    skipped = [p for p, has in recs if not has]

    print("== Verovio scaling: lazy + cache ==")
    print(f"   corpus: {len(recs)} records; renderable: {len(renderable)}; "
          f"skipped by lazy rule: {len(skipped)}")
    if not renderable:
        print("   nothing renderable; aborting")
        return

    shutil.rmtree(CACHE, ignore_errors=True)

    cold, warm, failed = [], [], []
    for _ in range(repeat):
        for p in renderable:
            try:
                _, hit, ms = render_cached(p)
            except RuntimeError:
                # One unrenderable record must not abort a bulk page render.
                if os.path.basename(p) not in failed:
                    failed.append(os.path.basename(p))
                continue
            (warm if hit else cold).append(ms)
    if failed:
        print(f"   ! render failed for {len(failed)} record(s): {', '.join(failed)}")

    # A page that naively rendered EVERY record would pay cold cost per record.
    naive_estimate = st.mean(cold) * len(recs) if cold else 0.0
    lazy_cold = st.mean(cold) * len(renderable) if cold else 0.0
    lazy_warm = st.mean(warm) * len(renderable) if warm else 0.0

    res = {
        "records_total": len(recs),
        "records_renderable": len(renderable),
        "records_skipped_by_lazy": len(skipped),
        "cold_renders": len(cold),
        "warm_hits": len(warm),
        "cold_ms_mean": round(st.mean(cold), 2) if cold else None,
        "cold_ms_median": round(st.median(cold), 2) if cold else None,
        "warm_ms_mean": round(st.mean(warm), 3) if warm else None,
        "warm_ms_median": round(st.median(warm), 3) if warm else None,
        "speedup_factor": round(st.mean(cold) / st.mean(warm), 1) if (cold and warm) else None,
        "page_naive_ms": round(naive_estimate, 1),
        "page_lazy_cold_ms": round(lazy_cold, 1),
        "page_lazy_warm_ms": round(lazy_warm, 1),
    }

    print(f"   cold render : mean {res['cold_ms_mean']} ms (n={len(cold)})")
    if warm:
        print(f"   warm cache  : mean {res['warm_ms_mean']} ms (n={len(warm)})")
        print(f"   speed-up    : {res['speedup_factor']}x")
    print(f"   whole-page estimate: naive {res['page_naive_ms']} ms -> "
          f"lazy-cold {res['page_lazy_cold_ms']} ms -> "
          f"lazy-warm {res['page_lazy_warm_ms']} ms")

    json.dump(res, open(REPORT, "w"), indent=2)
    print("   wrote", REPORT)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", action="store_true")
    ap.add_argument("--repeat", type=int, default=1)
    a = ap.parse_args()
    if a.benchmark:
        benchmark(a.repeat)
    else:
        for p, has in renderable_records():
            if has:
                _, hit, ms = render_cached(p)
                print(f"{'HIT ' if hit else 'MISS'} {os.path.basename(p):32} {ms:8.1f} ms")
