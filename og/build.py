"""Builds the share pages, link-preview images and icons.

  python og/build.py

Writes, relative to the repo root:
  og.png                      main preview image (from og/card.html)
  <class>/index.html          share page with its own Discord/OG embed, forwards to /#<class>
  <class>/og.png              that class's preview image (from og/class-card.html)
  favicon.ico, apple-touch-icon.png
Rendering uses headless Edge; icons use Pillow.
"""
import html
import json
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SITE = "https://tuckerscottalleborn.github.io/forever-class-codex/"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CLASSES = [
    dict(id="warrior", key=1, name="Warrior", color="#C69B6D", specs="Arms · Fury · Protection", dist=1.5, level="Low–moderate",
         card="The safest pick if you want Classic, just better."),
    dict(id="paladin", key=2, name="Paladin", color="#F48CBA", specs="Holy · Protection · Retribution", dist=4, level="Very high",
         card="One of the biggest overhauls in the game. A real healer, tank or Ret."),
    dict(id="hunter", key=3, name="Hunter", color="#AAD372", specs="Beast Mastery · Marksmanship · Survival", dist=3, level="High",
         card="Three trees that are now different ways to play. Survival is close to a new spec."),
    dict(id="rogue", key=4, name="Rogue", color="#FFF468", specs="Assassination · Combat · Subtlety", dist=2, level="Moderate",
         card="Classic Rogue with clearer specs, not a reinvention."),
    dict(id="priest", key=5, name="Priest", color="#FFFFFF", specs="Discipline · Holy · Shadow", dist=3, level="High",
         card="All three specs become much more complete. Disc is the one to relearn."),
    dict(id="shaman", key=6, name="Shaman", color="#0070DD", specs="Elemental · Enhancement · Restoration", dist=4, level="Very high",
         card="New to the Alliance as Dwarf Shaman, and heavily redesigned besides."),
    dict(id="mage", key=7, name="Mage", color="#3FC7EB", specs="Arcane · Fire · Frost", dist=3, level="High",
         card="The same Classic control chassis, now with an engine for each spec."),
    dict(id="warlock", key=8, name="Warlock", color="#8788EE", specs="Affliction · Demonology · Destruction", dist=3, level="High",
         card="The cleanest three-way spec split among the pure casters."),
    dict(id="druid", key=9, name="Druid", color="#FF7C0A", specs="Balance · Feral · Restoration", dist=4, level="Very high",
         card="Perhaps the deepest Classic-plus redesign. The changes reach the engine level."),
]


def render(src: Path, out: Path, fragment: str = "") -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    profile = tempfile.mkdtemp(prefix="og-edge-")
    try:
        subprocess.run([
            EDGE, "--headless=new", f"--user-data-dir={profile}", "--no-first-run", "--disable-gpu",
            "--hide-scrollbars", "--force-device-scale-factor=1", "--window-size=1200,630",
            "--virtual-time-budget=5000", f"--screenshot={out}", src.as_uri() + fragment,
        ], check=True, capture_output=True, timeout=90)
        # msedge.exe can return before its headless child has written the file
        for _ in range(40):
            if out.exists():
                break
            time.sleep(0.5)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not out.exists():
        raise SystemExit(f"render failed: {out}")
    print("rendered", out.relative_to(ROOT))


def share_page(c: dict) -> str:
    url = f"{SITE}{c['id']}/"
    title = f"{c['name']} · Forever Class Codex"
    desc = f"{c['card']} Distance from Vanilla: {c['level']}. How WoW: Forever changes the {c['name']} compared with Vanilla."
    target = f"../#{c['id']}"
    e = html.escape
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Forever Class Codex">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{url}og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{e(c['name'])}: {e(c['card'])}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:image" content="{url}og.png">
<meta name="theme-color" content="{c['color']}">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="icon" href="../favicon.ico" sizes="32x32">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<meta http-equiv="refresh" content="0; url={target}">
<script>location.replace("{target}")</script>
<style>body{{margin:0;background:#0b0f17;color:#ece2c8;font:18px/1.5 Georgia,serif;display:grid;place-items:center;min-height:100vh;padding:16px;box-sizing:border-box}}a{{color:#ffd100}}</style>
</head>
<body>
<p>Opening the <a href="{target}">{e(c['name'])} section of the Forever Class Codex</a>…</p>
</body>
</html>
"""


def icons() -> None:
    def draw(size: int) -> Image.Image:
        s = size * 4
        im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.19, fill="#0b0f17")
        c, r = s / 2, s * 0.40
        d.polygon([(c, c - r), (c + r, c), (c, c + r), (c - r, c)], outline="#c9a046", width=max(4, int(s * 0.06)))
        r2 = s * 0.20
        d.polygon([(c, c - r2), (c + r2, c), (c, c + r2), (c - r2, c)], fill="#ffd100")
        return im.resize((size, size), Image.LANCZOS)

    draw(180).save(ROOT / "apple-touch-icon.png")
    draw(64).save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("wrote favicon.ico, apple-touch-icon.png")


def main() -> None:
    icons()
    render(HERE / "card.html", ROOT / "og.png")
    for c in CLASSES:
        render(HERE / "class-card.html", ROOT / c["id"] / "og.png", "#" + urllib.parse.quote(json.dumps(c)))
        (ROOT / c["id"] / "index.html").write_text(share_page(c), encoding="utf-8", newline="\n")
        print("wrote", f"{c['id']}/index.html")


if __name__ == "__main__":
    main()
