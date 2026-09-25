#!/usr/bin/env python3
"""
api/main.py - FastAPI REST layer over the CNW linked-data graph (Expose layer).

Design notes
------------
* The API is a thin, typed facade over SPARQL. Every endpoint is one query, so
  no business logic duplicates what the graph already models. This keeps the RDF
  the single source of truth and means the REST layer adds accessibility for
  developers who do not write SPARQL (the secondary audience in 3.1).
* Two backends are supported behind one interface: Apache Jena Fuseki (the
  production target) and in-process rdflib (used when Fuseki is not running).
  Because SPARQL is engine-agnostic, the query strings are identical for both.
* Pydantic response models give automatic OpenAPI documentation at /docs.


Run:
    uvicorn api.main:app --reload --port 8000
    # then open http://localhost:8000/docs
"""
import os
import re
import threading
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

HERE = os.path.dirname(os.path.abspath(__file__))
TTL = os.path.join(HERE, "..", "out", "cnw_combined.ttl")

FUSEKI_QUERY_URL = os.environ.get("FUSEKI_QUERY_URL", "http://localhost:3030/cnw/query")
USE_FUSEKI = os.environ.get("USE_FUSEKI", "auto")  # "auto" | "yes" | "no"

PREFIXES = """
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX cnw:     <https://cnw-ld.org/ontology#>
PREFIX frbr:    <http://purl.org/vocab/frbr/core#>
PREFIX foaf:    <http://xmlns.com/foaf/0.1/>
PREFIX owl:     <http://www.w3.org/2002/07/owl#>
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
"""


# --------------------------------------------------------------------------
# Input handling
# --------------------------------------------------------------------------
def lit(value: str) -> str:
    """Escape a user-supplied string for safe use inside a SPARQL literal.

    Backslashes first, then quotes and control characters, following the
    SPARQL 1.1 grammar for STRING_LITERAL. Without this, a caller could close
    the literal and append arbitrary graph patterns, which is the SPARQL
    equivalent of SQL injection (OWASP A03).
    """
    s = str(value)
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return s


def normalise_number(term: str) -> str:
    """Reduce a user-typed catalogue reference to its comparable core.

    Participants typed "CNW 129", "cnw129" and "CNW-129" for the same work, so
    the prefix, separators and leading zeros are stripped before matching.
    """
    t = re.sub(r"[^a-z0-9]", "", str(term).lower())
    t = re.sub(r"^cnw", "", t)
    return t.lstrip("0") or t


# --------------------------------------------------------------------------
# Backend abstraction: identical SPARQL, two engines
# --------------------------------------------------------------------------
class Backend:
    """Chooses Fuseki if reachable, otherwise falls back to in-process rdflib.

    THREAD SAFETY (important):
    FastAPI runs non-async endpoints in a worker threadpool, so several SPARQL
    queries can be parsed concurrently. rdflib's SPARQL parser is built on
    pyparsing, whose parse-action arity detection is NOT thread-safe: concurrent
    first-time parses corrupt a shared flag and raise errors such as
        TypeError: Param.postParse2() missing 1 required positional argument

    Two mitigations are applied together:
      1. a warm-up parse in the main thread at start-up, so arity detection
         completes once, single-threaded, before any request arrives, and
      2. a mutex around rdflib query execution.
    Fuseki is unaffected, since it parses server-side, so no lock is taken.
    """

    def __init__(self):
        self.engine = None
        self._graph = None
        self._lock = threading.Lock()
        if USE_FUSEKI in ("auto", "yes"):
            try:
                import httpx
                r = httpx.post(FUSEKI_QUERY_URL,
                               data={"query": "ASK { ?s ?p ?o }"},
                               headers={"Accept": "application/sparql-results+json"},
                               timeout=3)
                if r.status_code == 200:
                    self.engine = "fuseki"
            except Exception:
                pass
        if self.engine is None:
            if USE_FUSEKI == "yes":
                raise RuntimeError("Fuseki required but not reachable")
            from rdflib import Graph
            self._graph = Graph().parse(TTL, format="turtle")
            self.engine = "rdflib"
            self._warm_up()

    def _warm_up(self):
        """Force pyparsing's arity detection to settle in the main thread."""
        for q in (
            "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }",
            PREFIXES + "SELECT ?t WHERE { ?w dcterms:title ?t } LIMIT 1",
            PREFIXES + 'SELECT ?n WHERE { ?w cnw:cnwNumber ?n . OPTIONAL { ?w frbr:realization ?e } '
                       'FILTER(CONTAINS(LCASE(STR(?n)), "1")) } LIMIT 1',
            PREFIXES + "SELECT ?a (GROUP_CONCAT(?x; separator='|') AS ?g) WHERE "
                       "{ ?a a foaf:Agent . OPTIONAL { ?a owl:sameAs ?x } } GROUP BY ?a LIMIT 1",
            PREFIXES + "SELECT ?s (COUNT(?w) AS ?n) WHERE { ?w dcterms:subject ?s } "
                       "GROUP BY ?s ORDER BY DESC(?n) LIMIT 1",
        ):
            try:
                list(self._graph.query(q))
            except Exception:
                pass

    def query(self, q: str) -> List[dict]:
        """Return a list of {var: value} dicts, engine-independent."""
        if self.engine == "fuseki":
            import httpx
            r = httpx.post(FUSEKI_QUERY_URL, data={"query": q},
                           headers={"Accept": "application/sparql-results+json"},
                           timeout=30)
            r.raise_for_status()
            res = r.json()
            cols = res["head"]["vars"]
            return [{c: b.get(c, {}).get("value") for c in cols}
                    for b in res["results"]["bindings"]]
        with self._lock:
            rows = self._graph.query(q)
            cols = [str(v) for v in rows.vars]
            return [{c: (str(r[i]) if r[i] is not None else None)
                     for i, c in enumerate(cols)} for r in rows]


backend = Backend()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Build the row cache before the first request rather than during it."""
    # Every read-only projection is built before the first request, so no user
    # ever pays the cold-start cost.
    all_rows()
    detail_index()
    composers()
    facets(min_count=1)
    health()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="MerMEId Re-imagined API",
    version="1.0.0",
    description=(
        "REST access to four thematic catalogues produced by the Danish Centre "
        "for Music Editing, re-modelled as Linked Open Data: Carl Nielsen (CNW), "
        "Niels W. Gade (NWGW), J.P.E. Hartmann (HartW) and J.A. Scheibe (SchW). "
        "A typed facade over SPARQL for developers who do not write SPARQL."
    ),
)


# --------------------------------------------------------------------------
# Response models (these generate the OpenAPI schema)
# --------------------------------------------------------------------------
class WorkSummary(BaseModel):
    iri: str = Field(..., description="Stable, dereferenceable work IRI")
    catalogue: Optional[str] = Field(
        None, description="Catalogue code: CNW, NWGW, HartW or SchW")
    cnw: Optional[str] = Field(
        None, description="Catalogue number within that catalogue, if any")
    title: Optional[str] = None
    key: Optional[str] = None
    meter: Optional[str] = None
    genres: List[str] = []
    incipit_image: Optional[str] = Field(
        None, description="Incipit graphic filename, served from the portal")


class WorkDetail(WorkSummary):
    opus: Optional[str] = None
    composer: Optional[str] = None
    created: Optional[str] = None
    tempo: Optional[str] = None
    incipit_text: Optional[str] = None
    has_notated_music: Optional[bool] = None
    scoring: List[str] = []
    editorial_notes: List[str] = []


class Composer(BaseModel):
    iri: str
    name: Optional[str] = None
    external_links: List[str] = []


class FacetValue(BaseModel):
    value: str
    count: int


class Facets(BaseModel):
    catalogue: List[FacetValue] = []
    genre: List[FacetValue] = []
    key: List[FacetValue] = []
    meter: List[FacetValue] = []


class Health(BaseModel):
    status: str
    engine: str = Field(..., description="'fuseki' or 'rdflib'")
    triples: int
    works_cached: int = 0
    details_cached: int = 0


# --------------------------------------------------------------------------
# Shared query fragments
# --------------------------------------------------------------------------
def _work_rows(filters: str = "") -> List[dict]:
    q = PREFIXES + f"""
        SELECT ?w
               (SAMPLE(?cnwv)   AS ?cnw)
               (SAMPLE(?catv)   AS ?catalogue)
               (GROUP_CONCAT(DISTINCT ?tagged; separator="||") AS ?titles)
               (SAMPLE(?keyv)   AS ?key)
               (SAMPLE(?meterv) AS ?meter)
               (SAMPLE(?imgv)   AS ?image)
               (GROUP_CONCAT(DISTINCT ?genrev; separator="|") AS ?genres)
        WHERE {{
          ?w a frbr:Work ; dcterms:title ?titlev .
          # Titles are collected in every language and chosen in Python. Five
          # works in the full catalogue have no English title, and filtering on
          # English here removed them from the catalogue listing entirely.
          BIND(CONCAT(STR(?titlev), "@@", LANG(?titlev)) AS ?tagged)
          OPTIONAL {{ ?w cnw:cnwNumber ?cnw0 }}
          OPTIONAL {{ ?w cnw:catalogueCode ?cat0 }}
          OPTIONAL {{ ?w dcterms:subject ?genre0 }}
          OPTIONAL {{ ?w frbr:realization ?e .
                     OPTIONAL {{ ?e cnw:key ?key0 }}
                     OPTIONAL {{ ?e cnw:meter ?meter0 }}
                     OPTIONAL {{ ?e cnw:incipitImage ?img0 }} }}
          # rdflib raises NotBoundError inside GROUP_CONCAT/SAMPLE when a
          # variable is unbound for some rows, so every optional is given a
          # bound default here. Empty strings are dropped in Python below.
          BIND(COALESCE(?cnw0,   "") AS ?cnwv)
          BIND(COALESCE(?cat0,   "") AS ?catv)
          BIND(COALESCE(?genre0, "") AS ?genrev)
          BIND(COALESCE(?key0,   "") AS ?keyv)
          BIND(COALESCE(?meter0, "") AS ?meterv)
          BIND(COALESCE(?img0,   "") AS ?imgv)
          {filters}
        }} GROUP BY ?w"""
    return backend.query(q)


TITLE_PREFERENCE = ("en", "da", "de", "la", "")


def pick_title(tagged: Optional[str]) -> Optional[str]:
    if not tagged:
        return None
    pairs = []
    for item in tagged.split("||"):
        text, _, lang = item.rpartition("@@")
        if text:
            pairs.append((text, lang))
    if not pairs:
        return None
    for want in TITLE_PREFERENCE:
        for text, lang in pairs:
            if lang == want:
                return text
    return pairs[0][0]


# --------------------------------------------------------------------------
# Row cache
# --------------------------------------------------------------------------
# The graph is immutable for the lifetime of the process, so the work-row
# projection is computed once and reused. Measured on the full 446-record
# catalogue, this removes roughly a second of SPARQL parsing and evaluation
# from every list and search request, which made the portal's type-to-search
# feel unresponsive. Filtering then happens over plain Python dicts.
_ROWS_CACHE: Optional[List[dict]] = None
_ROWS_LOCK = threading.Lock()


def all_rows() -> List[dict]:
    global _ROWS_CACHE
    if _ROWS_CACHE is None:
        with _ROWS_LOCK:
            if _ROWS_CACHE is None:
                _ROWS_CACHE = _work_rows("")
    return _ROWS_CACHE


_DETAIL_CACHE: Optional[dict] = None


def detail_index() -> dict:
    global _DETAIL_CACHE
    if _DETAIL_CACHE is not None:
        return _DETAIL_CACHE
    with _ROWS_LOCK:
        if _DETAIL_CACHE is not None:
            return _DETAIL_CACHE

        fields = backend.query(PREFIXES + """
            SELECT ?w
                   (GROUP_CONCAT(DISTINCT ?tagged; separator="||") AS ?titles)
                   (SAMPLE(?catv)     AS ?catalogue)
                   (SAMPLE(?cnwv)     AS ?cnw)
                   (SAMPLE(?opusv)    AS ?opus)
                   (SAMPLE(?compv)    AS ?composer)
                   (SAMPLE(?createdv) AS ?created)
                   (SAMPLE(?keyv)     AS ?key)
                   (SAMPLE(?tempov)   AS ?tempo)
                   (SAMPLE(?meterv)   AS ?meter)
                   (SAMPLE(?incipitv) AS ?incipit)
                   (SAMPLE(?imgv)     AS ?image)
                   (SAMPLE(?nmv)      AS ?nm)
                   (GROUP_CONCAT(DISTINCT ?genrev; separator="|") AS ?genres)
            WHERE {
              ?w a frbr:Work ; dcterms:title ?titlev .
              BIND(CONCAT(STR(?titlev), "@@", LANG(?titlev)) AS ?tagged)
              OPTIONAL { ?w cnw:catalogueCode ?cat0 }
              OPTIONAL { ?w cnw:cnwNumber ?cnw0 }
              OPTIONAL { ?w cnw:opus ?opus0 }
              OPTIONAL { ?w dcterms:creator ?c . ?c foaf:name ?comp0 }
              OPTIONAL { ?w cnw:arranger ?ar . ?ar foaf:name ?arr0 }
              OPTIONAL { ?w dcterms:created ?created0 }
              OPTIONAL { ?w dcterms:subject ?genre0 }
              OPTIONAL { ?w frbr:realization ?e .
                         OPTIONAL { ?e cnw:key ?key0 }
                         OPTIONAL { ?e cnw:tempo ?tempo0 }
                         OPTIONAL { ?e cnw:meter ?meter0 }
                         OPTIONAL { ?e cnw:incipitText ?incipit0 }
                         OPTIONAL { ?e cnw:incipitImage ?img0 }
                         OPTIONAL { ?e cnw:hasNotatedMusic ?nm0 } }
              BIND(COALESCE(?cat0, "")     AS ?catv)
              BIND(COALESCE(?cnw0, "")     AS ?cnwv)
              BIND(COALESCE(?opus0, "")    AS ?opusv)
              BIND(COALESCE(?comp0, ?arr0, "") AS ?compv)
              BIND(COALESCE(?created0, "") AS ?createdv)
              BIND(COALESCE(?genre0, "")   AS ?genrev)
              BIND(COALESCE(?key0, "")     AS ?keyv)
              BIND(COALESCE(?tempo0, "")   AS ?tempov)
              BIND(COALESCE(?meter0, "")   AS ?meterv)
              BIND(COALESCE(?incipit0, "") AS ?incipitv)
              BIND(COALESCE(?img0, "")     AS ?imgv)
              BIND(COALESCE(?nm0, "")      AS ?nmv)
            } GROUP BY ?w""")

        scoring: dict = {}
        for r in backend.query(PREFIXES + """
            SELECT ?w (GROUP_CONCAT(DISTINCT ?s; separator="|") AS ?scoring) WHERE {
              ?w frbr:realization ?e . ?e cnw:performingForce ?s
            } GROUP BY ?w"""):
            scoring[r["w"]] = [x for x in (r.get("scoring") or "").split("|") if x]

        notes: dict = {}
        for r in backend.query(PREFIXES + """
            SELECT ?w (GROUP_CONCAT(DISTINCT ?n; separator="||") AS ?notes) WHERE {
              ?w cnw:editorialNote ?n
            } GROUP BY ?w"""):
            notes[r["w"]] = [x for x in (r.get("notes") or "").split("||") if x]

        index: dict = {}
        for r in fields:
            r = dict(r)
            r["scoring"] = scoring.get(r["w"], [])
            r["notes"] = notes.get(r["w"], [])
            index.setdefault((r.get("cnw") or "", r.get("catalogue") or ""), r)
            index.setdefault((r.get("cnw") or "", ""), r)
        _DETAIL_CACHE = index
    return _DETAIL_CACHE


def _matches_facets(r: dict, key, genre, meter, catalogue=None) -> bool:
    if catalogue and (r.get("catalogue") or "") != catalogue:
        return False
    if key and (r.get("key") or "") != key:
        return False
    if meter and (r.get("meter") or "") != meter:
        return False
    if genre and genre not in [g for g in (r.get("genres") or "").split("|") if g]:
        return False
    return True


def _sort_key(row: dict):
    """Catalogue order: numeric entries first in numeric order, then the rest.

    Plain string ordering puts CNW 10 before CNW 2, and collection entries such
    as "Coll. 18" have no numeric position at all.
    """
    cat = (row.get("catalogue") or "\uffff")
    cnw = (row.get("cnw") or "").strip()
    m = re.match(r"^(\d+)", cnw)
    if m:
        return (cat, 0, int(m.group(1)), cnw)
    return (cat, 1, 0, cnw)


def _to_summary(r: dict) -> WorkSummary:
    blank = lambda v: v if (v not in ("", None)) else None
    return WorkSummary(
        iri=r["w"], catalogue=blank(r.get("catalogue")),
        cnw=blank(r.get("cnw")), title=pick_title(r.get("titles")),
        key=blank(r.get("key")), meter=blank(r.get("meter")),
        genres=[g for g in (r.get("genres") or "").split("|") if g],
        incipit_image=blank(r.get("image")),
    )


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
_TRIPLE_COUNT: Optional[int] = None
_COMPOSERS_CACHE: Optional[List["Composer"]] = None


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy",
                                "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "cross-origin")

    path = request.url.path
    if path.startswith(("/docs", "/redoc", "/openapi.json")):
        csp = ("default-src 'self'; "
               "img-src 'self' data: https://fastapi.tiangolo.com; "
               "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
               "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
               "font-src 'self' data: https://cdn.jsdelivr.net; "
               "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
               "form-action 'self'")
    else:
        csp = ("default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
               "form-action 'none'")
    response.headers.setdefault("Content-Security-Policy", csp)
    return response


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=Health, tags=["meta"])
def health():
    global _TRIPLE_COUNT
    if _TRIPLE_COUNT is None:
        rows = backend.query("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")
        _TRIPLE_COUNT = int(rows[0]["n"])
    rows = [{"n": _TRIPLE_COUNT}]
    return Health(status="ok", engine=backend.engine, triples=int(rows[0]["n"]),
                  works_cached=len(all_rows()), details_cached=len(detail_index()))


_FACETS_CACHE: dict = {}


@app.get("/facets", response_model=Facets, tags=["works"])
def facets(min_count: int = Query(1, ge=1, description="Hide values rarer than this")):
    """Facet values and counts, read from the graph rather than hardcoded.

    The portal builds its filter controls from this, so a facet can never offer
    a value that returns nothing, and new values appear automatically when the
    corpus grows.
    """
    def counts(pattern: str) -> List[FacetValue]:
        q = PREFIXES + f"""
            SELECT ?v (COUNT(DISTINCT ?w) AS ?n) WHERE {{ {pattern} }}
            GROUP BY ?v ORDER BY DESC(?n)"""
        out = []
        for r in backend.query(q):
            if r.get("v") and int(r["n"]) >= min_count:
                out.append(FacetValue(value=r["v"], count=int(r["n"])))
        return out

    if min_count not in _FACETS_CACHE:
        _FACETS_CACHE[min_count] = Facets(
            catalogue=counts("?w a frbr:Work ; cnw:catalogueCode ?v"),
            genre=counts("?w a frbr:Work ; dcterms:subject ?v"),
            key=counts("?w a frbr:Work ; frbr:realization ?e . ?e cnw:key ?v"),
            meter=counts("?w a frbr:Work ; frbr:realization ?e . ?e cnw:meter ?v"),
        )
    return _FACETS_CACHE[min_count]


@app.get("/works", response_model=List[WorkSummary], tags=["works"])
def list_works(
    response: Response,
    catalogue: Optional[str] = Query(
        None, description="Filter by catalogue: CNW, NWGW, HartW or SchW"),
    key: Optional[str] = Query(None, description="Filter by key, e.g. 'D major'"),
    genre: Optional[str] = Query(None, description="Filter by genre, e.g. 'Song'"),
    meter: Optional[str] = Query(None, description="Filter by metre, e.g. '6/8'"),
    q: Optional[str] = Query(None, description="Title or catalogue number fragment"),
    limit: int = Query(50, ge=1, le=5000,
                      description="Page size. The whole four-catalogue corpus is "
                                  "1,920 works, and the portal fetches it in one "
                                  "request, so the ceiling sits above that."),
    offset: int = Query(0, ge=0),
):
    """
    List catalogue works, with optional facets. Filtering across the whole
    catalogue by key, genre or metre is the cross-cutting query that the
    original per-file XML cannot answer without external tooling (see the
    evaluation chapter).

    The total number of matches before paging is returned in the
    X-Total-Count header.
    """
    rows = [r for r in all_rows() if _matches_facets(r, key, genre, meter, catalogue)]

    if q:
        needle = q.strip().lower()
        num = normalise_number(q)
        def matches(r):
            title = (pick_title(r.get("titles")) or "").lower()
            cnw = normalise_number(r.get("cnw") or "")
            return needle in title or (num and cnw == num) or (num and num in cnw)
        rows = [r for r in rows if matches(r)]

    rows.sort(key=_sort_key)
    response.headers["X-Total-Count"] = str(len(rows))
    return [_to_summary(r) for r in rows[offset:offset + limit]]


@app.get("/search", response_model=List[WorkSummary], tags=["works"])
def search(q: str = Query(..., min_length=1, description="Title or catalogue number"),
           limit: int = Query(25, ge=1, le=200)):
    """Search across work titles and catalogue numbers.

    Titles are matched as a case-insensitive substring in SPARQL. Catalogue
    numbers are matched after normalisation, so "CNW 129", "cnw129" and "129"
    all reach the same work. The usability study found that the title-only
    version silently returned nothing for a catalogue number, which four of ten
    participants attempted.
    """
    needle = q.strip().lower()
    num = normalise_number(needle)
    rows = []
    for r in all_rows():
        titles = (r.get("titles") or "").lower()
        cnw = normalise_number(r.get("cnw") or "")
        if needle in titles or (num and (cnw == num or num in cnw)):
            rows.append(r)
    rows.sort(key=_sort_key)
    return [_to_summary(r) for r in rows[:limit]]


@app.get("/works/{cnw_number:path}", response_model=WorkDetail, tags=["works"])
def get_work(cnw_number: str,
             catalogue: Optional[str] = Query(
                 None, description="Disambiguate when the same number exists in "
                                   "more than one catalogue, e.g. CNW 2 and HartW 2")):
    """Full scholarly record for one work, addressed by catalogue number.

    Served from an index built once at start-up. Numbering restarts in every
    catalogue, so a bare number can be ambiguous across the four DCM
    catalogues: without a catalogue the first match in catalogue order is
    returned, and the response says which one it was.
    """
    num = cnw_number.strip()
    idx = detail_index()
    r = idx.get((num, catalogue or "")) if catalogue else idx.get((num, ""))
    if r is None and not catalogue:
        # Fall back to any catalogue holding that number.
        matches = sorted((v for (n, c), v in idx.items() if n == num),
                         key=lambda x: x.get("catalogue") or "\uffff")
        r = matches[0] if matches else None
    if r is None:
        detail = f"No work with catalogue number {cnw_number}"
        if catalogue:
            detail += f" in catalogue {catalogue}"
        raise HTTPException(status_code=404, detail=detail)

    blank = lambda v: v if (v not in ("", None)) else None
    nm = blank(r.get("nm"))
    return WorkDetail(
        iri=r["w"], catalogue=blank(r.get("catalogue")), cnw=blank(r.get("cnw")),
        title=pick_title(r.get("titles")), opus=blank(r.get("opus")),
        composer=blank(r.get("composer")), created=blank(r.get("created")),
        key=blank(r.get("key")), tempo=blank(r.get("tempo")),
        meter=blank(r.get("meter")), incipit_text=blank(r.get("incipit")),
        incipit_image=blank(r.get("image")),
        genres=[g for g in (r.get("genres") or "").split("|") if g],
        has_notated_music=(str(nm).lower() == "true") if nm is not None else None,
        scoring=r.get("scoring", []), editorial_notes=r.get("notes", []),
    )


@app.get("/composers", response_model=List[Composer], tags=["composers"])
def composers():
    """Composers with their reconciled external authority identifiers.

    Cached for the same reason as the work index: the set cannot change while
    the process runs, and rebuilding it per request serialised behind the lock.
    """
    global _COMPOSERS_CACHE
    if _COMPOSERS_CACHE is not None:
        return _COMPOSERS_CACHE
    rows = backend.query(PREFIXES + """
        SELECT ?a ?name (GROUP_CONCAT(?ext; separator="|") AS ?exts) WHERE {
          ?a a foaf:Agent . OPTIONAL { ?a foaf:name ?name }
          OPTIONAL { ?a owl:sameAs ?ext }
        } GROUP BY ?a ?name""")
    _COMPOSERS_CACHE = [
        Composer(iri=r["a"], name=r.get("name"),
                 external_links=[e for e in (r.get("exts") or "").split("|") if e])
        for r in rows]
    return _COMPOSERS_CACHE