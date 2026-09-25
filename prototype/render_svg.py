import os, verovio
HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(HERE, "data", "nielsen_cnw0129.xml")
OUT  = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

tk = verovio.toolkit()
assert tk.loadFile(SRC), "could not load MEI"
tk.setOptions({"pageWidth": 2200, "pageHeight": 800, "scale": 45,
               "adjustPageHeight": True, "footer": "none", "header": "none"})
tk.redoLayout()
open(os.path.join(OUT, "cnw129_incipit.svg"), "w", encoding="utf-8").write(tk.renderToSVG(1))
print("Rendered notation ->", os.path.join(OUT, "cnw129_incipit.svg"))