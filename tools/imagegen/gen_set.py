"""Generate candidate images for every pet pose with the phoebechobi LoRA.

    python gen_set.py            # every pose, 2 seeds each
    python gen_set.py sit lie    # only these poses
    python gen_set.py walk_a --seeds 5 --start 300

Files land in ComfyUI/output as set_<pose>_s<seed>_00001_.png.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = HERE.parent / "gen.py"
BASE = "phoebechobi, 1girl, solo, chibi, full body, {}, simple background, green background"
NEGATIVE = (
    "worst quality, low quality, lowres, bad anatomy, bad hands, extra limbs, text, watermark, signature, "
    "multiple views, shadow, floor, ground, grass, gradient background, scenery, object, chair, hat"
)

POSES = {
    "stand": "standing, arms at sides, closed mouth, :3, looking at viewer",
    "talk": "standing, arms at sides, open mouth, smile, looking at viewer",
    "think": "standing, hand on own chin, thinking, looking up, closed mouth",
    "walk_a": "walking, from side, profile, leg forward, closed mouth",
    "walk_b": "walking, from side, profile, legs apart, mid-stride, closed mouth",
    "fall": "falling, midair, arms up, open mouth, surprised, floating hair",
    "resist": "midair, flailing, outstretched arms, legs apart, >_<, closed eyes, open mouth, struggling",
    "hang": "midair, limp, arms at sides, legs dangling, feet off ground, closed mouth, half-closed eyes",
    "sit": "sitting, spread legs, closed mouth, :3, looking at viewer",
    "look_up": "sitting, spread legs, looking up, head tilted back, open mouth",
    "lie": "lying, on stomach, closed eyes, sleeping, from side",
    "creep": "lying, on stomach, crawling, arm reaching forward, from side, open eyes",
    "squat": "squatting, crouching, hands on own knees, closed mouth",
    "wall": "from side, profile, climbing, arms up, reaching up, legs bent, clinging",
    "wall2": "from side, profile, midair, hugging, outstretched arms, arms forward, knees up, legs bent, closed mouth",
    "ceiling2": "midair, arms up, hands up, reaching up, stretching, legs dangling, straight-on, closed mouth, looking at viewer",
    "ceiling":"hanging, arms up, both arms raised straight up, legs dangling, feet off ground, closed mouth",
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("poses", nargs="*")
    p.add_argument("--seeds", type=int, default=2)
    p.add_argument("--start", type=int, default=100)
    a = p.parse_args()
    for pose in a.poses or POSES:
        for seed in range(a.start, a.start + a.seeds):
            subprocess.run(
                [sys.executable, str(GEN), BASE.format(POSES[pose]), "--name", f"set_{pose}_s{seed}",
                 "--seed", str(seed), "--lora", "phoebechobi.safetensors", "--negative", NEGATIVE],
                check=True,
            )


if __name__ == "__main__":
    main()
