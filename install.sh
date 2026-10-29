#!/usr/bin/env bash
# Installs System 1 from this checkout. Safe to run again (after a pull, or
# after a Noctalia update to refresh the pixel icons).
#
#   ./install.sh [--location "LAT LON"]     install / update
#   ./install.sh --uninstall                switch off and remove the links
#
# It does not switch the theme on; run  ~/.config/system1/bin/theme-switch system1
# (or press SUPER+CTRL+T) afterwards.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
S1="$HOME/.config/system1"
HYPR="$HOME/.config/hypr"
FONTS="$HOME/.local/share/fonts/system1"
FC="$HOME/.config/fontconfig/conf.d/50-system1.conf"
GF="https://raw.githubusercontent.com/google/fonts/main/ofl"

say() { printf '\033[1m::\033[0m %s\n' "$*"; }
die() { printf 'install.sh: %s\n' "$*" >&2; exit 1; }

# link DST -> SRC, refusing to replace a real file
link() {
    local src="$1" dst="$2"
    if [ -e "$dst" ] && [ ! -L "$dst" ]; then
        die "$dst exists and is not a link; move it away first"
    fi
    mkdir -p "$(dirname "$dst")"
    ln -sfn "$src" "$dst"
}

uninstall() {
    if [ "$(cat "$HYPR/theme-name" 2>/dev/null)" = system1 ]; then
        say "switching System 1 off"
        "$S1/bin/theme-switch" off || true
    fi
    say "removing links"
    for l in "$HYPR/themes/system1/init.lua" "$HYPR/themes/loader.lua" "$FC" \
             "$HOME/.config/noctalia/palettes/System1.json" "$HOME/.config/noctalia/system1.toml"; do
        [ -L "$l" ] && rm -f "$l"
    done
    rmdir "$HYPR/themes/system1" 2>/dev/null || true
    [ -L "$S1" ] && rm -f "$S1"
    echo
    echo "Remove  require(\"themes.loader\")  from $HYPR/hyprland.lua and reload Hyprland."
    echo "The fonts in $FONTS are left in place."
}

location=""
case "${1:-}" in
    --uninstall) uninstall; exit 0 ;;
    --location) location="${2:?--location needs \"LAT LON\"}" ;;
    "") ;;
    *) die "usage: install.sh [--location \"LAT LON\"] | --uninstall" ;;
esac

say "checking dependencies"
missing=()
for c in hyprctl noctalia wayland-scanner pkg-config cc make rsvg-convert magick python3 fc-match curl; do
    command -v "$c" >/dev/null || missing+=("$c")
done
pkg-config --exists wayland-client wayland-egl egl glesv2 || missing+=("wayland/EGL/GLES2 development files")
python3 -c "import PIL, fontTools" 2>/dev/null || missing+=("python Pillow and fontTools")
[ -d /usr/share/noctalia/assets ] || missing+=("Noctalia assets in /usr/share/noctalia")
[ -f "$HYPR/hyprland.lua" ] || missing+=("a Lua Hyprland config ($HYPR/hyprland.lua)")
[ ${#missing[@]} -eq 0 ] || die "missing: $(printf '%s, ' "${missing[@]}" | sed 's/, $//')"

say "linking $S1 -> $REPO"
[ "$(readlink -f "$S1" 2>/dev/null)" = "$REPO" ] || link "$REPO" "$S1"

say "fonts"
mkdir -p "$FONTS"
fetch_font() {   # family, path under google/fonts/ofl
    local family="$1" path="$2"
    if [ "$(fc-match -f '%{family[0]}' "$family")" != "$family" ]; then
        echo "   downloading $family"
        curl -fsSL "$GF/$path" -o "$FONTS/$(basename "${path//%5B/[}" | sed 's/%5D/]/')"
        curl -fsSL "$GF/$(dirname "$path")/OFL.txt" -o "$FONTS/OFL-$(basename "$(dirname "$path")").txt"
    fi
}
fetch_font "Pixelify Sans" "pixelifysans/PixelifySans%5Bwght%5D.ttf"
fetch_font "VT323" "vt323/VT323-Regular.ttf"
fetch_font "DotGothic16" "dotgothic16/DotGothic16-Regular.ttf"
link "$REPO/fontconfig/50-system1.conf" "$FC"
fc-cache -f >/dev/null

say "building system1-bg"
make -s -C "$REPO/src" install PREFIX="$REPO"

say "rendering textures"
"$REPO/src/build-assets.sh" >/dev/null

say "pixelating Noctalia's icons"
python3 "$REPO/src/pixel-icons.py"

if [ -n "$location" ]; then
    printf '%s\n' "$location" > "$REPO/location"
fi
if [ ! -f "$REPO/location" ]; then
    echo "   no location set: sunrise/sunset default to Aachen, Germany."
    echo "   re-run with --location \"LAT LON\" (decimal degrees) to change it."
fi

say "Hyprland"
link "$REPO/hypr/system1.lua" "$HYPR/themes/system1/init.lua"
link "$REPO/hypr/loader.lua" "$HYPR/themes/loader.lua"

echo
if grep -q 'require("themes.loader")' "$HYPR/hyprland.lua"; then
    say "done. Switch it on with  $S1/bin/theme-switch system1"
else
    say "almost done. Add this line to the end of $HYPR/hyprland.lua:"
    echo
    echo '    require("themes.loader")'
    echo
    echo "then reload Hyprland and run  $S1/bin/theme-switch system1"
fi
