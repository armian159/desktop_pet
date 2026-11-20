"""Turn the chosen generated images into pet frames in assets/phoebe.

Run from the pet project so Pillow and numpy are available:

    cd D:\\study\\phoebe-slack-bot
    uv run python D:\\study\\ComfyUI\\sprites\\build.py

Each image gets its own background colour removed and loose bits (shadows, zzz,
sparkles) dropped. Floor animations share one scale; air and wall poses get a
size picked per pose so the head stays about the same size.
"""
import functools
import sys
import tomllib
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

PET = Path(r"D:\study\phoebe-slack-bot")
OUTPUT = Path(__file__).resolve().parent.parent / "ComfyUI_windows_portable" / "ComfyUI" / "output"
sys.path.insert(0, str(PET / "tools"))
import import_sheet as tool  # noqa: E402

SIZE = 128
WORK = 512  # images are shrunk to this before cutting; plenty for 128px frames

# Floor animations are all grown from one standing image (see vid_set.py), so the camera
# and the character's size are the same in every clip. They are cut with ONE scale and ONE
# foot line taken from the standing image, never per clip, or the head would change size
# between actions.
# name -> (prefix, first frame, last frame)
FLOOR = {
    "idle": ("wan_idle", 1, 32),
    "talk": ("wan_talk", 1, 32),
    "to_walk": ("u_towalk", 1, 17),
    "walk": ("u_walk", 1, 32),
    "to_sit": ("u_tosit", 1, 17),
    "sit": ("u_sit", 1, 32),
    "to_lie": ("u_tolie", 1, 33),
    "creep": ("u_creep", 1, 32),
    "to_sleep": ("u_tosleep", 1, 33),
    "sleep": ("u_sleep", 1, 32),
    "think": ("u_think", 1, 32),
    "look": ("u_look", 1, 32),
    "land": ("u_land", 13, 22),  # only the rise from the crouch back to standing
}
# Lying down the body is longer than the frame is wide, so these clips are drawn a little
# smaller; the clip that leads into them shrinks gradually so the change is not seen.
LYING = {"creep", "to_sleep", "sleep"}
INTO_LYING = "to_lie"
ONE_WAY = {"to_walk", "to_sit", "to_lie", "to_sleep", "land"}  # clips that do not end where they began
ANCHOR = ("wan_idle", 1)  # the standing image every floor clip starts from
STAND_HEIGHT = 118  # how tall that standing image is drawn, in px

# Single frames some actions still ask for by number: frame -> floor frame to copy.
# shime26 is what a sitting pet shows when the mouse comes near, so it has to be a sitting picture.
ALIASES = {"shime1": "idle01", "shime11": "sit01", "shime26": "sit01"}

# Stills for poses in the air or on a wall, which have no video clip.
# frame -> (image, flip, rotate degrees, target height in px, or ("w", px) for width)
FRAMES = {
    "shime7": ("hang_s101", False, -12, 94),
    "shime9": ("hang_s101", False, -26, 94),
    "shime8": ("hang_s101", False, 12, 94),
    "shime10": ("hang_s101", False, 26, 94),
}

# Air and wall animations, each cut from its own video (ComfyUI/output/<prefix>_#####_.png).
# They start from other images, so each needs its own size to bring the head to the floor size.
# name -> (prefix, frame count, flip, size of the first frame: height in px or ("w", px), where it sits)
SEQUENCES = {
    "resist": ("wan_resist", 32, False, 98, "held"),
    "fall": ("wan_fall", 32, False, 104, "floor"),
    "climb": ("wan_climb", 32, False, 112, "wall"),
    "ceiling": ("wan_ceiling", 32, False, 114, "ceiling"),
}

# What the character's own actions.toml changes from the project default: section -> {key: value}.
# A change that names a clip which has no frames yet is skipped. "{name_r}" is a clip played backwards.
ACTION_CHANGES = {
    "action.stand": {"frames": "{idle}", "frame_ms": "62", "next": '["to_walk", "to_run", "sit_down", "look_up", "stand"]'},
    "action.walk": {"frames": "{walk}", "frame_ms": "62", "speed": "40", "next": '["from_walk"]'},
    "action.run": {"frames": "{walk}", "frame_ms": "21", "speed": "150", "next": '["from_walk"]'},
    "action.look_up": {"frames": "{look}", "frame_ms": "62", "duration": "[2, 2]"},
    "action.sit": {"frames": "{sit}", "frame_ms": "62", "next": '["stand_up", "sit_dangle", "lie_down"]'},
    "action.sit_dangle": {"frames": "{sit}", "frame_ms": "62", "offset": "[0, 0]"},
    "action.lie": {"frames": "{sleep}", "frame_ms": "62", "next": '["wake_up"]'},
    "action.creep": {"frames": "{creep}", "frame_ms": "62", "next": '["doze_off", "get_up"]'},
    "action.wall_hold": {"frames": '["climb01"]', "offset": "{climb_offset}"},
    "action.wall_climb": {"frames": "{climb}", "frame_ms": "62", "offset": "{climb_offset}"},
    "action.ceiling_hold": {"frames": '["ceiling01"]', "offset": "{ceiling_offset}"},
    "action.ceiling_move": {"frames": "{ceiling}", "frame_ms": "62", "offset": "{ceiling_offset}"},
    "special.fall": {"frames": "{fall}", "frame_ms": "62"},
    "special.land": {"frames": "{land}", "frame_ms": "40"},
    "special.resist": {"frames": "{resist}", "frame_ms": "62"},
    "special.think": {"frames": "{think}", "frame_ms": "62"},
    "special.talk": {"frames": "{talk}", "frame_ms": "62"},
}
DROPPED = {"action.sit_spin"}  # needs pictures this character does not have

# Actions only this character has: the moves between two poses.
# name -> (frames, frame_ms, weight, idle_weight, next, extra line)
TRANSITIONS = {
    "to_walk": ("{to_walk}", 62, 5, 4, ["walk"], "intro = true"),
    "to_run": ("{to_walk}", 31, 1, 0.2, ["run"], "intro = true"),
    "from_walk": ("{to_walk_r}", 62, 1, 1, ["stand"], ""),
    "sit_down": ("{to_sit}", 62, 2, 4, ["sit"], ""),
    "stand_up": ("{to_sit_r}", 62, 6, 4, ["stand"], ""),
    "lie_down": ("{to_lie}", 62, 1, 2, ["creep", "doze_off"], ""),
    "get_up": ("{to_lie_r}", 62, 1, 1, ["sit"], ""),
    "doze_off": ("{to_sleep}", 62, 2, 4, ["lie"], ""),
    "wake_up": ("{to_sleep_r}", 62, 1, 1, ["creep", "get_up"], ""),
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
    cleared_image = tool.remove_background(image, tool._border_colour(image), 40)
    return tool._content(largest_piece(cleared_image))


@functools.cache
def cleared(prefix: str, index: int) -> Image.Image:
    """One video frame with its background and loose bits removed."""
    image = Image.open(OUTPUT / f"{prefix}_{index:05d}_.png").convert("RGB")
    return largest_piece(tool.remove_background(image, tool._border_colour(image), 40))


def _box(image: Image.Image) -> tuple[int, int, int, int]:
    return image.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()


def floor_placement() -> tuple[float, float, float]:
    """Scale and offset that draw the standing image STAND_HEIGHT tall, centred, feet on the bottom edge."""
    left, top, right, bottom = _box(cleared(*ANCHOR))
    scale = STAND_HEIGHT / (bottom - top)
    return scale, SIZE / 2 - (left + right) / 2 * scale, SIZE - bottom * scale


def lying_fit(placement: tuple[float, float, float], clips: list[tuple[str, int, int]]) -> tuple[float, float]:
    """How much to shrink and slide the lying clips so the stretched-out body fits the frame."""
    scale, dx, _ = placement
    boxes = [_box(cleared(prefix, i)) for prefix, first, last in clips for i in range(first, last + 1)]
    left, right = min(b[0] for b in boxes) * scale + dx, max(b[2] for b in boxes) * scale + dx
    shrink = min(1.0, (SIZE - 2) / (right - left))
    centre = SIZE / 2 + ((left + right) / 2 - SIZE / 2) * shrink  # where the body's middle lands after shrinking
    return shrink, SIZE / 2 - centre


def cut_floor(prefix, first, last, placement, start=(1.0, 0.0), end=(1.0, 0.0)) -> list[Image.Image]:
    """Cut a floor clip exactly where the standing image sits, so clips join without a jump.

    `start` and `end` are (shrink, slide) for the first and last frame; frames between move
    evenly from one to the other. Shrinking is about the bottom centre, where the feet are.
    """
    scale, dx, dy = placement
    frames = []
    for i in range(first, last + 1):
        t = (i - first) / max(1, last - first)
        shrink, slide = (start[k] + (end[k] - start[k]) * t for k in (0, 1))
        piece = cleared(prefix, i)
        size = (round(piece.width * scale * shrink), round(piece.height * scale * shrink))
        x = (dx - SIZE / 2) * shrink + SIZE / 2 + slide
        y = (dy - SIZE) * shrink + SIZE
        frame = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        frame.paste(piece.resize(size, Image.LANCZOS), (round(x), round(y)))
        frames.append(frame)
    return frames


def cut_sequence(prefix: str, count: int, flip: bool, target, where: str = "floor") -> tuple[list[Image.Image], tuple[int, int]]:
    """Cut every frame with one shared box and scale, so nothing jitters between frames.

    Also returns the action offset that puts the picture against its wall or ceiling: the
    program draws the frame shifted by it, so the body's edge, not the frame's, meets the screen edge.
    """
    pieces = []
    for i in range(1, count + 1):
        piece = cleared(prefix, i)
        pieces.append(piece.transpose(Image.FLIP_LEFT_RIGHT) if flip else piece)
    boxes = [_box(f) for f in pieces]
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    if isinstance(target, tuple):
        scale = target[1] / (boxes[0][2] - boxes[0][0])
    else:
        scale = target / (boxes[0][3] - boxes[0][1])
    # The whole motion has to fit the frame.
    scale = min(scale, SIZE / (box[2] - box[0]), SIZE / (box[3] - box[1]))
    w, h = round((box[2] - box[0]) * scale), round((box[3] - box[1]) * scale)
    spot = {
        "floor": ((SIZE - w) // 2, SIZE - h),
        "wall": (SIZE - w, SIZE - h),  # against the frame's right edge; the offset below brings it to the wall
        "ceiling": ((SIZE - w) // 2, SIZE - h),
        "held": ((SIZE - w) // 2, 0),
    }[where]
    frames = []
    for f in pieces:
        content = f.crop(box).resize((w, h), Image.LANCZOS)
        frame = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        frame.paste(content, spot)
        frames.append(frame)
    offset = {"wall": (w - SIZE, 0), "ceiling": (0, h - SIZE)}.get(where, (0, 0))
    return frames, offset


def steady(frames: list[Image.Image], loop: bool, reach: int = 2, tolerance: float = 28.0) -> list[Image.Image]:
    """Calm the shimmer of generated video: blend each pixel with the same pixel in the frames
    just before and after, but only where it barely differs, so real movement stays sharp.
    A loop wraps around; a one-way move stops at its ends."""
    pre = []
    for f in frames:
        a = np.asarray(f).astype(np.float32)
        a[..., :3] *= a[..., 3:4] / 255.0  # premultiplied, so see-through pixels add no colour
        pre.append(a)
    soft = [np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(1))).astype(np.float32) for a in pre]
    result = []
    for i in range(len(pre)):
        total, weight = pre[i].copy(), np.ones(pre[i].shape[:2], np.float32)
        for k in range(-reach, reach + 1):
            j = i + k
            if k == 0 or (not loop and not 0 <= j < len(pre)):
                continue
            j %= len(pre)
            near = np.exp(-((np.abs(soft[j] - soft[i]).max(-1) / tolerance) ** 2)) * (0.8 if abs(k) == 1 else 0.5)
            total += pre[j] * near[..., None]
            weight += near
        mixed = total / weight[..., None]
        alpha = mixed[..., 3:4]
        mixed[..., :3] = np.where(alpha > 0, mixed[..., :3] * 255.0 / np.maximum(alpha, 1e-3), 0)
        result.append(Image.fromarray(np.clip(mixed + 0.5, 0, 255).astype(np.uint8), "RGBA"))
    return result


def _fill(text: str, lists: dict[str, str]) -> str | None:
    """`text` with its {clip} replaced, or None while that clip has no frames."""
    if text.startswith("{") and text.strip("{}") not in lists:
        return None
    return text.format(**lists) if text.startswith("{") else text


def write_actions(out: Path, lists: dict[str, str]) -> None:
    """Copy the project's actions.toml with this character's animations and transitions put in."""
    made = [name for name, spec in TRANSITIONS.items() if _fill(spec[0], lists)]
    section, lines = "", []
    for line in (PET / "actions.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("["):
            section = line.strip("[]")
        if section in DROPPED:
            continue
        key = line.split("=")[0].strip()
        changes = ACTION_CHANGES.get(section, {})
        change = changes.get(key) if "=" in line else None
        if change and any(_fill(v, lists) is None for v in changes.values()):
            change = None  # this action's clip is missing: leave the whole action as it was
        if change and key == "next":
            targets = tomllib.loads(f"n = {change}")["n"]
            if any(t in TRANSITIONS and t not in made for t in targets):
                change = None
        if key == "next" and not change:  # nothing may point at an action that was dropped
            kept = [t for t in tomllib.loads(line)["next"] if f"action.{t}" not in DROPPED]
            line = "next = [" + ", ".join(f'"{t}"' for t in kept) + "]"
        lines.append(f"{key} = {_fill(change, lists)}" if change else line)
    lines += ["", "# 자세 사이를 잇는 전환 동작 (tools/imagegen/build.py 가 만든다)"]
    for name in made:
        frames, frame_ms, weight, idle_weight, following, extra = TRANSITIONS[name]
        lines += [
            "",
            f"[action.{name}]",
            'surface = "floor"',
            f"frames = {_fill(frames, lists)}",
            f"frame_ms = {frame_ms}",
            "speed = 0",
            "duration = [0.1, 0.1]",  # shorter than the clip: it plays exactly once
            f"weight = {weight}",
            f"idle_weight = {idle_weight}",
            "next = [" + ", ".join(f'"{n}"' for n in following) + "]",
        ] + ([extra] if extra else [])
    (out / "actions.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    out = PET / "assets" / "phoebe"
    out.mkdir(parents=True, exist_ok=True)
    lists: dict[str, str] = {}
    written: dict[str, Image.Image] = {}

    def save(name: str, frames: list[Image.Image]) -> None:
        frames = steady(frames, loop=name not in ONE_WAY)
        names = [f"{name}{i:02d}" for i in range(1, len(frames) + 1)]
        for frame_name, frame in zip(names, frames):
            frame.save(out / f"{frame_name}.png")
            written[frame_name] = frame
        lists[name] = "[" + ", ".join(f'"{n}"' for n in names) + "]"
        lists[name + "_r"] = "[" + ", ".join(f'"{n}"' for n in reversed(names)) + "]"
        print(f"wrote {len(frames)} {name} frames")

    placement = floor_placement()
    ready = {n: clip for n, clip in FLOOR.items() if (OUTPUT / f"{clip[0]}_{clip[2]:05d}_.png").exists()}
    lying = (1.0, 0.0)
    if INTO_LYING in ready:
        prefix, _, last = ready[INTO_LYING]
        lying = lying_fit(placement, [(prefix, last, last)] + [ready[n] for n in LYING if n in ready])
    for name in FLOOR:
        if name not in ready:
            print(f"no frames for {name} yet; skipped")
        elif name in LYING:
            save(name, cut_floor(*ready[name], placement, lying, lying))
        elif name == INTO_LYING:
            save(name, cut_floor(*ready[name], placement, end=lying))
        else:
            save(name, cut_floor(*ready[name], placement))
    for name, (prefix, count, flip, target, where) in SEQUENCES.items():
        if not (OUTPUT / f"{prefix}_{count:05d}_.png").exists():
            print(f"no frames for {name} yet; skipped")
            continue
        frames, offset = cut_sequence(prefix, count, flip, target, where)
        save(name, frames)
        lists[name + "_offset"] = f"[{offset[0]}, {offset[1]}]"
    write_actions(out, lists)
    cache: dict[str, Image.Image] = {}
    frames = {}
    for frame, source in ALIASES.items():
        if source in written:
            frames[frame] = written[source]
            frames[frame].save(out / f"{frame}.png")
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
    frames.update({f"{name}01": written[f"{name}01"] for name in lists if f"{name}01" in written})
    tool._preview(frames, SIZE, out / "_preview.png")
    print(f"wrote {len(written) + len(frames)} frames to {out}")
    print(f"check {out / '_preview.png'}")


if __name__ == "__main__":
    main()
