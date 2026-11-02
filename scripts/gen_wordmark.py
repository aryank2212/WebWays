"""Generate the WebWays wordmark and icon as outlined SVG (no font needed to display them).

    .venv/bin/pip install fonttools uharfbuzz
    .venv/bin/python scripts/gen_wordmark.py

Font: Bodoni Moda Bold (SIL OFL 1.1) from the npm package @fontsource/bodoni-moda, the same face the UI loads.
Outputs: docs/assets/webways-wordmark{,-light}.svg (README banner, dark/light) and ui/src/assets/favicon.svg.
"""
from __future__ import annotations

import io
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "ui/node_modules/@fontsource/bodoni-moda/files/bodoni-moda-latin-700-normal.woff"
TRACKING = -0.02                       # em; the UI uses the same letter-spacing so both look identical
NAME = "WebWays"                       # both W capitals: this exact casing everywhere the name is displayed


def shape(text: str):
    tt = TTFont(FONT)
    tt.flavor = None                   # HarfBuzz wants plain sfnt, not WOFF
    raw = io.BytesIO()
    tt.save(raw)
    font = hb.Font(hb.Face(raw.getvalue()))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": False})     # real kerning: "We", "Wa", "ay"
    return tt, buf


def outline(text: str):
    """Return (svg path data, (xmin, ymin, xmax, ymax)) in SVG coordinates (y down)."""
    tt, buf = shape(text)
    gs, order = tt.getGlyphSet(), tt.getGlyphOrder()
    pen, bounds, x = SVGPathPen(gs), BoundsPen(gs), 0
    track = TRACKING * tt["head"].unitsPerEm
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        t = (1, 0, 0, -1, x + pos.x_offset, -pos.y_offset)
        gs[order[info.codepoint]].draw(TransformPen(pen, t))
        gs[order[info.codepoint]].draw(TransformPen(bounds, t))
        x += pos.x_advance + track
    return pen.getCommands(), bounds.bounds


def svg(text: str, fill: str, extra_style: str = "", pad: float = 0.04) -> str:
    d, (x0, y0, x1, y1) = outline(text)
    p = (y1 - y0) * pad
    vb = f"{x0 - p:.0f} {y0 - p:.0f} {x1 - x0 + 2 * p:.0f} {y1 - y0 + 2 * p:.0f}"
    style = f"<style>{extra_style}</style>" if extra_style else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img" aria-label="{text}">'
            f'<title>{text}</title>{style}<path fill="{fill}" d="{d}"/></svg>\n')


if __name__ == "__main__":
    (ROOT / "docs/assets/webways-wordmark.svg").write_text(svg(NAME, "#111111"))
    (ROOT / "docs/assets/webways-wordmark-light.svg").write_text(svg(NAME, "#ffffff"))
    # Favicon: the W alone, dark on light tabs and light on dark tabs.
    (ROOT / "ui/src/assets/favicon.svg").write_text(
        svg("W", "#111111", "@media (prefers-color-scheme: dark){path{fill:#ffffff}}", pad=0.08))
    print("wrote wordmark + favicon")
