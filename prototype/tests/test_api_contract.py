#!/usr/bin/env python3
"""
tests/test_api_contract.py - interface, security and resilience of the REST layer.

Covers three of the areas the draft report feedback asked for.

Functional contract
    Every endpoint returns the shape the OpenAPI schema promises, filters
    compose, paging is consistent, and unknown identifiers produce 404 rather
    than a 500 or an empty 200.

Security (OWASP A03, injection)
    The API builds SPARQL by string interpolation, which is the same hazard as
    SQL concatenation. An earlier build passed user input straight into the
    query. These tests attempt injection through every user-facing parameter and
    assert that the graph is unchanged and no query error escapes to the caller.

Resilience, recovery and network behaviour
    The API must degrade predictably: a missing graph file, an unreachable
    Fuseki, oversized parameters and malformed input should produce a clean
    error rather than a stack trace, and the service must keep serving after a
    bad request rather than needing a restart.

Run:
    pytest -v tests/test_api_contract.py
"""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

TTL = os.path.join(ROOT, "out", "cnw_combined.ttl")


@pytest.fixture(scope="module")
def client():
    if not os.path.exists(TTL):
        pytest.skip("run_pipeline.py has not been run")
    os.environ["USE_FUSEKI"] = "no"          # exercise the in-process backend
    import api.main as main
    importlib.reload(main)
    return TestClient(main.app)


@pytest.fixture(scope="module")
def triples_before(client):
    return client.get("/health").json()["triples"]


# ---------------------------------------------------------------- contract
class TestContract:

    def test_health_reports_engine_and_size(self, client):
        h = client.get("/health").json()
        assert h["status"] == "ok"
        assert h["engine"] in ("rdflib", "fuseki")
        assert h["triples"] > 0
        assert h["works_cached"] > 0

    def test_works_returns_declared_fields(self, client):
        rows = client.get("/works", params={"limit": 5}).json()
        assert rows, "catalogue listing is empty"
        for r in rows:
            assert set(r) >= {"iri", "catalogue", "cnw", "title", "key",
                              "meter", "genres", "incipit_image"}
            assert isinstance(r["genres"], list)

    def test_total_count_header_is_present_and_sane(self, client):
        r = client.get("/works", params={"limit": 1})
        total = int(r.headers["X-Total-Count"])
        assert total >= len(r.json())

    def test_paging_does_not_repeat_or_skip(self, client):
        a = client.get("/works", params={"limit": 10, "offset": 0}).json()
        b = client.get("/works", params={"limit": 10, "offset": 10}).json()
        ids_a = [x["iri"] for x in a]
        ids_b = [x["iri"] for x in b]
        assert not set(ids_a) & set(ids_b), "pages overlap"
        full = client.get("/works", params={"limit": 20, "offset": 0}).json()
        assert [x["iri"] for x in full] == ids_a + ids_b, "paging is not stable"

    def test_facets_come_from_the_data(self, client):
        f = client.get("/facets").json()
        assert set(f) >= {"catalogue", "genre", "key", "meter"}
        for name, values in f.items():
            for v in values:
                assert v["count"] >= 1, f"{name} facet offers an empty value"

    def test_every_facet_value_returns_results(self, client):
        """A filter must never offer a value that yields nothing."""
        f = client.get("/facets").json()
        for name in ("catalogue", "genre", "key", "meter"):
            for v in f[name][:3]:
                rows = client.get("/works", params={name: v["value"], "limit": 1})
                assert rows.json(), f"{name}={v['value']} returned no works"

    def test_filters_compose(self, client):
        f = client.get("/facets").json()
        if not f["genre"]:
            pytest.skip("no genre facet in this corpus")
        genre = f["genre"][0]["value"]
        wide = client.get("/works", params={"genre": genre, "limit": 500}).json()
        cat = wide[0]["catalogue"]
        narrow = client.get("/works", params={"genre": genre, "catalogue": cat,
                                              "limit": 500}).json()
        assert len(narrow) <= len(wide)
        assert all(genre in r["genres"] and r["catalogue"] == cat for r in narrow)

    def test_search_matches_titles_and_numbers(self, client):
        sample = client.get("/works", params={"limit": 1}).json()[0]
        by_number = client.get("/search", params={"q": sample["cnw"]}).json()
        assert any(r["iri"] == sample["iri"] for r in by_number)
        word = (sample["title"] or "").split()[0]
        if len(word) > 2:
            by_title = client.get("/search", params={"q": word}).json()
            assert any(r["iri"] == sample["iri"] for r in by_title)

    def test_catalogue_prefix_is_ignored_in_search(self, client):
        """Participants typed "CNW 129"; the prefix and spacing must not matter."""
        rows = client.get("/works", params={"catalogue": "CNW", "limit": 1}).json()
        if not rows:
            pytest.skip("no CNW works in this corpus")
        num = rows[0]["cnw"]
        for form in (f"CNW {num}", f"cnw{num}", f"CNW-{num}", num):
            hit = client.get("/search", params={"q": form}).json()
            assert any(r["cnw"] == num for r in hit), f"search failed for '{form}'"

    def test_a_work_appears_exactly_once_however_many_titles_it_has(self, client):
        """
        Three works in the corpus carry two English titles, which is editorially
        correct. The listing must still show each work once: the earlier build
        returned one row per title, which the portal rendered as duplicate
        cards and a participant reported as a filtering bug.
        """
        rows = client.get("/works", params={"limit": 5000}).json()
        iris = [r["iri"] for r in rows]
        assert len(iris) == len(set(iris)), "a work appeared more than once"
        keyed = [(r["catalogue"], r["cnw"]) for r in rows if r["cnw"]]
        assert len(keyed) == len(set(keyed)), "a catalogue number appeared twice"

    def test_unknown_work_is_404(self, client):
        assert client.get("/works/no-such-number-999999").status_code == 404

    def test_detail_matches_summary(self, client):
        s = client.get("/works", params={"limit": 1}).json()[0]
        d = client.get(f"/works/{s['cnw']}",
                       params={"catalogue": s["catalogue"]}).json()
        assert d["iri"] == s["iri"]
        assert d["title"] == s["title"]


# ---------------------------------------------------------------- security
INJECTIONS = [
    'x") } INSERT DATA { <a:a> <a:b> <a:c> } #',
    'x"} ; DROP GRAPH <https://cnw-ld.org/> ; #',
    '" } UNION { ?s ?p ?o } #',
    "'; DELETE WHERE { ?s ?p ?o } ;#",
    'x\\" } #',
    '<script>alert(1)</script>',
    "../../etc/passwd",
    "%00",
    "\u0000truncated",
]


class TestInjection:
    """OWASP A03. User input must never alter the query's structure."""

    @pytest.mark.parametrize("payload", INJECTIONS)
    def test_search_is_not_injectable(self, client, payload, triples_before):
        r = client.get("/search", params={"q": payload})
        assert r.status_code in (200, 422), f"unexpected status for {payload!r}"
        if r.status_code == 200:
            assert isinstance(r.json(), list)
        assert client.get("/health").json()["triples"] == triples_before, (
            "the graph changed after a crafted query: injection succeeded")

    @pytest.mark.parametrize("param", ["catalogue", "genre", "key", "meter", "q"])
    def test_every_filter_parameter_is_escaped(self, client, param, triples_before):
        r = client.get("/works", params={param: INJECTIONS[0], "limit": 5})
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            assert r.json() == [] or isinstance(r.json(), list)
        assert client.get("/health").json()["triples"] == triples_before

    def test_path_parameter_is_escaped(self, client, triples_before):
        r = client.get('/works/1" } INSERT DATA { <a:a> <a:b> <a:c> } #')
        assert r.status_code in (404, 422)
        assert client.get("/health").json()["triples"] == triples_before

    def test_errors_do_not_leak_internals(self, client):
        """A failure must not return a stack trace, file path or query text."""
        body = client.get("/works/definitely-not-a-work").text.lower()
        for leak in ("traceback", "site-packages", "sparql", "rdflib",
                     "c:\\", "/home/"):
            assert leak not in body, f"error response leaked '{leak}'"


# ------------------------------------------------------- resilience
class TestResilience:

    def test_out_of_range_paging_is_empty_not_an_error(self, client):
        r = client.get("/works", params={"limit": 10, "offset": 10_000_000})
        assert r.status_code == 200 and r.json() == []

    def test_invalid_parameters_are_rejected_cleanly(self, client):
        for params in ({"limit": 0}, {"limit": -5}, {"limit": 99999},
                       {"offset": -1}, {"limit": "abc"}):
            r = client.get("/works", params=params)
            assert r.status_code == 422, f"{params} was not rejected"

    def test_service_survives_a_bad_request(self, client):
        client.get("/search", params={"q": INJECTIONS[0]})
        client.get("/works", params={"limit": -1})
        assert client.get("/health").json()["status"] == "ok", (
            "the service did not recover after malformed input")

    def test_empty_search_is_rejected_rather_than_scanning(self, client):
        assert client.get("/search", params={"q": ""}).status_code == 422

    def test_unicode_and_long_input_are_handled(self, client):
        for q in ("Æbleblomst", "Händel", "字", "x" * 5000):
            r = client.get("/search", params={"q": q})
            assert r.status_code in (200, 422)

    def test_repeated_requests_are_stable(self, client):
        """Reliability: the same request must give the same answer every time."""
        first = client.get("/works", params={"limit": 25}).json()
        for _ in range(20):
            assert client.get("/works", params={"limit": 25}).json() == first

    def test_concurrent_requests_do_not_corrupt_results(self, client):
        """
        rdflib's SPARQL parser is not thread-safe on first use, which produced
        intermittent errors under the FastAPI threadpool. The backend warms up
        and serialises access; this guards that fix.
        """
        from concurrent.futures import ThreadPoolExecutor
        expected = client.get("/works", params={"limit": 10}).json()
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(client.get, "/works", params={"limit": 10})
                       for _ in range(24)]
            for f in futures:
                r = f.result()
                assert r.status_code == 200
                assert r.json() == expected


class TestRecovery:
    """Behaviour when a dependency is missing or unreachable."""

    def test_missing_graph_file_fails_loudly_at_startup(self, tmp_path, monkeypatch):
        """
        A missing graph must stop the service starting, not produce an API that
        silently serves an empty catalogue.
        """
        import api.main as main
        monkeypatch.setattr(main, "TTL", str(tmp_path / "absent.ttl"))
        monkeypatch.setenv("USE_FUSEKI", "no")
        with pytest.raises(Exception):
            main.Backend()

    def test_unreachable_fuseki_falls_back_to_rdflib(self, monkeypatch):
        """
        With USE_FUSEKI=auto and no server running, the API must fall back to
        the in-process store rather than refusing to start.
        """
        monkeypatch.setenv("USE_FUSEKI", "auto")
        monkeypatch.setenv("FUSEKI_QUERY_URL", "http://127.0.0.1:9/nothing")
        import api.main as main
        importlib.reload(main)
        assert main.Backend().engine == "rdflib"

    def test_required_fuseki_fails_rather_than_pretending(self, monkeypatch):
        """With USE_FUSEKI=yes the absence of Fuseki must be an error."""
        monkeypatch.setenv("USE_FUSEKI", "yes")
        monkeypatch.setenv("FUSEKI_QUERY_URL", "http://127.0.0.1:9/nothing")
        import api.main as main
        # The module constructs a backend at import time, so the failure surfaces
        # during reload rather than from a later call. Either way it must be a
        # refusal to start, not a silent fallback.
        with pytest.raises(RuntimeError):
            importlib.reload(main)
        monkeypatch.setenv("USE_FUSEKI", "no")
        importlib.reload(main)
