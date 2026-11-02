"""Generate the Windows icon (packaging/windows/webways.ico): a white "W" in the wordmark face on a dark square.

    .venv/bin/pip install fonttools pillow
    .venv/bin/python scripts/gen_icon.py
"""
from __future__ import annotations

import io
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "ui/node_modules/@fontsource/bodoni-moda/files/bodoni-moda-latin-700-normal.woff"
OUT = ROOT / "packaging/windows/webways.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(px: int = 1024) -> Image.Image:
    tt = TTFont(FONT)
    tt.flavor = None
    raw = io.BytesIO()
    tt.save(raw)
    raw.seek(0)
    font = ImageFont.truetype(raw, int(px * 0.82))
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, px - 1, px - 1), radius=int(px * 0.18), fill=(17, 17, 17, 255))
    l, t, r, b = d.textbbox((0, 0), "W", font=font)
    d.text(((px - (r - l)) / 2 - l, (px - (b - t)) / 2 - t), "W", font=font, fill=(255, 255, 255, 255))
    return img


if __name__ == "__main__":
    big = render()
    big.save(OUT, sizes=[(s, s) for s in SIZES])
    big.resize((256, 256), Image.LANCZOS).save(OUT.with_suffix(".png"))
    print("wrote", OUT, f"({OUT.stat().st_size} bytes)")
