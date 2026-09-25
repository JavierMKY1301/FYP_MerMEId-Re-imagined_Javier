import glob, collections
from lxml import etree
M = "{http://www.music-encoding.org/ns/mei}"
c = collections.Counter()
sample = {}
for f in glob.glob("data/*.xml"):
    for el in etree.parse(f).iter(M + "incipText"):
        has_p = len(el.findall(M + "p")) > 0
        txt = "".join(el.itertext()).strip()
        c[(has_p, bool(txt))] += 1
        if (has_p, bool(txt)) not in sample and txt:
            sample[(has_p, bool(txt))] = etree.tostring(el, encoding="unicode")[:200]
print("(has <p>, has text): count")
for k, n in c.most_common():
    print("  ", k, n)
    if k in sample:
        print("      ", sample[k].replace("\n", " ")[:160])