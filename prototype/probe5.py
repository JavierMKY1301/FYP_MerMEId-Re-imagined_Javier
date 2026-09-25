import glob, collections, rdflib
from lxml import etree
M = "{http://www.music-encoding.org/ns/mei}"

labels = collections.Counter()
for f in glob.glob("data/*.xml"):
    for w in etree.parse(f).iter(M + "work"):
        for i in w.findall(M + "identifier"):
            labels[i.get("label")] += 1
print("identifier labels:", labels.most_common(12))

g = rdflib.Graph().parse("out/cnw_combined.ttl", format="turtle")
FRBR = rdflib.Namespace("http://purl.org/vocab/frbr/core#")
CNWN = rdflib.URIRef("https://cnw-ld.org/ontology#cnwNumber")
works = set(g.subjects(rdflib.RDF.type, FRBR.Work))
withnum = {s for s in works if (s, CNWN, None) in g}
print("work nodes:", len(works), "| with catalogue number:", len(withnum))

titles = collections.Counter(str(s) for s, p, o in g.triples((None, rdflib.URIRef("http://purl.org/dc/terms/title"), None)))
print("work nodes with 4+ titles (possible IRI collision):", sum(1 for v in titles.values() if v >= 4))