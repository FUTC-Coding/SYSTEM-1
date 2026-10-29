#!/usr/bin/env bash
# Renders the textures system1-bg samples from: the bird logo, a strip of
# vertical Japanese captions and the VT323 clock digits. All 8-bit PGM,
# white = ink. Re-run after changing a phrase or the logo.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../assets"
LOGO="${LOGO:-$HERE/../logo/bird.svg}"
font() {   # path of an installed font family, or fail
    local f; f="$(fc-match -f '%{file}' "$1")"
    [ "$(fc-match -f '%{family[0]}' "$1")" = "$1" ] || { echo "build-assets: font '$1' is not installed" >&2; exit 1; }
    printf '%s' "$f"
}
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT"

# Bird: 1024 px wide, coverage in the gray channel
rsvg-convert -w 1024 "$LOGO" -o "$TMP/bird.png"
magick "$TMP/bird.png" -alpha extract -depth 8 "$OUT/bird.pgm"

# Captions: 8 columns of 160x960, one vertical phrase each.
#   0-3: time-of-day greetings (morning, afternoon, sunset, night)
#   4-6: general phrases
#   7:   the single glyph cut out of the red hanko seal
PHRASES=("おはよう" "こんにちは" "夕焼け" "おやすみ" "折り紙" "未来" "電子の鳥" "鳥")
JA="$(font DotGothic16)"
cols=()
for i in "${!PHRASES[@]}"; do
    p="${PHRASES[$i]}"
    v="$(printf '%s' "$p" | sed 's/./&\n/g' | sed '/^$/d')"
    size=112; [ "$i" = 7 ] && size=136
    magick -size 160x960 xc:black -font "$JA" -pointsize $size -fill white \
        -gravity north -interline-spacing -14 -annotate +0+8 "$v" "$TMP/c$i.png"
    cols+=("$TMP/c$i.png")
done
magick "${cols[@]}" +append -colorspace gray -depth 8 "$OUT/text.pgm"

# Clock digits "0123456789:" in VT323, 11 cells of 64x128
VT="$(font VT323)"
cells=()
for i in 0 1 2 3 4 5 6 7 8 9 :; do
    n="$TMP/d_${i/:/colon}.png"
    magick -size 64x128 xc:black -font "$VT" -pointsize 150 -fill white \
        -gravity center -annotate +0+0 "$i" "$n"
    cells+=("$n")
done
magick "${cells[@]}" +append -colorspace gray -depth 8 "$OUT/digits.pgm"

ls -l "$OUT"
