"""Generate the desktop app icon (PNG + ICO) with no external assets."""
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src-tauri",
                   "icons")
os.makedirs(OUT, exist_ok=True)

S = 512
img = Image.new("RGBA", (S, S), (12, 14, 20, 255))
d = ImageDraw.Draw(img)

# rounded dark tile
d.rounded_rectangle([16, 16, S - 16, S - 16], radius=96,
                    fill=(20, 24, 36, 255), outline=(94, 230, 168, 255),
                    width=10)

# a small "chip" glyph: body + pins
cx, cy, half = S // 2, S // 2, 110
d.rounded_rectangle([cx - half, cy - half, cx + half, cy + half],
                    radius=24, fill=(12, 14, 20, 255),
                    outline=(94, 230, 168, 255), width=8)
for i in range(4):
    off = -60 + i * 40
    d.line([cx - half - 34, cy + off, cx - half, cy + off],
           fill=(94, 230, 168, 255), width=10)
    d.line([cx + half, cy + off, cx + half + 34, cy + off],
           fill=(94, 230, 168, 255), width=10)
    d.line([cx + off, cy - half - 34, cx + off, cy - half],
           fill=(94, 230, 168, 255), width=10)
    d.line([cx + off, cy + half, cx + off, cy + half + 34],
           fill=(94, 230, 168, 255), width=10)

# "R" mark inside
try:
    f = ImageFont.truetype("arialbd.ttf", 150)
except Exception:
    f = ImageFont.load_default()
d.text((cx, cy - 6), "R", font=f, fill=(232, 236, 244, 255), anchor="mm")

png = os.path.join(OUT, "icon.png")
img.save(png)
img.save(os.path.join(OUT, "icon.ico"),
         sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.resize((128, 128), Image.LANCZOS).save(os.path.join(OUT, "128x128.png"))
img.resize((32, 32), Image.LANCZOS).save(os.path.join(OUT, "32x32.png"))
print("wrote", png)
print("icons:", sorted(os.listdir(OUT)))
