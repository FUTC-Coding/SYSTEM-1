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
ICONS="$HOME/.local/share/icons"
GF="https://raw.githubusercontent.com/google/fonts/main/ofl"
DM_VERSION=1.500

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
             "$HOME/.config/noctalia/palettes/System1.json" "$HOME/.config/noctalia/system1.toml" \
             "$ICONS/System1-Light" "$ICONS/System1-Dark"; do
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
# true if FAMILY is installed as a font Noctalia can render; web-font copies
# (.woff/.woff2) show up in fontconfig, but Noctalia can't use them
have_font() {
    local have; have="$(fc-match -f '%{family[0]}|%{file}' "$1")"
    [ "${have%%|*}" = "$1" ] && [[ "$have" != *.woff && "$have" != *.woff2 ]]
}
if ! have_font "Departure Mono"; then
    echo "   downloading Departure Mono $DM_VERSION"
    tmp="$(mktemp -d)"
    curl -fsSL "https://github.com/rektdeckard/departure-mono/releases/download/v$DM_VERSION/DepartureMono-$DM_VERSION.zip" -o "$tmp/dm.zip"
    python3 -I -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$tmp/dm.zip" "$tmp"
    cp "$tmp/DepartureMono-$DM_VERSION/DepartureMono-Regular.otf" "$FONTS/"
    cp "$tmp/DepartureMono-$DM_VERSION/LICENSE" "$FONTS/OFL-departuremono.txt"
    rm -rf "$tmp"
fi
if ! have_font "DotGothic16"; then
    echo "   downloading DotGothic16"
    curl -fsSL "$GF/dotgothic16/DotGothic16-Regular.ttf" -o "$FONTS/DotGothic16-Regular.ttf"
    curl -fsSL "$GF/dotgothic16/OFL.txt" -o "$FONTS/OFL-dotgothic16.txt"
fi
link "$REPO/fontconfig/50-system1.conf" "$FC"
fc-cache -f >/dev/null

say "building system1-bg"
make -s -C "$REPO/src" install PREFIX="$REPO"

say "rendering textures"
"$REPO/src/build-assets.sh" >/dev/null

say "pixelating Noctalia's icons"
python3 "$REPO/src/pixel-icons.py"

say "building the file icon themes"
[ -d /usr/share/icons/breeze ] || echo "   breeze icons not found: only the icons System 1 draws itself will show"
python3 "$REPO/src/build-icons.py"
for t in System1-Light System1-Dark; do
    link "$REPO/icons/$t" "$ICONS/$t"
done

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
