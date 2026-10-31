#!/usr/bin/env python3
"""Writes themes/system1-{light,dark}.json, Claude Code custom themes in the
System 1 palette (noctalia/System1.json): black/white text, grey for the
secondary text, and red where Claude Code uses its orange and blue accents.
Run again after changing the palette."""
import json, pathlib

here = pathlib.Path(__file__).resolve().parent
# per-mode: text, inverse, strong grey, soft grey, faint grey, red, dark red,
#           bright red, surface, surface2, added bg, removed bg, added word, removed word,
#           dimmed added, dimmed removed, selection
P = {
    "light": dict(text="#000000", inv="#ffffff", grey1="#2a2a2a", grey2="#4a4a4a", grey3="#6a6a6a",
                  border="#8a8a8a", red="#e00000", red2="#b00000", red3="#ff5c5c",
                  surf="#f2f2f2", surf2="#e6e6e6", add="#e0e0e0", rem="#ffd6d6",
                  addw="#bdbdbd", remw="#ff9a9a", addd="#f2f2f2", remd="#ffecec", sel="#ffc0c0",
                  empty="#d0d0d0"),
    "dark":  dict(text="#ffffff", inv="#000000", grey1="#e4e4e4", grey2="#bdbdbd", grey3="#9a9a9a",
                  border="#6a6a6a", red="#ff3b3b", red2="#ff5c5c", red3="#ff8a8a",
                  surf="#141414", surf2="#202020", add="#2a2a2a", rem="#4a0000",
                  addw="#5a5a5a", remw="#8a0000", addd="#141414", remd="#240000", sel="#8a0000",
                  empty="#3a3a3a"),
}

def overrides(c):
    return {
        "text": c["text"], "inverseText": c["inv"],
        "claude": c["red"], "claudeShimmer": c["red3"],
        "clawd_body": c["red"],
        "claudeBlue_FOR_SYSTEM_SPINNER": c["grey1"], "claudeBlueShimmer_FOR_SYSTEM_SPINNER": c["grey3"],
        "permission": c["red"], "permissionShimmer": c["red3"],
        "suggestion": c["red"], "remember": c["red2"],
        "autoAccept": c["red2"], "autoAcceptShimmer": c["red3"],
        "planMode": c["grey1"], "ide": c["grey2"], "skill": c["red2"],
        "bashBorder": c["red"], "background": c["grey2"], "merged": c["red2"],
        "promptBorder": c["border"], "promptBorderShimmer": c["grey3"],
        "inactive": c["grey2"], "inactiveShimmer": c["grey3"], "subtle": c["grey3"],
        "success": c["grey1"], "error": c["red"], "warning": c["red2"], "warningShimmer": c["red3"],
        "diffAdded": c["add"], "diffRemoved": c["rem"],
        "diffAddedDimmed": c["addd"], "diffRemovedDimmed": c["remd"],
        "diffAddedWord": c["addw"], "diffRemovedWord": c["remw"],
        "userMessageBackground": c["surf"], "userMessageBackgroundHover": c["surf2"],
        "composerSidebarBackground": c["surf"], "selectionBg": c["sel"],
        "bashMessageBackgroundColor": c["surf"], "memoryBackgroundColor": c["surf"],
        "rate_limit_fill": c["red"], "rate_limit_empty": c["empty"],
        "fastMode": c["red"], "fastModeShimmer": c["red3"], "effortUltra": c["red"],
        "briefLabelYou": c["text"], "briefLabelClaude": c["red"],
        "professionalBlue": c["grey2"], "chromeYellow": c["grey2"],
    }

for mode, c in P.items():
    theme = {"name": f"System 1 ({mode})", "base": mode, "overrides": overrides(c)}
    (here / "themes" / f"system1-{mode}.json").write_text(json.dumps(theme, indent=2) + "\n")
