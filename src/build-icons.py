#!/usr/bin/env python3
"""Build the System 1 icon themes for Qt/KDE apps (Dolphin, file dialogs).

1-bit pixel icons: at 32 px and up, folders and documents are drawn as
outlines on a pixel grid with a small pixelated Tabler glyph inside (after
the 1984 Finder); smaller sizes, devices and actions are Tabler icons on
the 16x16 grid, like the bar. Every icon is a single-colour SVG whose pixels
sit exactly on the grid, coloured through KDE's ColorScheme-Text class, so
KDE apps tint them with the colour scheme (selection included); other Qt apps
get the default ink. Writes ../icons/System1-Light and ../icons/System1-Dark
(black and white ink), inheriting breeze and breeze-dark for everything not
covered. Every mimetype and places icon breeze has gets a System 1 stand-in,
so no blue folder or coloured file icon shows through.

    python3 build-icons.py
"""
import logging
import os
import shutil
import warnings
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

warnings.filterwarnings("ignore")
logging.getLogger("fontTools").setLevel(logging.ERROR)
FONT = Path("/usr/share/noctalia/assets/fonts/noctalia-tabler.ttf")
BREEZE = Path("/usr/share/icons/breeze")
OUT = Path(__file__).resolve().parent.parent / "icons"
THEMES = {"System1-Light": ("#000000", "breeze"), "System1-Dark": ("#ffffff", "breeze-dark")}
SIZES = [16, 22, 24, 32, 48, 64, 96, 128, 256]
CONTEXTS = {"places": "Places", "mimetypes": "MimeTypes", "devices": "Devices", "actions": "Actions"}

# ---------------------------------------------------------------- glyphs

# the 24-unit Tabler viewbox sits at x 10.5..1010.5, y -100..900 in font units
X0, Y_TOP = 10.5, 900.0
cmap = {name: cp for cp, name in TTFont(str(FONT)).getBestCmap().items()}
_glyphs = {}


def glyph(name, n):
    """Tabler icon `name` resampled onto an n x n grid: set of (x, y)."""
    key = (name, n)
    if key not in _glyphs:
        size = n * 32
        pil = ImageFont.truetype(str(FONT), size, layout_engine=ImageFont.Layout.BASIC)
        img = Image.new("L", (size, size), 0)
        s = size / 1000.0
        ImageDraw.Draw(img).text((-X0 * s, Y_TOP * s), chr(cmap[name]), font=pil, fill=255, anchor="ls")
        px = img.resize((n, n), Image.BOX).load()
        _glyphs[key] = {(x, y) for y in range(n) for x in range(n) if px[x, y] >= 0.45 * 255}
    return _glyphs[key]


# ---------------------------------------------------------------- drawing

class Grid:
    def __init__(self, g):
        self.g, self.on = g, set()

    def px(self, x, y):
        if 0 <= x < self.g and 0 <= y < self.g:
            self.on.add((x, y))

    def hline(self, x0, x1, y):
        for x in range(x0, x1 + 1):
            self.px(x, y)

    def vline(self, x, y0, y1):
        for y in range(y0, y1 + 1):
            self.px(x, y)

    def diag(self, x0, y0, x1, y1):
        steps = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(steps + 1):
            self.px(round(x0 + (x1 - x0) * i / steps), round(y0 + (y1 - y0) * i / steps))

    def dither(self, x0, y0, x1, y1):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if (x + y) % 2 == 0:
                    self.px(x, y)

    def stamp(self, pixels, cx, cy, n):
        ox, oy = cx - n // 2, cy - n // 2
        for x, y in pixels:
            self.px(ox + x, oy + y)

    def clear(self, x0, y0, x1, y1):
        self.on = {(x, y) for x, y in self.on if not (x0 <= x <= x1 and y0 <= y <= y1)}


def folder(g, inner=None):
    """Finder-style folder on a g grid (designed at 32), optional glyph inside."""
    f = lambda v: round(v * g / 32)
    d = Grid(g)
    left, right, top, bottom = f(2), f(29), f(9), f(26)
    tab_r, tab_top = f(12), f(6)
    d.hline(left, tab_r, tab_top)
    d.vline(left, tab_top, bottom)
    d.diag(tab_r, tab_top, tab_r + (top - tab_top), top)
    d.hline(tab_r + (top - tab_top), right, top)
    d.vline(right, top, bottom)
    d.hline(left, right, bottom)
    d.dither(left + 2, tab_top + 2, tab_r - 1, top - 1)     # shaded tab
    d.hline(left, right, top + f(2))                         # the front flap
    if inner:
        n = f(13)
        d.stamp(glyph(inner, n), (left + right + 1) // 2, (top + f(2) + bottom + 1) // 2, n)
    return d


def document(g, inner=None):
    """Page with a folded corner; text lines when there is no glyph, empty for "_blank"."""
    f = lambda v: round(v * g / 32)
    d = Grid(g)
    left, right, top, bottom, ear = f(6), f(25), f(2), f(29), f(6)
    d.hline(left, right - ear, top)
    d.diag(right - ear, top, right, top + ear)
    d.vline(right, top + ear, bottom)
    d.hline(left, right, bottom)
    d.vline(left, top, bottom)
    d.vline(right - ear, top, top + ear)
    d.hline(right - ear, right, top + ear)
    if inner == "_blank":
        pass
    elif inner:
        n = f(14)
        d.stamp(glyph(inner, n), (left + right + 1) // 2, f(18), n)
    else:
        step = max(2, f(3))
        for i, y in enumerate(range(top + ear + step, bottom - step + 1, step)):
            end = right - f(3) - (f(5) if i % 3 == 2 else 0)
            d.hline(left + f(3), end, y)
    return d


def pixel_icon(name, s):
    """Tabler icon: below 32 px on the 16 grid (padded), like the bar; from 32 px
    on the same 1-pixel line grid as the folders and documents."""
    if s < 32:
        d = Grid(s)
        d.stamp(glyph(name, 16), s // 2, s // 2, 16)
        return d
    g = s if s < 64 else 32
    n = round(g * 0.75)
    d = Grid(g)
    d.stamp(glyph(name, n), g // 2, g // 2, n)
    return upscale(d, s)


def upscale(grid, s):
    unit = s // grid.g
    if unit == 1:
        return grid
    big = Grid(s)
    for x, y in grid.on:
        for dy in range(unit):
            for dx in range(unit):
                big.px(x * unit + dx, y * unit + dy)
    return big


def render(design, s):
    """design = (kind, glyph) -> Grid of s x s pixels."""
    kind, inner = design
    if kind == "glyph":
        return pixel_icon(inner, s)
    if s < 32:
        return pixel_icon(small_for(design), s)
    g = s if s < 64 else 32
    return upscale(folder(g, inner) if kind == "folder" else document(g, inner), s)


def small_for(design):
    kind, inner = design
    if kind == "folder":
        return inner or "folder"
    return SMALL_DOC.get(inner, "file-text" if inner is None else inner)


SMALL_DOC = {"code": "file-code", "music": "file-music", "archive": "file-zip", "pdf": "file-type-pdf",
             "typography": "file-typography", "file-spreadsheet": "file-spreadsheet", "_blank": "file"}


def svg(grid, s, ink):
    d = []
    for y in range(s):
        x = 0
        while x < s:
            if (x, y) not in grid.on:
                x += 1
                continue
            start = x
            while x < s and (x, y) in grid.on:
                x += 1
            d.append(f"M{start} {y}h{x - start}v1h{start - x}z")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" viewBox="0 0 {s} {s}">'
            f'<style type="text/css" id="current-color-scheme">.ColorScheme-Text{{color:{ink};}}</style>'
            f'<path class="ColorScheme-Text" fill="currentColor" shape-rendering="crispEdges" d="{"".join(d)}"/></svg>\n')


# ---------------------------------------------------------------- names

FOLDER_GLYPHS = {
    "user-home": "home", "folder-home": "home", "user-desktop": "device-desktop", "folder-desktop": "device-desktop",
    "folder-documents": "file-text", "folder-download": "download", "folder-downloads": "download",
    "folder-music": "music", "folder-sound": "music", "library-music": "music", "folder-pictures": "photo",
    "folder-picture": "photo", "folder-images": "photo", "folder-image": "photo", "folder-videos": "movie",
    "folder-video": "movie", "folder-network": "network", "folder-remote": "network", "folder-cloud": "cloud",
    "folder-git": "brand-git", "folder-development": "code", "folder-script": "code", "folder-html": "code",
    "folder_html": "code", "folder-locked": "lock", "folder-encrypted": "lock", "folder-favorites": "star",
    "folder-bookmark": "bookmark", "folder-book": "book", "folder-library": "book", "folder-games": "device-gamepad-2",
    "folder-publicshare": "world", "folder-public": "world", "folder-recent": "clock", "folder-templates": "file-plus",
    "folder-text": "file-text", "folder-txt": "file-text", "folder-tar": "archive", "folder-mail": "mail",
}
PLACES_GLYPHS = {"user-trash": "trash", "user-trash-full": "trash", "network-workgroup": "network",
                 "network-server": "server-2", "favorites": "star", "desktop": "device-desktop",
                 "certificate-server": "key", "start-here-kde": "home", "start-here-kde-plasma": "home"}


def mime_design(name):
    n = name.lower()
    has = lambda *ks: any(k in n for k in ks)
    if n.startswith("inode-directory") or n == "folder":
        return ("folder", None)
    if n.startswith("image-"):
        return ("doc", "photo")
    if n.startswith("video-") or has("flash-video", "realmedia", "mplayer"):
        return ("doc", "movie")
    if n.startswith("audio") or has("ogg", "-cda"):
        return ("doc", "music")
    if n.startswith("font-") or has("-font-"):
        return ("doc", "typography")
    if has("markdown"):
        return ("doc", "markdown")
    if has("pdf", "postscript", "epub", "djvu", "-dvi"):
        return ("doc", "pdf")
    if has("iso", "cd-image", "diskimage", "disk-image", "qemu-disk", "vdi-disk", "squashfs", "-cue", "ms-wim"):
        return ("doc", "disc")
    if has("zip", "tar", "compress", "gzip", "bzip", "-xz", "7z", "rar", "lzma", "lzop", "zstd", "-arj", "-lha",
           "cpio", "archive", "-ace", "-zoo", "-arc", "-ar.", "jar", "-deb", "rpm", "-pak", "xpinstall",
           "package", "appimage", "-snap", "flatpak", "-apk", "-tzo"):
        return ("doc", "archive")
    if has("pgp", "pkcs", "x509", "certificate", "pem-key", "pkix", "keys", "-cert"):
        return ("doc", "key")
    if has("shellscript", "executable-script", "-awk", "-m4") or n in ("text-x-script",):
        return ("doc", "terminal-2")
    if has("executable", "sharedlib", "ms-dos", "msdownload", "-object", "-core", "-rom", "bytecode"):
        return ("doc", "binary")
    if has("desktop", "ms-shortcut", "mswinurl"):
        return ("doc", "app-window")
    if has("spreadsheet", "excel", "calc", "gnumeric", "-csv", "quattropro", "applix-spreadsheet", "sheet"):
        return ("doc", "file-spreadsheet")
    if has("presentation", "powerpoint", "impress", "slide"):
        return ("doc", "presentation")
    if has("sql", "database", "kexi", "access"):
        return ("doc", "database")
    if n in ("text-plain", "text-x-generic", "text-x-log", "text-x-readme", "text-x-changelog", "text-x-copying",
             "text-x-authors", "text-x-install", "text-x-nfo"):
        return ("doc", None)
    if has("text-x-", "javascript", "json", "xml", "toml", "yaml", "html", "css", "java", "python", "perl",
           "ruby", "php", "gdscript", "godot", "patch", "diff", "makefile", "cmake", "qml", "-kcsrc", "relaxng",
           "xsd", "xslt", "rss", "atom", "mathml"):
        return ("doc", "code")
    if n.startswith("text-"):
        return ("doc", None)
    if has("word", "writer", "opendocument.text", "rtf", "abiword", "kword", "lyx", "-chm", "office",
           "wps-office", "msonenote"):
        return ("doc", None)
    return ("doc", "_blank")


DEVICES = {"drive-harddisk": "server-2", "drive-multidisk": "server-2", "drive-partition": "server-2",
           "drive-removable-media": "usb", "media-flash": "device-sd-card", "drive-optical": "disc",
           "media-optical": "disc", "media-write": "disc", "computer-laptop": "device-laptop",
           "computer": "device-desktop", "monitor": "device-desktop", "video-display": "device-desktop",
           "phone": "device-mobile", "smartphone": "device-mobile", "printer": "printer", "cups": "printer",
           "camera": "camera", "input-keyboard": "keyboard", "input-mouse": "mouse", "input-game": "device-gamepad-2",
           "audio-headphones": "headphones", "audio-headset": "headphones", "cpu": "cpu", "memory": "cpu"}

ACTIONS = {
    "go-previous": "arrow-left", "go-next": "arrow-right", "go-up": "arrow-up", "go-down": "arrow-down",
    "go-home": "home", "go-parent-folder": "arrow-up", "edit-find": "search", "system-search": "search",
    "application-menu": "menu-2", "open-menu": "menu-2", "view-split-left-right": "layout-columns",
    "view-list-icons": "layout-grid", "view-list-details": "list", "view-list-tree": "list-tree",
    "view-list-compact": "layout-list", "view-refresh": "refresh", "document-new": "file-plus",
    "folder-new": "folder-plus", "edit-copy": "copy", "edit-cut": "cut", "edit-paste": "clipboard",
    "edit-delete": "trash", "edit-rename": "pencil", "edit-undo": "arrow-back-up", "edit-redo": "arrow-forward-up",
    "list-add": "plus", "list-remove": "minus", "window-close": "x", "tab-close": "x", "dialog-close": "x",
    "edit-clear": "eraser", "tab-new": "square-plus", "configure": "settings", "settings-configure": "settings",
    "view-hidden": "eye-off", "view-visible": "eye", "view-preview": "eye", "bookmark-new": "bookmark",
    "document-open": "folder-open", "document-save": "device-floppy", "document-save-as": "device-floppy",
    "document-properties": "info-circle", "edit-select-all": "select-all", "utilities-terminal": "terminal-2",
    "zoom-in": "zoom-in", "zoom-out": "zoom-out", "view-sort": "arrows-sort", "view-filter": "filter",
    "go-jump-today": "calendar-event", "view-calendar-day": "calendar", "document-open-recent": "clock",
    "view-history": "clock", "trash-empty": "trash", "folder-open": "folder-open",
}


def breeze_names(context):
    names = set()
    for d in (BREEZE / context).glob("*"):
        if d.is_dir() and "@" not in d.name:
            names |= {p.stem for p in d.glob("*.svg")}
    return names


def catalogue():
    """{context: {icon name: design}} with design = (kind, glyph)."""
    places = {}
    for n in breeze_names("places") | set(FOLDER_GLYPHS) | {"folder", "folder-open", "inode-directory"}:
        if n in PLACES_GLYPHS:
            places[n] = ("glyph", PLACES_GLYPHS[n])
        elif n.startswith("folder") or n in FOLDER_GLYPHS or n in ("stock_folder", "inode-directory"):
            places[n] = ("folder", FOLDER_GLYPHS.get(n))
    mimes = {n: mime_design(n) for n in breeze_names("mimetypes") | {"unknown", "text-plain", "inode-directory"}}
    devices = {}
    for n in breeze_names("devices"):
        for prefix, g in DEVICES.items():
            if n.startswith(prefix):
                devices[n] = ("glyph", g)
                break
    actions = {n: ("glyph", g) for n, g in ACTIONS.items()}
    return {"places": places, "mimetypes": mimes, "devices": devices, "actions": actions}


# ---------------------------------------------------------------- output

def main():
    cat = catalogue()
    missing = {g for ctx in cat.values() for k, g in ctx.values() if g and g != "_blank" and g not in cmap}
    assert not missing, f"glyphs not in the Tabler font: {missing}"
    designs = sorted({d for ctx in cat.values() for d in ctx.values()}, key=str)
    key = lambda d: f"{d[0]}-{d[1] or 'plain'}"
    rendered = {(d, s): render(d, s) for d in designs for s in SIZES}

    for theme, (ink, parent) in THEMES.items():
        root = OUT / theme
        shutil.rmtree(root, ignore_errors=True)
        dirs = []
        for s in SIZES:
            store = root / f"{s}" / "_"
            store.mkdir(parents=True)
            for d in designs:
                (store / f"{key(d)}.svg").write_text(svg(rendered[(d, s)], s, ink))
            for ctx, icons in cat.items():
                sub = root / f"{s}" / ctx
                sub.mkdir()
                dirs.append((f"{s}/{ctx}", s, CONTEXTS[ctx]))
                for name, d in icons.items():
                    os.symlink(f"../_/{key(d)}.svg", sub / f"{name}.svg")
        lines = ["[Icon Theme]", f"Name={theme}", "Comment=System 1: 1-bit pixel icons", f"Inherits={parent},hicolor",
                 "Directories=" + ",".join(p for p, _, _ in dirs), ""]
        for path, s, ctx in dirs:
            lines += [f"[{path}]", f"Size={s}", f"Context={ctx}", "Type=Fixed", ""]
        (root / "index.theme").write_text("\n".join(lines))
    n = sum(len(c) for c in cat.values())
    print(f"{n} icon names, {len(designs)} designs, {len(SIZES)} sizes -> {OUT}/{{{','.join(THEMES)}}}")


if __name__ == "__main__":
    main()
