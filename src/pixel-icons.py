#!/usr/bin/env python3
"""Pixelate Noctalia's Tabler icon font: every icon is resampled onto the
16x16 grid (chunky but still legible at bar size) and rebuilt
from square cells. Writes ../noctalia/assets/fonts/noctalia-tabler.ttf.

    python3 pixel-icons.py [grid] [threshold]
"""
import logging
import sys
import warnings
from pathlib import Path

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

warnings.filterwarnings("ignore")
logging.getLogger("fontTools").setLevel(logging.ERROR)
ASSETS = Path("/usr/share/noctalia/assets")
SRC = ASSETS / "fonts/noctalia-tabler.ttf"
MIRROR = Path(__file__).resolve().parent.parent / "noctalia/assets"
OUT = MIRROR / "fonts/noctalia-tabler.ttf"

GRID = int(sys.argv[1]) if len(sys.argv) > 1 else 16
# the 24-unit Tabler viewbox sits at x 10.5..1010.5, y -100..900 in font units
X0, Y_TOP, BOX = 10.5, 900.0, 1000.0
CELL_PX = 32                       # supersampling per output pixel
SIZE = GRID * CELL_PX              # render size, pixels per em (em = 1000)
SCALE = SIZE / 1000.0
THRESHOLD = float(sys.argv[2]) if len(sys.argv) > 2 else 0.45

font = TTFont(str(SRC))
glyf = font["glyf"]
pil = ImageFont.truetype(str(SRC), SIZE, layout_engine=ImageFont.Layout.BASIC)
unit = BOX / GRID

done = 0
for cp, name in font.getBestCmap().items():
    img = Image.new("L", (SIZE, SIZE), 0)
    # baseline (y=0) is Y_TOP font units below the top of the box
    ImageDraw.Draw(img).text((-X0 * SCALE, Y_TOP * SCALE), chr(cp), font=pil, fill=255, anchor="ls")
    small = img.resize((GRID, GRID), Image.BOX)
    px = small.load()

    pen = TTGlyphPen(None)
    for j in range(GRID):
        y1 = Y_TOP - j * unit
        y0 = y1 - unit
        i = 0
        while i < GRID:
            if px[i, j] < THRESHOLD * 255:
                i += 1
                continue
            start = i
            while i < GRID and px[i, j] >= THRESHOLD * 255:
                i += 1
            x0, x1 = X0 + start * unit, X0 + i * unit
            # clockwise, as TrueType expects for filled contours
            pen.moveTo((round(x0), round(y0)))
            pen.lineTo((round(x0), round(y1)))
            pen.lineTo((round(x1), round(y1)))
            pen.lineTo((round(x1), round(y0)))
            pen.closePath()
    glyf[name] = pen.glyph()
    done += 1

OUT.parent.mkdir(parents=True, exist_ok=True)
font.save(OUT)

# the rest of the mirror: symlinks to Noctalia's assets
for src in list(ASSETS.iterdir()) + list((ASSETS / "fonts").iterdir()):
    dst = MIRROR / src.relative_to(ASSETS)
    if src == ASSETS / "fonts" or dst == OUT:
        continue
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(src)
print(f"{done} icons on a {GRID}x{GRID} grid -> {OUT}")
