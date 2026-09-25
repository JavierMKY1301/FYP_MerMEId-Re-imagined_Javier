import rdflib
g = rdflib.Graph().parse("out/cnw_combined.ttl", format="turtle")
q = lambda s: [tuple(str(x) for x in r) for r in g.query(s)]
P = "PREFIX cnw: <https://cnw-ld.org/ontology#> PREFIX dcterms: <http://purl.org/dc/terms/> PREFIX frbr: <http://purl.org/vocab/frbr/core#> PREFIX foaf: <http://xmlns.com/foaf/0.1/> "
print("works              ", q(P+"SELECT (COUNT(DISTINCT ?w) AS ?n) WHERE { ?w cnw:cnwNumber ?c }")[0][0])
print("with any title     ", q(P+"SELECT (COUNT(DISTINCT ?w) AS ?n) WHERE { ?w cnw:cnwNumber ?c ; dcterms:title ?t }")[0][0])
print("with EN title      ", q(P+'SELECT (COUNT(DISTINCT ?w) AS ?n) WHERE { ?w cnw:cnwNumber ?c ; dcterms:title ?t FILTER(lang(?t)="en") }')[0][0])
print("with DA title      ", q(P+'SELECT (COUNT(DISTINCT ?w) AS ?n) WHERE { ?w cnw:cnwNumber ?c ; dcterms:title ?t FILTER(lang(?t)="da") }')[0][0])
print("with no-lang title ", q(P+'SELECT (COUNT(DISTINCT ?w) AS ?n) WHERE { ?w cnw:cnwNumber ?c ; dcterms:title ?t FILTER(lang(?t)="") }')[0][0])
print("with key           ", q(P+"SELECT (COUNT(DISTINCT ?w) AS ?n) WHERE { ?w frbr:realization ?e . ?e cnw:key ?k }")[0][0])
print("with incipit image ", q(P+"SELECT (COUNT(DISTINCT ?w) AS ?n) WHERE { ?w frbr:realization ?e . ?e cnw:incipitImage ?i }")[0][0])
print("distinct keys      ", q(P+"SELECT ?k (COUNT(?e) AS ?n) WHERE { ?e cnw:key ?k } GROUP BY ?k ORDER BY DESC(?n)")[:12])
print("agents             ", q(P+"SELECT ?a (COUNT(?w) AS ?n) WHERE { ?w dcterms:creator ?a } GROUP BY ?a ORDER BY DESC(?n)")[:10])