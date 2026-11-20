"""Contact sheet of generated candidates: python sheet.py <glob> <out.jpg> [cols]"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUTPUT = Path(__file__).resolve().parent.parent / "ComfyUI_windows_portable" / "ComfyUI" / "output"
pattern, out = sys.argv[1], sys.argv[2]
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 6
cell = 256
files = sorted(OUTPUT.glob(pattern))
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * cell, rows * cell), "gray")
draw = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    im = Image.open(f).convert("RGB").resize((cell, cell))
    x, y = (i % cols) * cell, (i // cols) * cell
    sheet.paste(im, (x, y))
    label = f.name.replace("set_", "").replace("_00001_.png", "")
    draw.rectangle((x, y, x + 8 * len(label) + 6, y + 14), fill="white")
    draw.text((x + 3, y + 2), label, fill="red")
sheet.save(out, quality=88)
print(len(files))
