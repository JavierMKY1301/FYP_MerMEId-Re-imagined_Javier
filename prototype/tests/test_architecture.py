#!/usr/bin/env python3
"""
tests/test_architecture.py - architectural integrity.

The draft report feedback asked for testing of "architectural integrity" alongside unit and
functional testing. These tests assert the properties the design chapter claims
about the system's shape, so that a later change which quietly violates the
architecture fails the build rather than passing unnoticed.

Four properties are checked:

  1. Layering. The pipeline (transform) must not import the API, and the API
     must not import the pipeline. They communicate only through the serialised
     graph, which is what allows either to be replaced independently.
  2. Transformation locus. The mapping from MEI to RDF lives in XSLT, not in
     Python. Python orchestrates. If mapping logic leaks into the driver, the
     claim that the transformation is declarative stops being true.
  3. Query locus. SPARQL is the only query language used against the graph, and
     the API must not reimplement filtering in Python over a triple store.
  4. Engine independence. No SPARQL query may use syntax specific to one engine,
     because the design claims Fuseki and rdflib are interchangeable.

Run:
    pytest -v tests/test_architecture.py
"""
import ast
import os
import re

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
API = os.path.join(ROOT, "api", "main.py")
PIPELINE = os.path.join(ROOT, "run_pipeline.py")
RECONCILE = os.path.join(ROOT, "reconcile.py")
XSLT = os.path.join(ROOT, "xslt", "mei2rdf.xsl")


def imports_of(path):
    """Top-level module names imported by a Python file."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


class TestLayering:
    """Layers may not reach across each other."""

    def test_api_does_not_import_the_pipeline(self):
        assert "run_pipeline" not in imports_of(API), (
            "The API imported the pipeline driver. The two layers communicate "
            "through out/cnw_combined.ttl only, so that either can be replaced "
            "without touching the other."
        )

    def test_pipeline_does_not_import_the_api(self):
        assert "api" not in imports_of(PIPELINE)

    def test_api_does_not_read_source_mei(self):
        """The API serves the graph, never the XML it came from."""
        src = open(API, encoding="utf-8").read()
        assert ".xml" not in src and "lxml" not in src, (
            "The API referenced MEI source files. Reading XML at request time "
            "would bypass the transformation and make the graph optional."
        )

    def test_api_has_no_write_path(self):
        """The Expose layer is read-only, as the design states."""
        src = open(API, encoding="utf-8").read()
        for verb in ("@app.post", "@app.put", "@app.delete", "@app.patch"):
            assert verb not in src, f"API declares a write endpoint ({verb})"
        for kw in ("INSERT DATA", "DELETE WHERE", "DROP GRAPH"):
            assert kw not in src.upper(), f"API contains a SPARQL update ({kw})"


class TestTransformationLocus:
    """Mapping belongs in XSLT; Python orchestrates."""

    def test_xslt_carries_the_mapping(self):
        xsl = open(XSLT, encoding="utf-8").read()
        # A representative sample of the vocabulary the mapping produces.
        for term in ("dcterms:title", "cnw:cnwNumber", "frbr:realization",
                     "cnw:catalogueCode"):
            assert term in xsl, f"{term} is not produced by the stylesheet"

    def test_pipeline_does_not_build_rdf_by_hand(self):
        """
        The driver may add reconciliation links and read the graph, but it must
        not construct catalogue triples itself. Finding dcterms:title or
        cnw:cnwNumber being written in Python would mean the mapping had leaked
        out of the declarative layer.
        """
        src = open(PIPELINE, encoding="utf-8").read()
        # Strip comments and docstrings so prose mentions do not trip the check.
        code = re.sub(r"#.*", "", src)
        code = re.sub(r'"""[\s\S]*?"""', "", code)
        for pattern in (r"g\.add\(\(\s*\w+\s*,\s*DCT\.title",
                        r"g\.add\(\(\s*\w+\s*,\s*CNW\.cnwNumber"):
            assert not re.search(pattern, code), (
                "The pipeline wrote catalogue triples directly. Mapping belongs "
                "in xslt/mei2rdf.xsl."
            )


class TestQueryLocus:
    """The graph is queried with SPARQL, not traversed by hand."""

    def test_api_uses_sparql(self):
        src = open(API, encoding="utf-8").read()
        assert "SELECT" in src and "WHERE" in src

    def test_api_does_not_walk_triples_directly(self):
        """
        rdflib exposes .triples() and .subjects(), which would let the API
        sidestep SPARQL. Doing so would break the claim that the same queries
        run unchanged against Fuseki.
        """
        src = open(API, encoding="utf-8").read()
        code = re.sub(r'"""[\s\S]*?"""', "", re.sub(r"#.*", "", src))
        for call in (".triples(", ".subjects(", ".objects(", ".predicates("):
            assert call not in code, (
                f"The API used {call}, which is rdflib-specific graph traversal. "
                f"Queries must be SPARQL so both backends behave identically."
            )


class TestEngineIndependence:
    """SPARQL must be portable between rdflib and Fuseki."""

    def test_no_engine_specific_syntax(self):
        src = open(API, encoding="utf-8").read()
        # Functions and magic predicates that only one engine implements.
        for token in ("apf:", "text:query", "pf:", "list:member",
                      "bif:", "afn:", "SERVICE <http://localhost"):
            assert token not in src, f"Engine-specific SPARQL found: {token}"

    def test_both_backends_are_reachable_through_one_interface(self):
        src = open(API, encoding="utf-8").read()
        assert "fuseki" in src.lower() and "rdflib" in src.lower()
        assert "def query" in src, (
            "Backend.query is the single seam through which both engines are "
            "used. Without it, engine choice would leak into the endpoints."
        )
