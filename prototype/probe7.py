import glob
from lxml import etree
M = "{http://www.music-encoding.org/ns/mei}"
shown = 0
for f in sorted(glob.glob("data/*.xml")):
    t = etree.parse(f)
    w = t.find(f".//{M}work")
    if w is None:
        continue
    ids = [(i.get("label"), (i.text or "").strip()) for i in w.findall(M + "identifier")]
    if not any(lbl == "HartW" and val.upper().startswith("B") for lbl, val in ids):
        continue
    if shown >= 3:
        break
    shown += 1
    print("===", f.split("\\")[-1], ids[:3])
    for c in w.findall(M + "contributor"):
        print("   contributor:", etree.tostring(c, encoding="unicode")[:220].replace("\n", " "))
    for p in w.iter(M + "persName"):
        print("   persName role=%s: %s" % (p.get("role"), (p.text or "").strip()[:50]))
    if w.find(M + "contributor") is None:
        print("   (no contributor element at all)")