#!/usr/bin/env python3
"""Claude Code status line for System 1: context use, usage limits and
whether the prompt cache is still warm. Uses the terminal's ANSI palette
(red, default foreground, the "blue" slot as grey), so it follows kitty
when System 1 switches between light and dark."""
import json, os, sys, time

RED, GREY, BOLD, RST, FG = "\033[31m", "\033[34m", "\033[1m", "\033[0m", "\033[39m"
SEP = f" {GREY}·{RST} "

def k(n):
    return f"{n/1_000_000:.1f}M" if n >= 1_000_000 else f"{round(n/1000)}k"

def pct(label, p, extra=""):
    col = RED + BOLD if p >= 80 else FG
    return f"{GREY}{label}{RST} {col}{p:.0f}%{RST}{extra}"

def reset(ts, now):
    if not ts: return ""
    left = ts - now
    if left <= 0: return ""
    t = time.localtime(ts)
    when = time.strftime("%H:%M", t) if left < 86400 else time.strftime("%a %H:%M", t)
    return f" {GREY}↻{when}{RST}"

def main():
    raw = sys.stdin.read()
    try: d = json.loads(raw)
    except ValueError: d = {}
    if os.environ.get("SYSTEM1_STATUSLINE_DEBUG"):
        with open(os.path.expanduser("~/.cache/claude-statusline.json"), "w") as f: f.write(raw)
    now = time.time()
    parts = []

    cw = d.get("context_window") or {}
    used, size = cw.get("used_percentage"), cw.get("context_window_size")
    if used is not None:
        tok = (cw.get("total_input_tokens") or 0)
        cu = cw.get("current_usage") or {}
        if cu:
            tok = sum(cu.get(x) or 0 for x in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        extra = f" {GREY}{k(tok)}/{k(size)}{RST}" if size else ""
        parts.append(pct("ctx", used, extra))
    elif size:
        parts.append(f"{GREY}ctx{RST} 0% {GREY}0/{k(size)}{RST}")

    rl = d.get("rate_limits") or {}
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        b = rl.get(key)
        if b and b.get("used_percentage") is not None:
            parts.append(pct(label, b["used_percentage"], reset(b.get("resets_at"), now)))
    if not rl:
        parts.append(f"{GREY}limits n/a{RST}")

    pc = d.get("prompt_cache")
    if pc is not None:
        exp = pc.get("expires_at")
        if pc.get("warm") and (exp is None or exp > now):
            left = ""
            if exp:
                s = int(exp - now); left = f" {GREY}{s//60}:{s%60:02d}{RST}"
            hit = pc.get("hit_ratio")
            hit = f" {GREY}{hit*100:.0f}% hit{RST}" if hit is not None else ""
            parts.append(f"{GREY}cache{RST} {FG}warm{RST}{left}{hit}")
        else:
            parts.append(f"{GREY}cache{RST} {RED}{BOLD}cold{RST}")

    model = (d.get("model") or {}).get("display_name")
    if model: parts.append(f"{GREY}{model}{RST}")
    print(SEP.join(parts))

main()
