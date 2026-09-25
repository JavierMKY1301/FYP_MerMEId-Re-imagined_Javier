import collections, rdflib
from rdflib import Graph
from pyshacl import validate

g = Graph().parse("out/cnw_combined.ttl", format="turtle")
shapes = Graph().parse("shapes/cnw-shapes.ttl", format="turtle")
conforms, rg, text = validate(g, shacl_graph=shapes, inference="none", abort_on_first=False)

msgs = collections.Counter()
nodes = collections.defaultdict(list)
block = []
for line in text.splitlines():
    if line.startswith("Constraint Violation"):
        block = [line]
    elif block is not None:
        block.append(line)
        if line.strip().startswith("Message:"):
            m = line.split("Message:", 1)[1].strip()
            focus = next((b.split("Focus Node:", 1)[1].strip() for b in block
                          if "Focus Node:" in b), "?")
            msgs[m] += 1
            if len(nodes[m]) < 5:
                nodes[m].append(focus)
            block = []

print("conforms:", conforms)
for m, n in msgs.most_common():
    print(f"\n{n:5}  {m}")
    for f in nodes[m]:
        print("        ", f)