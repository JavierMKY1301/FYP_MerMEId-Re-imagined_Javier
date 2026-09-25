#!/usr/bin/env python3
"""
render_incipit.py - render the notated record (CNW 129) to SVG/PNG with Verovio.
Demonstrates that notation preserved in the source MEI is renderable in the
Connect layer. Output: out/cnw129_incipit.svg / .png (+ cropped excerpt).
"""
import os
import verovio
import cairosvg
from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(HERE, "data", "nielsen_cnw0129.xml")
OUT  = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

tk = verovio.toolkit()
assert tk.loadFile(SRC), "could not load MEI"
tk.setOptions({"pageWidth": 2200, "pageHeight": 800, "scale": 45,
               "adjustPageHeight": True, "footer": "none", "header": "none"})
tk.redoLayout()
svg = tk.renderToSVG(1)
open(os.path.join(OUT, "cnw129_incipit.svg"), "w", encoding="utf-8").write(svg)
cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                 write_to=os.path.join(OUT, "cnw129_incipit.png"), output_width=1600)

im = Image.open(os.path.join(OUT, "cnw129_incipit.png"))
w, h = im.size
crop = ImageOps.expand(im.crop((0, 0, int(w * 0.62), h)), border=12, fill="white")
crop.save(os.path.join(OUT, "cnw129_incipit_crop.png"))
print("rendered:", tk.getPageCount(), "pages ->", OUT)
