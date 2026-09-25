import glob, collections
from lxml import etree
M = "{http://www.music-encoding.org/ns/mei}"
tags = ["key", "meter", "tempo", "perfRes", "incip"]
seen = {t: collections.Counter() for t in tags}
sample = {}
for f in sorted(glob.glob("data/*.xml")):
    t = etree.parse(f)
    for tag in tags:
        for el in t.iter(M + tag):
            txt = (el.text or "").strip()
            attrs = ",".join(sorted(el.attrib.keys())) or "-"
            seen[tag][(bool(txt), attrs)] += 1
            k = (tag, bool(txt), attrs)
            if k not in sample:
                sample[k] = (f.split("\\")[-1], etree.tostring(el, encoding="unicode")[:180])
for tag in tags:
    print("==", tag)
    for (has_text, attrs), n in seen[tag].most_common(6):
        print(f"   text={has_text} attrs=[{attrs}] count={n}")
        print("      ", sample[(tag, has_text, attrs)][1].replace("\n", " ")[:160])