#!/usr/bin/env python3
"""
perf/locustfile.py - load, stress, spike and soak testing for the REST API.

Locust is used rather than k6 or JMeter because the project is already a Python
codebase, so the load profile lives in the same language and needs no extra
runtime. The scenarios below correspond to the four kinds of test the project requires. 
They differ only in how users arrive and how long they stay, so one
file defines all of them and the shape is chosen on the command line.

Load     expected traffic, held steady, to establish normal behaviour.
Stress   ramp past capacity until latency or errors degrade, to find where.
Spike    idle, then a sudden surge, to test recovery rather than throughput.
Soak     modest load for a long period, to expose leaks and drift.

Workload mix reflects the portal's real behaviour rather than an even spread.
The portal fetches the whole catalogue once on load and then filters in the
browser, so listing is heavy but rare, while detail pages are light and
frequent. Weighting the tasks the other way round would measure a system nobody
uses.

"""
import random

from locust import HttpUser, task, between, events

# Service level objectives. These are the thresholds the evaluation reports
# against, declared before the run rather than chosen afterwards to fit.
SLO_P95_MS = 500
SLO_ERROR_RATE = 0.01

_catalogue = {"works": [], "facets": {}}


@events.test_start.add_listener
def _prime(environment, **_):
    """Fetch the catalogue once so virtual users exercise real identifiers.

    Hammering one hardcoded work would measure the cache rather than the
    service, and requesting numbers that do not exist would measure the 404
    path. Both would flatter the result.
    """
    import urllib.request, json
    host = environment.host or "http://localhost:8000"
    try:
        with urllib.request.urlopen(f"{host}/works?limit=500", timeout=30) as r:
            _catalogue["works"] = [w for w in json.load(r) if w.get("cnw")]
        with urllib.request.urlopen(f"{host}/facets", timeout=30) as r:
            _catalogue["facets"] = json.load(r)
        print(f"primed with {len(_catalogue['works'])} works")
    except Exception as e:
        print(f"could not prime workload, falling back to fixed values: {e}")


def _random_work():
    if _catalogue["works"]:
        w = random.choice(_catalogue["works"])
        return w["cnw"], w.get("catalogue")
    return "128", "CNW"


def _facet(name):
    vals = _catalogue["facets"].get(name) or []
    return random.choice(vals)["value"] if vals else None


class PortalUser(HttpUser):
    """A reader browsing the catalogue through the portal."""

    wait_time = between(0.5, 2.5)

    @task(10)
    def open_a_work(self):
        cnw, cat = _random_work()
        params = {"catalogue": cat} if cat else {}
        with self.client.get(f"/works/{cnw}", params=params,
                             name="/works/{cnw}", catch_response=True) as r:
            if r.status_code == 404:
                r.success()          # a missing work is a valid answer, not a failure
            elif r.elapsed.total_seconds() * 1000 > SLO_P95_MS * 4:
                r.failure(f"detail took {r.elapsed.total_seconds():.1f}s")

    @task(4)
    def search(self):
        term = random.choice(["summer", "sang", "129", "CNW 2", "opera",
                              "symfoni", "hartmann", "lied"])
        self.client.get("/search", params={"q": term, "limit": 25}, name="/search")

    @task(3)
    def filter_by_facet(self):
        name = random.choice(["genre", "catalogue", "key", "meter"])
        value = _facet(name)
        if value:
            self.client.get("/works", params={name: value, "limit": 50},
                            name=f"/works?{name}=")

    @task(2)
    def page_through_listing(self):
        offset = random.choice([0, 20, 40, 100, 500])
        self.client.get("/works", params={"limit": 20, "offset": offset},
                        name="/works?paged")

    @task(1)
    def load_whole_catalogue(self):
        """What the portal does on first load. The heaviest single request."""
        self.client.get("/works", params={"limit": 5000}, name="/works?all")

    @task(1)
    def facets(self):
        self.client.get("/facets", name="/facets")


class ApiConsumer(HttpUser):
    """A developer using the REST API directly, with no think time."""

    wait_time = between(0, 0.1)

    @task(3)
    def health(self):
        self.client.get("/health", name="/health")

    @task(2)
    def composers(self):
        self.client.get("/composers", name="/composers")

    @task(5)
    def detail(self):
        cnw, cat = _random_work()
        self.client.get(f"/works/{cnw}", params={"catalogue": cat} if cat else {},
                        name="/works/{cnw} (api)")


@events.test_stop.add_listener
def _verdict(environment, **_):
    """Print a pass or fail against the declared objectives."""
    stats = environment.stats.total
    p95 = stats.get_response_time_percentile(0.95) or 0
    rate = (stats.num_failures / stats.num_requests) if stats.num_requests else 0
    print("\n=== Verdict against declared objectives ===")
    print(f"   requests           {stats.num_requests}")
    print(f"   throughput         {stats.total_rps:.1f} req/s")
    print(f"   median             {stats.median_response_time} ms")
    print(f"   p95                {p95:.0f} ms   (objective {SLO_P95_MS} ms)")
    print(f"   failures           {rate:.2%}      (objective {SLO_ERROR_RATE:.0%})")
    ok = p95 <= SLO_P95_MS and rate <= SLO_ERROR_RATE
    print(f"   RESULT             {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("   Note: for a stress run a FAIL is the expected outcome. Record "
              "the user count at which the objective was first breached.")
