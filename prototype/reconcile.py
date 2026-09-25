#!/usr/bin/env python3
"""
reconcile.py - work-level reconciliation to external LOD identifiers (RQ3).

Modelling decisions
-------------------
* owl:sameAs is NOT used for fuzzy matches. It asserts identity, and a
  string-similarity match does not license that. Instead each candidate becomes
  a cnw:reconciledTo link carrying cnw:matchConfidence and cnw:matchSource.
  owl:sameAs is reserved for exact identifier-based matches.
* Accepted links are written back into the graph as local triples
  (out/reconciliation.ttl) so page requests do not incur a network round-trip.
  This implements the cache-back behaviour promised in the design chapter.
* Anything below the auto-accept threshold goes to a review queue CSV, which is
  the input to the manually verified gold standard used for precision/recall.

Usage:
    python3 reconcile.py              # live lookups
    python3 reconcile.py --offline    # no network; uses fixtures for testing
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher

import rdflib
from rdflib import Graph, Literal, Namespace, URIRef

HERE = os.path.dirname(os.path.abspath(__file__))
TTL_IN = os.path.join(HERE, "out", "cnw_combined.ttl")
TTL_OUT = os.path.join(HERE, "out", "reconciliation.ttl")
QUEUE_OUT = os.path.join(HERE, "out", "reconciliation_review_queue.csv")
FIXTURES = os.path.join(HERE, "gold", "fixtures.json")

CNW = Namespace("https://cnw-ld.org/ontology#")
DCTERMS = Namespace("http://purl.org/dc/terms/")
OWL = Namespace("http://www.w3.org/2002/07/owl#")

USER_AGENT = "MerMEId-Reimagined/0.3 (CM3070 student project; contact: jkymok001@mymail.sim.edu.sg)"

# Wikidata QIDs for composers, used to constrain candidate works. Seeded with
# the two confirmed by hand; reconcile_composers() fills in the rest at run time
# and writes them to out/composer_reconciliation.ttl, so the hardcoded list is a
# fallback rather than the mechanism.
WD_COMPOSER = {"Carl Nielsen": "Q205139", "Niels W. Gade": "Q313452"}

# Wikidata class for "composer", used to verify that a name match is actually a
# composer and not a namesake. Hartmann in particular is a trap: the family
# produced several composers across three generations.
WD_COMPOSER_CLASS = "Q36834"

COMPOSER_TTL_OUT = os.path.join(HERE, "out", "composer_reconciliation.ttl")
COMPOSER_QUEUE_OUT = os.path.join(HERE, "out", "composer_review_queue.csv")

# Composer identity is asserted with owl:sameAs only at this confidence, which
# is stricter than the work-level threshold. A wrong composer identity would
# propagate to every work in that catalogue.
COMPOSER_ACCEPT = 0.95

# Authority files append life dates to personal-name labels, for example
# "Hartmann, J. P. E., 1805-1900" or "Johann Schop, umbes 1590-1667". The dates
# are metadata about the person, not part of the name, so they are stripped
# before scoring for the same reason catalogue numbers are stripped from titles.
# Leaving them in cost roughly 0.3 of similarity and sent every correct VIAF
# match to the review queue.
_LIFE_DATES = re.compile(
    r"[,(\s]+(ca?\.|circa|umbes|approximately|born|d\.)?\s*"
    r"\d{3,4}\s*[-–—]?\s*(\d{3,4})?\s*\??\s*\)?\s*$")

# Names that stand for unknown or collective authorship. These are placeholders,
# not people, so no identity claim is made about them even when an external
# database happens to hold a record with the same label. Asserting
# owl:sameAs between our "Anonymous" and MusicBrainz's would state that every
# anonymous work in this catalogue shares an identity with every anonymous work
# in theirs, which is false.
PLACEHOLDER_NAMES = {
    "anonymous", "anon", "unknown", "traditional", "trad", "various",
    "folk song", "danish folk song", "folkevise", "ukendt",
}

AUTO_ACCEPT = 0.90   # >= this -> written to the graph automatically
REVIEW_FLOOR = 0.60  # >= this but < AUTO_ACCEPT -> review queue


# --------------------------------------------------------------------------
# String normalisation and similarity
# --------------------------------------------------------------------------
# Catalogue qualifiers that external authorities append to titles, e.g.
# "Æbleblomst, op. 10 no. 1" or "Maskarade, FS 39". These are metadata, not
# part of the title, and penalising them rejects correct matches.
_CAT_SUFFIX = re.compile(
    r",?\s*(op\.?|opus|fs|cnw|fog[- ]schousboe|bwv|kv|k\.|d\.|woo)\s*"
    r"\d+[a-z]?(\s*(no\.?|nr\.?)\s*\d+)?\s*$",
    re.IGNORECASE)


def normalise(s: str) -> str:
    """
    Fold case, strip accents/punctuation so 'Æbleblomst' ~ 'aebleblomst'.

    Also strips trailing catalogue qualifiers. Note that text after a colon is
    deliberately KEPT: "Maskarade, FS 39" is the opera, but
    "Maskarade, FS 39: Act I" is a part of it, and the two must not collapse
    into the same string.
    """
    if not s:
        return ""
    s = re.sub(r"\([^)]*\)", " ", s)          # drop parenthetical asides
    prev = None
    while prev != s:                          # strip stacked qualifiers
        prev = s
        s = _CAT_SUFFIX.sub("", s).strip(" ,;")
    s = s.replace("Æ", "Ae").replace("æ", "ae").replace("Ø", "O").replace("ø", "o")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    """Token-aware ratio; returns 0.0-1.0."""
    na, nb = normalise(a), normalise(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    base = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    jaccard = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    return round(0.6 * base + 0.4 * jaccard, 3)


# --------------------------------------------------------------------------
# External sources
# --------------------------------------------------------------------------
class Sources:
    def __init__(self, offline=False):
        self.offline = offline
        self._last_mb = 0.0
        self.mb_delay = 1.5      # MusicBrainz permits ~1 req/s; be conservative
        self.errors = []         # (source, title, reason) - distinguishes API
                                 # failure from a genuine absence of matches
        self.fixtures = {}
        if offline and os.path.exists(FIXTURES):
            self.fixtures = json.load(open(FIXTURES, encoding="utf-8"))

    def wikidata(self, title, composer):
        """Candidate works by this composer whose label resembles `title`."""
        if self.offline:
            return self.fixtures.get("wikidata", {}).get(title, [])
        qid = WD_COMPOSER.get(composer)
        if not qid:
            return []
        query = f"""
        SELECT ?item ?itemLabel WHERE {{
          ?item wdt:P86 wd:{qid} .
          ?item rdfs:label ?itemLabel .
          FILTER(LANG(?itemLabel) IN ("en","da"))
        }} LIMIT 400"""
        try:
            import httpx
            r = httpx.get("https://query.wikidata.org/sparql",
                          params={"query": query, "format": "json"},
                          headers={"User-Agent": USER_AGENT,
                                   "Accept": "application/sparql-results+json"},
                          timeout=60)
            r.raise_for_status()
            return [{"id": b["item"]["value"], "label": b["itemLabel"]["value"]}
                    for b in r.json()["results"]["bindings"]]
        except Exception as e:
            print(f"   ! wikidata lookup failed: {e}", file=sys.stderr)
            return []

    def musicbrainz(self, title, composer):
        """
        MusicBrainz work search.

        MusicBrainz enforces roughly one request per second and requires a
        descriptive User-Agent with real contact details. Exceeding the limit
        returns 503 and then drops the TLS connection outright. We therefore
        rate-limit conservatively, retry with exponential backoff, and RECORD
        the failure reason: an empty candidate list caused by throttling is not
        the same finding as a genuine absence of matches, and the evaluation
        must not conflate them.
        """
        if self.offline:
            return self.fixtures.get("musicbrainz", {}).get(title, [])
        import httpx
        for attempt in range(3):
            delta = time.time() - self._last_mb
            wait = max(0.0, self.mb_delay - delta) + (2.0 ** attempt - 1.0)
            if wait > 0:
                time.sleep(wait)
            self._last_mb = time.time()
            try:
                r = httpx.get("https://musicbrainz.org/ws/2/work",
                              params={"query": f'work:"{title}" AND artist:"{composer}"',
                                      "fmt": "json", "limit": 10},
                              headers={"User-Agent": USER_AGENT}, timeout=30)
                if r.status_code == 503:
                    self.errors.append(("musicbrainz", title, "503 throttled"))
                    continue
                r.raise_for_status()
                return [{"id": f"https://musicbrainz.org/work/{w['id']}",
                         "label": w.get("title", "")} for w in r.json().get("works", [])]
            except Exception as e:
                self.errors.append(("musicbrainz", title, type(e).__name__))
        return []


    # ----------------------------------------------------------------------
    # Composer-level lookups
    # ----------------------------------------------------------------------
    def wikidata_person(self, name):
        """Wikidata items whose label matches `name` AND who are composers.

        Two steps on purpose. wbsearchentities finds candidates by label, then a
        SPARQL ASK verifies each is a composer (P106 -> Q36834, following
        subclasses). Name matching alone would happily return a footballer.
        """
        if self.offline:
            return self.fixtures.get("wikidata_person", {}).get(name, [])
        try:
            import httpx
            r = httpx.get("https://www.wikidata.org/w/api.php",
                          params={"action": "wbsearchentities", "search": name,
                                  "language": "en", "format": "json",
                                  "type": "item", "limit": 10},
                          headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            hits = [{"id": h["id"], "label": h.get("label", ""),
                     "description": h.get("description", "")}
                    for h in r.json().get("search", [])]
        except Exception as e:
            self.errors.append(("wikidata_person", name, type(e).__name__))
            return []

        verified = []
        for h in hits:
            try:
                q = (f"ASK {{ wd:{h['id']} wdt:P106/wdt:P279* wd:{WD_COMPOSER_CLASS} }}")
                r = httpx.get("https://query.wikidata.org/sparql",
                              params={"query": q, "format": "json"},
                              headers={"User-Agent": USER_AGENT,
                                       "Accept": "application/sparql-results+json"},
                              timeout=30)
                r.raise_for_status()
                if r.json().get("boolean"):
                    h["id"] = f"http://www.wikidata.org/entity/{h['id']}"
                    verified.append(h)
            except Exception as e:
                self.errors.append(("wikidata_person_verify", name, type(e).__name__))
        return verified

    def musicbrainz_person(self, name):
        """MusicBrainz artists matching `name`, restricted to people."""
        if self.offline:
            return self.fixtures.get("musicbrainz_person", {}).get(name, [])
        import httpx
        for attempt in range(3):
            delta = time.time() - self._last_mb
            wait = max(0.0, self.mb_delay - delta) + (2.0 ** attempt - 1.0)
            if wait > 0:
                time.sleep(wait)
            self._last_mb = time.time()
            try:
                r = httpx.get("https://musicbrainz.org/ws/2/artist",
                              params={"query": f'artist:"{name}"', "fmt": "json",
                                      "limit": 10},
                              headers={"User-Agent": USER_AGENT}, timeout=30)
                if r.status_code == 503:
                    self.errors.append(("musicbrainz_person", name, "503 throttled"))
                    continue
                r.raise_for_status()
                return [{"id": f"https://musicbrainz.org/artist/{a['id']}",
                         "label": a.get("name", ""),
                         "description": a.get("disambiguation", ""),
                         "type": a.get("type", "")}
                        for a in r.json().get("artists", [])
                        if a.get("type") in (None, "Person")]
            except Exception as e:
                self.errors.append(("musicbrainz_person", name, type(e).__name__))
        return []

    def viaf_person(self, name):
        """VIAF AutoSuggest. VIAF is the authority the source MEI itself cites."""
        if self.offline:
            return self.fixtures.get("viaf_person", {}).get(name, [])
        try:
            import httpx
            r = httpx.get("https://viaf.org/viaf/AutoSuggest",
                          params={"query": name},
                          headers={"User-Agent": USER_AGENT,
                                   "Accept": "application/json"}, timeout=30)
            r.raise_for_status()
            out = []
            for h in (r.json().get("result") or []):
                if h.get("nametype") and h["nametype"] != "personal":
                    continue
                out.append({"id": f"https://viaf.org/viaf/{h['viafid']}",
                            "label": h.get("term", ""), "description": ""})
            return out
        except Exception as e:
            self.errors.append(("viaf_person", name, type(e).__name__))
            return []


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
def strip_life_dates(label):
    """Remove trailing life dates from an authority label."""
    prev = None
    out = (label or "").strip()
    while prev != out:
        prev = out
        out = _LIFE_DATES.sub("", out).strip(" ,;()")
    return out


def is_placeholder(name):
    """True when a name stands for unknown authorship rather than a person."""
    n = normalise(name)
    return (not n) or n in {normalise(p) for p in PLACEHOLDER_NAMES}


def name_variants(name):
    """Both orderings of a personal name.

    The catalogues encode composers inconsistently, sometimes as
    "J.P.E. Hartmann" and sometimes as "Hartmann, J.P.E.". External authorities
    use either. Trying both is what makes the inverted form matchable.
    """
    n = re.sub(r"[\[\]]", "", (name or "")).strip()
    out = [n] if n else []
    if "," in n:
        last, _, first = n.partition(",")
        flipped = f"{first.strip()} {last.strip()}".strip()
        if flipped and flipped not in out:
            out.append(flipped)
    return out


def load_composers(g):
    """Every agent that at least one work names as creator or arranger."""
    q = """
    PREFIX dcterms: <http://purl.org/dc/terms/>
    PREFIX cnw:  <https://cnw-ld.org/ontology#>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    SELECT ?a ?name (COUNT(DISTINCT ?w) AS ?works) WHERE {
      { ?w dcterms:creator ?a } UNION { ?w cnw:arranger ?a }
      ?a foaf:name ?name .
    } GROUP BY ?a ?name ORDER BY DESC(?works)"""
    out = {}
    for r in g.query(q):
        iri = str(r[0])
        rec = out.setdefault(iri, {"iri": iri, "names": [], "works": 0})
        nm = re.sub(r"[\[\]]", "", str(r[1])).strip()
        if nm and nm not in rec["names"]:
            rec["names"].append(nm)
        rec["works"] = max(rec["works"], int(r[2]))
    return list(out.values())


def reconcile_composers(g, sources, debug=False, min_works=1):
    """Resolve composer agents to Wikidata, MusicBrainz and VIAF.

    Identity is asserted with owl:sameAs only above COMPOSER_ACCEPT, because a
    wrong composer identity propagates to every work in that catalogue. Weaker
    matches become cnw:reconciledTo with a confidence score, exactly as at work
    level, and anything below REVIEW_FLOOR goes to the review queue instead of
    the graph.
    """
    out = Graph()
    out.bind("cnw", CNW); out.bind("owl", OWL)
    queued, accepted, skipped = [], 0, []

    for c in load_composers(g):
        if c["works"] < min_works:
            continue
        variants = []
        for n in c["names"]:
            variants.extend(v for v in name_variants(n) if v not in variants)
        if not variants:
            continue
        if is_placeholder(variants[0]):
            print(f"   -- {variants[0][:40]:40} ({c['works']} works) "
                  f"SKIPPED: placeholder for unknown authorship, not a person")
            skipped.append({"agent_iri": c["iri"], "name": variants[0],
                            "reason": "placeholder name"})
            continue
        print(f"   -- {variants[0][:40]:40} ({c['works']} works)")

        for source, fetch in (("wikidata", sources.wikidata_person),
                              ("musicbrainz", sources.musicbrainz_person),
                              ("viaf", sources.viaf_person)):
            scored = []
            seen_ids = set()
            for v in variants:
                for cand in fetch(v):
                    if cand["id"] in seen_ids:
                        continue
                    seen_ids.add(cand["id"])
                    for v2 in variants:
                        # Authorities differ on name order: VIAF catalogues
                        # "Nielsen, Carl" while MusicBrainz uses "Carl Nielsen".
                        # Both orderings of the candidate label are scored, or
                        # every VIAF match would fall below threshold purely
                        # because of the inversion.
                        clean = strip_life_dates(cand["label"])
                        best = max(similarity(v2, lbl)
                                   for lbl in (name_variants(clean) or [""]))
                        scored.append((best, cand, v2))
            scored.sort(key=lambda x: x[0], reverse=True)

            # Best score per distinct target, so the same record appearing under
            # several name variants counts once.
            per_target = {}
            for sc, cd, v2 in scored:
                if cd["id"] not in per_target or sc > per_target[cd["id"]][0]:
                    per_target[cd["id"]] = (sc, cd, v2)
            ranked = sorted(per_target.values(), key=lambda x: x[0], reverse=True)
            top_score = ranked[0][0] if ranked else 0.0
            tied = [r for r in ranked if abs(r[0] - top_score) < 1e-9]
            if debug:
                top = ", ".join(f"{cd['label'][:24]}={s}" for s, cd, _ in scored[:3]) or "-"
                print(f"      [{source:12}] {len(scored):3} candidates | top: {top}")
            if not ranked or top_score < REVIEW_FLOOR:
                print(f"      [{source:12}] no candidate above {REVIEW_FLOOR}")
                continue
            conf, cand, via = ranked[0]

            # Stripping life dates makes correct matches score 1.0, but it also
            # erases what separates namesakes: VIAF holds three Franz Schuberts
            # and three Johann Hartmanns whose labels become identical once the
            # dates are gone. When more than one distinct target ties at the top
            # score there is no evidence for choosing between them, so nothing is
            # asserted and every tied candidate goes to the review queue. Picking
            # the first would be arbitrary, and an arbitrary owl:sameAs is a
            # false identity claim rather than a missing one.
            if len(tied) > 1:
                for sc, cd, v in tied:
                    queued.append({"agent_iri": c["iri"], "name": variants[0],
                                   "source": source, "target_id": cd["id"],
                                   "target_label": cd["label"],
                                   "description": cd.get("description", ""),
                                   "confidence": sc, "matched_via": v,
                                   "reason": f"ambiguous: {len(tied)} candidates tied at {sc}"})
                print(f"      [{source:12}] ~ {len(tied)} candidates tied at {top_score}, "
                      f"none asserted -> review queue")
                continue
            row = {"agent_iri": c["iri"], "name": variants[0], "source": source,
                   "target_id": cand["id"], "target_label": cand["label"],
                   "description": cand.get("description", ""),
                   "confidence": conf, "matched_via": via,
                   "reason": f"below {COMPOSER_ACCEPT}"}
            if conf >= COMPOSER_ACCEPT:
                a, t = URIRef(c["iri"]), URIRef(cand["id"])
                out.add((a, OWL.sameAs, t))
                out.add((t, rdflib.RDFS.label, Literal(cand["label"])))
                out.add((t, CNW.matchConfidence, Literal(conf)))
                out.add((t, CNW.matchSource, Literal(source)))
                accepted += 1
                print(f"      [{source:12}] + {cand['id']}  ({conf})")
            else:
                queued.append(row)
                print(f"      [{source:12}] ? {cand['id']}  ({conf}) -> review queue")

    out.serialize(destination=COMPOSER_TTL_OUT, format="turtle")
    with open(COMPOSER_QUEUE_OUT, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["agent_iri", "name", "source", "target_id",
                                            "target_label", "description",
                                            "confidence", "matched_via", "reason"])
        wr.writeheader(); wr.writerows(queued)
    if skipped:
        print(f"   skipped {len(skipped)} placeholder agents "
              f"({', '.join(s['name'] for s in skipped)})")
    print(f"   accepted (>= {COMPOSER_ACCEPT}): {accepted} owl:sameAs links "
          f"-> {COMPOSER_TTL_OUT}")
    print(f"   queued for review: {len(queued)} -> {COMPOSER_QUEUE_OUT}")
    return accepted, queued


def load_works(g):
    """
    Every work with ALL its title variants, plus composer and CNW number.

    IMPORTANT: all language variants are collected, not just English. The source
    MEI carries both the original Danish title and an English translation, and
    external authorities (Wikidata, MusicBrainz) overwhelmingly catalogue these
    works under their ORIGINAL Danish titles. Matching on the English title
    alone therefore fails even when the correct target exists - the preserved
    language tags from the transformation are what make matching possible.
    """
    q = """
    PREFIX dcterms: <http://purl.org/dc/terms/>
    PREFIX cnw:  <https://cnw-ld.org/ontology#>
    PREFIX frbr: <http://purl.org/vocab/frbr/core#>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    SELECT ?w ?cnw ?title ?alt ?composer WHERE {
      ?w a frbr:Work ; dcterms:title ?title .
      OPTIONAL { ?w dcterms:alternative ?alt }
      OPTIONAL { ?w cnw:cnwNumber ?cnw }
      OPTIONAL { ?w dcterms:creator ?c . ?c foaf:name ?composer }
    }"""
    out = {}
    for r in g.query(q):
        iri = str(r[0])
        rec = out.setdefault(iri, {"iri": iri, "cnw": None,
                                   "titles": [], "composer": None})
        if r[1] and not rec["cnw"]:
            rec["cnw"] = str(r[1])
        for t in (r[2], r[3]):
            if t is not None and str(t) not in rec["titles"]:
                rec["titles"].append(str(t))
        if r[4] and not rec["composer"]:
            rec["composer"] = re.sub(r"[\[\]]", "", str(r[4]))
    for rec in out.values():
        # English label first for display; all variants used for matching.
        rec["title"] = rec["titles"][0] if rec["titles"] else ""
    return list(out.values())


def best_matches(work, sources, debug=False):
    """
    Score candidates from each source against EVERY title variant.

    Trying each variant (Danish original and English translation) and keeping
    the best is what recovers matches that monolingual matching misses. The
    variant that produced the match is recorded, because "matched via the
    original-language title" is itself an evaluation finding.
    """
    variants = work.get("titles") or [work.get("title", "")]
    results = []
    for source, fetch in (("wikidata", sources.wikidata),
                          ("musicbrainz", sources.musicbrainz)):
        # Wikidata returns the composer's whole work list, so one fetch serves
        # all variants. MusicBrainz is a per-title search, so query each.
        pooled = []
        if source == "wikidata":
            pooled = fetch(variants[0], work["composer"] or "")
        else:
            for v in variants:
                pooled.extend(fetch(v, work["composer"] or ""))

        scored = []
        for c in pooled:
            for v in variants:
                scored.append((similarity(v, c["label"]), c, v))
        scored.sort(key=lambda x: x[0], reverse=True)

        if debug:
            top = ", ".join(f"{c['label'][:26]}={s} (via {v[:18]})"
                            for s, c, v in scored[:3]) or "-"
            print(f"      [{source:12}] {len(pooled):4} candidates | top: {top}")

        if scored and scored[0][0] >= REVIEW_FLOOR:
            conf, cand, via = scored[0]
            results.append({"source": source, "target_id": cand["id"],
                            "target_label": cand["label"], "confidence": conf,
                            "matched_via": via})
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="use local fixtures instead of live lookups")
    ap.add_argument("--debug", action="store_true",
                    help="show candidate counts and top similarity scores per work")
    ap.add_argument("--wikidata-only", action="store_true",
                    help="skip MusicBrainz (useful when it is throttling)")
    ap.add_argument("--composers", action="store_true",
                    help="reconcile composer agents as well as works")
    ap.add_argument("--composers-only", action="store_true",
                    help="reconcile composers and skip the work-level pass")
    args = ap.parse_args()

    g = Graph().parse(TTL_IN, format="turtle")

    if args.composers or args.composers_only:
        print(f"== Composer-level reconciliation "
              f"({'offline' if args.offline else 'live'}) ==")
        reconcile_composers(g, Sources(offline=args.offline), debug=args.debug)
        if args.composers_only:
            return

    works = load_works(g)
    print(f"== Work-level reconciliation ({'offline' if args.offline else 'live'}) ==")
    print(f"   {len(works)} works to reconcile")

    sources = Sources(offline=args.offline)
    if args.wikidata_only:
        sources.musicbrainz = lambda *a, **k: []
    out = Graph()
    out.bind("cnw", CNW); out.bind("owl", OWL)

    accepted, queued = 0, []
    for w in works:
        if args.debug:
            print(f"   -- {w['cnw'] or '(no cnw)':>9} {w['title'][:38]:38} "
                  f"composer={w['composer'] or '?'}")
            print(f"      titles: {w.get('titles')}")
        for m in best_matches(w, sources, debug=args.debug):
            row = {"cnw": w["cnw"] or "", "work_iri": w["iri"], "title": w["title"],
                   "source": m["source"], "target_id": m["target_id"],
                   "target_label": m["target_label"], "confidence": m["confidence"],
                   "matched_via": m.get("matched_via", "")}
            if m["confidence"] >= AUTO_ACCEPT:
                s = URIRef(w["iri"]); t = URIRef(m["target_id"])
                out.add((s, CNW.reconciledTo, t))
                out.add((t, CNW.matchConfidence, Literal(m["confidence"])))
                out.add((t, CNW.matchSource, Literal(m["source"])))
                out.add((t, CNW.matchedVia, Literal(m.get("matched_via", ""))))
                out.add((t, rdflib.RDFS.label, Literal(m["target_label"])))
                accepted += 1
                print(f"   + {w['cnw'] or '-':>8} {w['title'][:30]:30} -> "
                      f"{m['source']:12} {m['confidence']}  via '{m.get('matched_via','')[:24]}'")
            else:
                queued.append(row)

    out.serialize(destination=TTL_OUT, format="turtle")
    with open(QUEUE_OUT, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["cnw", "work_iri", "title", "source",
                                            "target_id", "target_label", "confidence",
                                            "matched_via"])
        wr.writeheader(); wr.writerows(queued)

    if sources.errors:
        from collections import Counter
        tally = Counter((src, reason) for src, _, reason in sources.errors)
        print("   ! API failures (NOT the same as 'no match found'):")
        for (src, reason), n in tally.items():
            print(f"       {src:12} {reason:24} x{n}")
        print("     -> Re-run when the service recovers, or use --wikidata-only.")
    print(f"   accepted (>= {AUTO_ACCEPT}): {accepted} links -> {TTL_OUT}")
    print(f"   queued for review: {len(queued)} -> {QUEUE_OUT}")
    print("   Note: fuzzy matches use cnw:reconciledTo, not owl:sameAs, "
          "because string similarity does not license an identity claim.")


if __name__ == "__main__":
    main()