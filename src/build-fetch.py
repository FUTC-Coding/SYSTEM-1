#!/usr/bin/env python3
"""Turns assets/bird.pgm into the terminal logo for bin/system1-fetch: the
bird in half blocks (one character = two square pixels), plus the frames of
an ordered-dither wipe that draws it in from tail to beak.

  assets/fetch/logo.txt    the finished bird
  assets/fetch/frames.txt  the wipe, frames one after another, each as tall
                           as logo.txt and padded to its width
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "assets", "bird.pgm")
OUT = os.path.join(HERE, "..", "assets", "fetch")
WIDTH = int(os.environ.get("SYSTEM1_FETCH_WIDTH", 48))   # columns
THRESHOLD = 0.4                                          # coverage that counts as ink
FRAMES = 18

BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def main():
    im = Image.open(SRC).convert("L")
    h = round(WIDTH * im.height / im.width)
    h += h % 2
    px = im.resize((WIDTH, h), Image.BOX).load()
    ink = [[px[x, y] / 255 >= THRESHOLD for x in range(WIDTH)] for y in range(h)]

    # drop empty rows top and bottom (in pairs, to keep the half-block rows)
    while h > 2 and not any(ink[0] + ink[1]):
        ink, h = ink[2:], h - 2
    while h > 2 and not any(ink[-1] + ink[-2]):
        ink, h = ink[:-2], h - 2

    def render(on):
        rows = []
        for y in range(0, h, 2):
            rows.append("".join(" ▀▄█"[on(x, y) + 2 * on(x, y + 1)] for x in range(WIDTH)))
        return rows

    # a pixel appears once the wipe front (left to right, softened by the
    # Bayer matrix so it dissolves rather than slides) has passed it
    def appear(x, y):
        return 0.65 * x / (WIDTH - 1) + 0.35 * BAYER[y % 4][x % 4] / 16

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "logo.txt"), "w") as f:
        f.write("\n".join(r.rstrip() for r in render(lambda x, y: ink[y][x])) + "\n")
    with open(os.path.join(OUT, "frames.txt"), "w") as f:
        for i in range(1, FRAMES + 1):
            t = i / FRAMES
            f.write("\n".join(render(lambda x, y: ink[y][x] and appear(x, y) < t)) + "\n")
    print(f"build-fetch: {WIDTH}x{h // 2} logo, {FRAMES} frames", file=sys.stderr)


if __name__ == "__main__":
    main()
