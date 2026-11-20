"""Turn the chosen generated images into pet frames in assets/phoebe.

Run from the pet project so Pillow and numpy are available:

    cd D:\\study\\phoebe-slack-bot
    uv run python D:\\study\\ComfyUI\\sprites\\build.py

Each image gets its own background colour removed, loose bits (shadows, zzz,
sparkles) dropped, and is scaled to a size picked per pose so the head stays
about the same size from frame to frame.
"""
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

PET = Path(r"D:\study\phoebe-slack-bot")
OUTPUT = Path(__file__).resolve().parent.parent / "ComfyUI_windows_portable" / "ComfyUI" / "output"
sys.path.insert(0, str(PET / "tools"))
import import_sheet as tool  # noqa: E402

SIZE = 128
WORK = 512  # images are shrunk to this before cutting; plenty for 128px frames

# frame -> (image, flip, rotate degrees, target height in px, or ("w", px) for width)
FRAMES = {
    "shime1": ("stand_s100", False, 0, 118),
    "talk1": ("talk_s100", False, 0, 118),
    "talk2": ("stand_s100", False, 0, 118),
    "think1": ("think_s101", False, 0, 118),
    "shime2": ("walk_b_s101", True, 0, 118),
    "shime3": ("walk_a_s101", True, 0, 118),
    "shime4": ("fall_s101", False, 0, 90),
    "shime5": ("resist_s101", False, 0, 88),
    "shime6": ("resist_s101", True, 0, 88),
    "shime7": ("hang_s101", False, -12, 94),
    "shime9": ("hang_s101", False, -26, 94),
    "shime8": ("hang_s101", False, 12, 94),
    "shime10": ("hang_s101", False, 26, 94),
    "shime11": ("sit_s100", False, 0, 86),
    "shime26": ("look_up_s100", False, 0, 86),
    "shime18": ("squat_s100", False, 0, 84),
    "shime21": ("lie_s100", False, 0, ("w", 124)),
    "shime20": ("creep_s100", False, 0, ("w", 124)),
    "shime13": ("ceiling2_s201", False, 0, 86),
    "shime23": ("ceiling2_s200", False, 0, 96),
}


# Animations cut from generated video frames (ComfyUI/output/<prefix>_#####_.png).
# name -> (prefix, frame count, flip, size of the first frame: height in px or ("w", px), where it sits)
# Remove a line here to fall back to the still frame for that action.
SEQUENCES = {
    "walk": ("wan_walk1", 32, True, 118, "floor"),
    "idle": ("wan_idle", 32, False, 118, "floor"),
    "talk": ("wan_talk", 32, False, 118, "floor"),
    "think": ("wan_think", 32, False, 118, "floor"),
    "sit": ("wan_sit", 32, False, 86, "floor"),
    "sleep": ("wan_sleep", 32, False, ("w", 124), "floor"),
    "creep": ("wan_creep", 32, False, ("w", 124), "floor"),
    "resist": ("wan_resist", 32, False, 88, "held"),
    "fall": ("wan_fall", 32, False, 90, "floor"),
    "climb": ("wan_climb", 32, False, 86, "wall"),
    "ceiling": ("wan_ceiling", 32, False, 96, "ceiling"),
}

# What the character's own actions.toml changes from the project default: section -> {key: value}.
# A change that names a sequence missing from SEQUENCES is skipped.
ACTION_CHANGES = {
    "action.walk": {"frames": "{walk}", "frame_ms": "62", "speed": "40"},
    "action.run": {"frames": "{walk}", "frame_ms": "21", "speed": "150"},
    "action.stand": {"frames": "{idle}", "frame_ms": "62"},
    "action.sit": {"frames": "{sit}", "frame_ms": "62"},
    "action.sit_dangle": {"frames": "{sit}", "frame_ms": "62", "offset": "[0, 0]"},
    "action.lie": {"frames": "{sleep}", "frame_ms": "62"},
    "action.creep": {"frames": "{creep}", "frame_ms": "62"},
    "action.wall_climb": {"frames": "{climb}", "frame_ms": "62"},
    "action.ceiling_move": {"frames": "{ceiling}", "frame_ms": "62"},
    "special.fall": {"frames": "{fall}", "frame_ms": "62"},
    "special.resist": {"frames": "{resist}", "frame_ms": "62"},
    "special.think": {"frames": "{think}", "frame_ms": "62"},
    "special.talk": {"frames": "{talk}", "frame_ms": "62"},
}


def largest_piece(image: Image.Image) -> Image.Image:
    """Keep only the biggest connected blob of opaque pixels."""
    alpha = np.asarray(image.getchannel("A")) > 8
    h, w = alpha.shape
    label = np.zeros((h, w), dtype=np.int32)
    best, best_size, current = 0, 0, 0
    for sy, sx in zip(*np.nonzero(alpha)):
        if label[sy, sx]:
            continue
        current += 1
        label[sy, sx] = current
        queue, count = deque([(sy, sx)]), 0
        while queue:
            y, x = queue.popleft()
            count += 1
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and alpha[ny, nx] and not label[ny, nx]:
                    label[ny, nx] = current
                    queue.append((ny, nx))
        if count > best_size:
            best, best_size = current, count
    keep = Image.fromarray(np.where(label == best, 255, 0).astype(np.uint8))
    result = image.copy()
    result.putalpha(Image.composite(image.getchannel("A"), Image.new("L", image.size, 0), keep))
    return result


def cut(name: str) -> Image.Image:
    image = Image.open(OUTPUT / f"set_{name}_00001_.png").convert("RGB").resize((WORK, WORK), Image.LANCZOS)
    cleared = tool.remove_background(image, tool._border_colour(image), 40)
    return tool._content(largest_piece(cleared))


def cut_sequence(prefix: str, count: int, flip: bool, target, where: str = "floor") -> list[Image.Image]:
    """Cut every frame with one shared box and scale, so nothing jitters between frames."""
    cleared = []
    for i in range(1, count + 1):
        image = Image.open(OUTPUT / f"{prefix}_{i:05d}_.png").convert("RGB")
        piece = largest_piece(tool.remove_background(image, tool._border_colour(image), 40))
        cleared.append(piece.transpose(Image.FLIP_LEFT_RIGHT) if flip else piece)
    boxes = [f.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox() for f in cleared]
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    if isinstance(target, tuple):
        scale = target[1] / (boxes[0][2] - boxes[0][0])
    else:
        scale = target / (boxes[0][3] - boxes[0][1])
    # The whole motion has to fit the frame (and the half/part of it a wall or ceiling pose may use).
    room_w = SIZE // 2 if where == "wall" else SIZE
    room_h = round(SIZE * (1 - tool.CEILING_Y)) if where == "ceiling" else SIZE
    scale = min(scale, room_w / (box[2] - box[0]), room_h / (box[3] - box[1]))
    w, h = round((box[2] - box[0]) * scale), round((box[3] - box[1]) * scale)
    spot = {
        "floor": ((SIZE - w) // 2, SIZE - h),
        "wall": (SIZE // 2, SIZE - h),
        "ceiling": ((SIZE - w) // 2, round(SIZE * tool.CEILING_Y)),
        "held": ((SIZE - w) // 2, 0),
    }[where]
    frames = []
    for f in cleared:
        content = f.crop(box).resize((w, h), Image.LANCZOS)
        frame = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        frame.paste(content, spot)
        frames.append(frame)
    return frames


def write_actions(out: Path, lists: dict[str, str]) -> None:
    """Copy the project's actions.toml with this character's longer animations swapped in."""
    section, lines = "", []
    for line in (PET / "actions.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("["):
            section = line.strip("[]")
        key = line.split("=")[0].strip()
        changes = ACTION_CHANGES.get(section, {})
        needed = changes.get("frames", "").strip("{}")
        change = changes.get(key) if "=" in line and (not needed or needed in lists) else None
        lines.append(f"{key} = {change.format(**lists)}" if change else line)
    (out / "actions.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    out = PET / "assets" / "phoebe"
    out.mkdir(parents=True, exist_ok=True)
    lists = {}
    for name, (prefix, count, flip, target, where) in SEQUENCES.items():
        if not (OUTPUT / f"{prefix}_{count:05d}_.png").exists():
            print(f"no frames for {name} yet; skipped")
            continue
        names = [f"{name}{i:02d}" for i in range(1, count + 1)]
        for frame_name, frame in zip(names, cut_sequence(prefix, count, flip, target, where)):
            frame.save(out / f"{frame_name}.png")
        lists[name] = "[" + ", ".join(f'"{n}"' for n in names) + "]"
        print(f"wrote {count} {name} frames")
    write_actions(out, lists)
    cache: dict[str, Image.Image] = {}
    frames = {}
    for frame, (name, flip, angle, target) in FRAMES.items():
        content = cache.get(name)
        if content is None:
            content = cache[name] = cut(name)
        if flip:
            content = content.transpose(Image.FLIP_LEFT_RIGHT)
        if isinstance(target, tuple):
            scale = target[1] / content.width
        else:
            scale = target / content.height
        content = content.resize((max(1, round(content.width * scale)), max(1, round(content.height * scale))), Image.LANCZOS)
        if angle:
            content = tool._content(content.rotate(angle, Image.BICUBIC, expand=True))
        if content.width > SIZE or content.height > SIZE:
            content.thumbnail((SIZE, SIZE), Image.LANCZOS)
        frames[frame] = tool._place(content, frame, SIZE, 1.0)
        frames[frame].save(out / f"{frame}.png")
    tool._preview(frames, SIZE, out / "_preview.png")
    print(f"wrote {len(frames)} frames to {out}")


if __name__ == "__main__":
    main()
