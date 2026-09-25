# MerMEId Re-imagined

A Linked Data portal for classical composer works catalogues.

Four thematic catalogues produced by the Danish Centre for Music Editing are
transformed from MEI XML into a single RDF graph, served through SPARQL and a
documented REST interface, and presented in a browsable portal.

| | |
| --- | --- |
| Records | 1,920 across four catalogues |
| Catalogues | Carl Nielsen (CNW) 446, Niels W. Gade (NWGW) 483, J.P.E. Hartmann (HartW) 590, Johann Adolph Scheibe (SchW) 401 |
| Graph | 65,376 triples |
| Field coverage | 99.8 percent of scholarly fields present in the source |
| Tests | 98 Python, 105 browser tests across five browser and device profiles |

University of London BSc Computer Science, CM3070 final project. Template
CM3010 Databases and Advanced Data Techniques, Project Idea 1, "Working with
works, a new approach to music cataloguing."

## Layout

```
prototype/           transform, validation, measurement, REST interface
  data/              MEI source records
  xslt/              the MEI to RDF stylesheet
  shapes/            SHACL constraints
  api/               REST interface
  tests/             test suites
  perf/              load profile
  out/               generated graph and results (produced by the pipeline)
portal/              React portal
  e2e/               browser tests
```

## Requirements

Python 3.10 or later, Node 18 or later. Docker is needed only for the security
scans and the optional triplestore.

## Running it

Install dependencies.

```
cd prototype
py -m pip install -r requirements.txt
cd ../portal
npm install
```

Build the graph. This runs the transformation, validates it against SHACL,
measures coverage and answers the competency questions.

```
cd prototype
py run_pipeline.py
```

Start the interface. It takes about five seconds to build its read-only caches
before serving.

```
py -m uvicorn api.main:app --port 8000
```

Start the portal in a second terminal.

```
cd portal
npm run dev
```

The portal is at localhost:5173 and the generated API documentation at
localhost:8000/docs.

## Optional, reconciliation

Composer reconciliation queries Wikidata, VIAF and MusicBrainz live. It accepts
a link only above a confidence of 0.95 and refuses to assert anything when two
candidates tie, queuing those for review instead.

```
py reconcile.py --composers-only
py run_pipeline.py
```

Results are written to `out/composer_reconciliation.ttl` and
`out/composer_review_queue.csv`.

## Tests

```
cd prototype
py -m pytest tests/ -v
```

```
cd portal
npx playwright install
npx playwright test
```


## Data

The source records are the thematic catalogues of Carl Nielsen, Niels W. Gade,
J.P.E. Hartmann and Johann Adolph Scheibe, created between 2010 and 2020 by the
Danish Centre for Music Editing and published by the Royal Danish Library in its
open repository under a CC0 public domain dedication.

https://loar.kb.dk/handle/1902/49096

Incipit graphics ship with the same dataset. To display them, copy the incipit
images into `portal/public/incipits/`.

Cite as: Danish Centre for Music Editing, Royal Danish Library, Thematic
Catalogues of Works by Carl Nielsen, Johann Adolph Scheibe, Niels W. Gade and
J.P.E. Hartmann.

## Licence

The catalogue data is CC0 and belongs to the Danish Centre for Music Editing and the Royal Danish Library.
It can be found in the url link above.
