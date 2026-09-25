# probe8.py
import glob
from lxml import etree
M = "{http://www.music-encoding.org/ns/mei}"
shown = 0
for f in sorted(glob.glob("data/*.xml")):
    w = etree.parse(f).find(f".//{M}work")
    if w is None:
        continue
    ids = [(i.get("label"), (i.text or "").strip()) for i in w.findall(M + "identifier")]
    if not any(lbl == "SchW" and val.upper().startswith("C1") for lbl, val in ids):
        continue
    if shown >= 3:
        break
    shown += 1
    title = w.find(M + "title")
    print("===", f.split("\\")[-1], ids[:2], "|", (title.text or "").strip()[:60] if title is not None else "-")
    people = list(w.iter(M + "persName"))
    if not people:
        print("   (no persName anywhere in the work)")
    for p in people:
        print("   persName role=%s: %s" % (p.get("role"), "".join(p.itertext()).strip()[:50]))
    for c in w.iter(M + "corpName"):
        print("   corpName role=%s: %s" % (c.get("role"), "".join(c.itertext()).strip()[:50]))