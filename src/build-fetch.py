#!/usr/bin/env python3
"""Turns the bird into the terminal logo for bin/system1-fetch: half blocks
(one character = two square pixels), plus the frames of an ordered-dither
wipe that draws it in from tail to beak.

The pixels come from logo/bird-fetch.txt if it exists: a hand-drawn grid,
'#' = ink, '.' = empty, an even number of rows. Edit it to fix single
pixels. Otherwise (or with SYSTEM1_FETCH_AUTO=1) assets/bird.pgm is scaled
down, which works for any logo but can't get every stroke right; delete
bird-fetch.txt after changing the logo.

  assets/fetch/logo.txt    the finished bird
  assets/fetch/frames.txt  the wipe, frames one after another, each as tall
                           as logo.txt and padded to its width
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "assets", "bird.pgm")
GRID = os.path.join(HERE, "..", "logo", "bird-fetch.txt")
OUT = os.path.join(HERE, "..", "assets", "fetch")
WIDTH = int(os.environ.get("SYSTEM1_FETCH_WIDTH", 52))   # columns
THRESHOLD = 0.5                                          # coverage that counts as ink
# Moves the bird down by this many logo pixels before sampling. Where the
# curves fall on the half-block grid decides whether they come out as clean
# strokes or leave stray blocks (above the head, by the beak) and a rounded head;
# 1 is clean for the futc bird at 52 columns. Try 0, 0.5 or 1 after changing
# the logo or width.
Y_SHIFT = float(os.environ.get("SYSTEM1_FETCH_SHIFT", 1))
FRAMES = 18

BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def from_grid():
    with open(GRID) as f:
        rows = [r.rstrip() for r in f if r.strip()]
    w = max(map(len, rows))
    if len(rows) % 2:
        rows.append("")
    return [[x < len(r) and r[x] == "#" for x in range(w)] for r in rows]


def from_image():
    im = Image.open(SRC).convert("L")
    scale = im.width / WIDTH                       # source pixels per logo pixel
    padded = Image.new("L", (im.width, im.height + round(3 * scale)), 0)
    padded.paste(im, (0, round(Y_SHIFT * scale)))
    im = padded
    h = round(WIDTH * im.height / im.width)
    h += h % 2
    px = im.resize((WIDTH, h), Image.BOX).load()
    return [[px[x, y] / 255 >= THRESHOLD for x in range(WIDTH)] for y in range(h)]


def main():
    hand = os.path.exists(GRID) and os.environ.get("SYSTEM1_FETCH_AUTO") != "1"
    ink = from_grid() if hand else from_image()
    h, width = len(ink), len(ink[0])

    # drop empty rows top and bottom (in pairs, to keep the half-block rows)
    while h > 2 and not any(ink[0] + ink[1]):
        ink, h = ink[2:], h - 2
    while h > 2 and not any(ink[-1] + ink[-2]):
        ink, h = ink[:-2], h - 2

    def render(on):
        rows = []
        for y in range(0, h, 2):
            rows.append("".join(" ▀▄█"[on(x, y) + 2 * on(x, y + 1)] for x in range(width)))
        return rows

    # a pixel appears once the wipe front (left to right, softened by the
    # Bayer matrix so it dissolves rather than slides) has passed it
    def appear(x, y):
        return 0.65 * x / (width - 1) + 0.35 * BAYER[y % 4][x % 4] / 16

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "logo.txt"), "w") as f:
        f.write("\n".join(r.rstrip() for r in render(lambda x, y: ink[y][x])) + "\n")
    with open(os.path.join(OUT, "frames.txt"), "w") as f:
        for i in range(1, FRAMES + 1):
            t = i / FRAMES
            f.write("\n".join(render(lambda x, y: ink[y][x] and appear(x, y) < t)) + "\n")
    print(f"build-fetch: {width}x{h // 2} logo from {'logo/bird-fetch.txt' if hand else 'bird.pgm'}, {FRAMES} frames", file=sys.stderr)


if __name__ == "__main__":
    main()
