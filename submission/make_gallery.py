"""Export the submission gallery at 3:2 (Devpost media requirement).

Every source PNG is already rendered by Coal itself. This only resizes and
letterboxes to 1500x1000 so the gallery is uniform; nothing is redrawn.

    py -3.15 make_gallery.py
"""
from __future__ import annotations

import os

from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "assets")
DST = os.path.join(SRC, "gallery")
W, H = 1500, 1000          # 3:2
BG = (12, 14, 20)          # matches the dark rendering palette


def fit(im: Image.Image) -> Image.Image:
    """Contain the image inside 3:2 on a dark field, never cropping."""
    im = im.convert("RGB")
    scale = min(W / im.width, H / im.height)
    im = im.resize((max(1, round(im.width * scale)),
                    max(1, round(im.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), BG)
    canvas.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
    return canvas


def main() -> int:
    os.makedirs(DST, exist_ok=True)
    made = []
    for name in sorted(os.listdir(SRC)):
        if not name.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        src = os.path.join(SRC, name)
        out = os.path.join(DST, os.path.splitext(name)[0] + "-3x2.png")
        fit(Image.open(src)).save(out, "PNG", optimize=True)
        kb = os.path.getsize(out) // 1024
        made.append((name, kb))
        flag = "  OVER 5MB" if kb > 5120 else ""
        print(f"  {name:24s} -> {os.path.basename(out):28s} {kb:5d} KB{flag}")

    print(f"\n{len(made)} images in {os.path.relpath(DST, HERE)}")
    over = [n for n, kb in made if kb > 5120]
    if over:
        print("OVER LIMIT:", ", ".join(over))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
