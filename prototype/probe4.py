import glob
from lxml import etree
M = "{http://www.music-encoding.org/ns/mei}"
XML = "{http://www.w3.org/XML/1998/namespace}"
for f in glob.glob("data/*.xml"):
    for w in etree.parse(f).iter(M + "work"):
        ts = w.findall(M + "title")
        if not ts:
            continue
        plain_en = [t for t in ts if t.get("type") in (None, "main") and t.get(XML + "lang") == "en"]
        typed_en = [t for t in ts if t.get("type") not in (None, "main") and t.get(XML + "lang") == "en"]
        if typed_en and not plain_en:
            print(f.split("\\")[-1])
            for t in ts:
                print("   type=%-12s lang=%-3s %s" % (t.get("type"), t.get(XML + "lang"), (t.text or "").strip()[:60]))