"""Cuts a sprite sheet into Shimeji-style frames the pet can load.

Example (a 5x2 sheet: stand, walk, walk, fall, sit / lie, held, held, wall, ceiling):

    uv run python tools/import_sheet.py sheet.png --grid 5x2 \
        --names 1,2,3,4,11,21,7,8,13,23 --character phoebe

Each cell has its background removed (unless the sheet is already
transparent), is trimmed, scaled by one factor shared by every frame, and
placed where the pet expects it: feet on the bottom centre, wall poses to the
right of the centre line, ceiling poses hanging from y=48 (of 128), held poses
hanging from the top. A _preview.png is written next to the frames.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

WALL = {"shime12", "shime13", "shime14"}
CEILING = {"shime23", "shime24", "shime25"}
HELD = {f"shime{n}" for n in range(5, 11)}
CEILING_Y = 48 / 128  # where the ceiling line sits inside a frame
_NAME = re.compile(r"^(shime([1-9]|[1-3]\d|4[0-6])|talk[1-9]|think[1-9])$")


def parse_names(spec: str, cells: int) -> list[str | None]:
    """'1,2,-,talk1' -> frame name per cell in reading order; '-' skips a cell."""
    names: list[str | None] = []
    for token in (t.strip() for t in spec.split(",")):
        if token in ("", "-"):
            names.append(None)
            continue
        name = f"shime{token}" if token.isdigit() else token.lower()
        if not _NAME.match(name):
            raise ValueError(f"'{token}' is not a frame: use 1-46, talk1, think1 or '-'")
        if name in names:
            raise ValueError(f"'{token}' is listed twice")
        names.append(name)
    if len(names) > cells:
        raise ValueError(f"{len(names)} names for only {cells} cells")
    return names + [None] * (cells - len(names))


def _is_transparent(image: Image.Image) -> bool:
    return "A" in image.getbands() and image.getchannel("A").getextrema()[0] < 250


def _border_colour(image: Image.Image) -> tuple[int, int, int]:
    rgb = np.asarray(image.convert("RGB"))
    edge = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    return tuple(int(v) for v in np.median(edge, axis=0))


def remove_background(cell: Image.Image, bg: tuple[int, int, int], tolerance: int) -> Image.Image:
    """Clear background-coloured pixels reachable from the cell's edge.

    Flooding from the edge keeps the same colour where the character encloses
    it (eyes, clothes), which a plain colour key would punch holes in.
    """
    rgb = np.asarray(cell.convert("RGB")).astype(np.int16)
    near = (np.abs(rgb - np.array(bg, dtype=np.int16)).max(axis=2) <= tolerance)
    h, w = near.shape
    outside = np.zeros((h, w), dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    def visit(y: int, x: int) -> None:
        if near[y, x] and not outside[y, x]:
            outside[y, x] = True
            queue.append((y, x))

    for x in range(w):
        visit(0, x)
        visit(h - 1, x)
    for y in range(h):
        visit(y, 0)
        visit(y, w - 1)
    while queue:
        y, x = queue.popleft()
        if y > 0:
            visit(y - 1, x)
        if y < h - 1:
            visit(y + 1, x)
        if x > 0:
            visit(y, x - 1)
        if x < w - 1:
            visit(y, x + 1)
    alpha = Image.fromarray(np.where(outside, 0, 255).astype(np.uint8))
    # One pixel of erosion drops the rim that is half character, half background.
    alpha = alpha.filter(ImageFilter.MinFilter(3))
    result = cell.convert("RGBA")
    result.putalpha(alpha)
    return result


def _content(image: Image.Image) -> Image.Image | None:
    box = image.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    return image.crop(box) if box else None


def _place(content: Image.Image, name: str, size: int, scale: float) -> Image.Image:
    w, h = content.size
    if name in WALL:
        scale = min(scale, (size / 2) / w)
    elif name in CEILING:
        scale = min(scale, size * (1 - CEILING_Y) / h)
    w, h = max(1, round(w * scale)), max(1, round(h * scale))
    content = content.resize((w, h), Image.LANCZOS)
    if name in WALL:
        x, y = size // 2, size - h
    elif name in CEILING:
        x, y = (size - w) // 2, round(size * CEILING_Y)
    elif name in HELD:
        x, y = (size - w) // 2, 0
    else:
        x, y = (size - w) // 2, size - h
    frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    frame.paste(content, (x, y))
    return frame


def _preview(frames: dict[str, Image.Image], size: int, path: Path) -> None:
    cols = min(8, len(frames))
    rows = -(-len(frames) // cols)
    sheet = Image.new("RGBA", (cols * size, rows * size), (140, 160, 185, 255))
    draw = ImageDraw.Draw(sheet)
    for i, (name, frame) in enumerate(frames.items()):
        x, y = (i % cols) * size, (i // cols) * size
        sheet.alpha_composite(frame, (x, y))
        draw.rectangle((x, y, x + size - 1, y + size - 1), outline=(40, 50, 80, 255))
        draw.line((x + size // 2, y, x + size // 2, y + 6), fill=(40, 50, 80, 255))
        draw.text((x + 4, y + 3), name, fill=(20, 20, 40, 255))
    sheet.save(path)


def import_sheet(
    sheet_path: Path,
    out_dir: Path,
    cols: int,
    rows: int,
    names: list[str | None],
    size: int = 128,
    bg: str = "auto",
    tolerance: int = 40,
    fill: float = 0.92,
) -> list[Path]:
    """Write one PNG per named cell into out_dir and return their paths."""
    sheet = Image.open(sheet_path)
    sheet.load()
    keep_alpha = bg == "none" or _is_transparent(sheet)
    if not keep_alpha:
        colour = _border_colour(sheet) if bg == "auto" else tuple(int(bg.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    cell_w, cell_h = sheet.width // cols, sheet.height // rows
    contents: dict[str, Image.Image] = {}
    for index, name in enumerate(names[: cols * rows]):
        if name is None:
            continue
        left, top = (index % cols) * cell_w, (index // cols) * cell_h
        cell = sheet.crop((left, top, left + cell_w, top + cell_h))
        cell = cell.convert("RGBA") if keep_alpha else remove_background(cell, colour, tolerance)
        content = _content(cell)
        if content is None:
            print(f"cell {index + 1} ({name}) is empty; skipped", file=sys.stderr)
            continue
        contents[name] = content
    if not contents:
        return []
    # One scale for every frame, or the character would grow and shrink as it moves.
    scale = size * fill / max(max(c.width, c.height) for c in contents.values())
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {name: _place(content, name, size, scale) for name, content in contents.items()}
    written = []
    for name, frame in frames.items():
        path = out_dir / f"{name}.png"
        frame.save(path)
        written.append(path)
    _preview(frames, size, out_dir / "_preview.png")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cut a sprite sheet into pet frames.")
    parser.add_argument("sheet", type=Path)
    parser.add_argument("--grid", required=True, help="COLSxROWS, e.g. 5x2")
    parser.add_argument("--names", required=True, help="frame per cell in reading order, e.g. 1,2,3,-,11,talk1")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--character", help="write to assets/<name>")
    target.add_argument("--out", type=Path, help="write to this folder")
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--bg", default="auto", help="auto, none, or a colour like #00ff00")
    parser.add_argument("--tolerance", type=int, default=40, help="how far from the background colour still counts as background (0-255)")
    parser.add_argument("--fill", type=float, default=0.92, help="how much of the frame the largest pose fills")
    args = parser.parse_args(argv)
    try:
        cols, rows = (int(v) for v in args.grid.lower().split("x"))
        names = parse_names(args.names, cols * rows)
        if args.bg not in ("auto", "none") and not re.fullmatch(r"#?[0-9a-fA-F]{6}", args.bg):
            raise ValueError("--bg must be auto, none or a colour like #00ff00")
    except ValueError as error:
        parser.error(str(error))
    out = args.out or Path(__file__).resolve().parent.parent / "assets" / args.character
    written = import_sheet(args.sheet, out, cols, rows, names, args.size, args.bg, args.tolerance, args.fill)
    print(f"wrote {len(written)} frames to {out}")
    print(f"check {out / '_preview.png'}")
    if args.character:
        print(f'then set character = "{args.character}" in config.toml')
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
