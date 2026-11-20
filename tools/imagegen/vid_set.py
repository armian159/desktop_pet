"""Generate the looping animation clips for the pet, one after another.

    python vid_set.py            # every clip that has no frames yet
    python vid_set.py sit sleep  # only these (overwrites nothing: bump --seed for a retry)

Frames land in ComfyUI/output as wan_<clip>_#####_.png.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMFY = HERE.parent / "ComfyUI_windows_portable" / "ComfyUI"
VID = HERE.parent / "vid.py"

# clip -> (start image in output/, what happens)
CLIPS = {
    "idle": ("set_stand_s100", "A chibi girl stands still facing the viewer, breathing gently, her body bobs up and down slightly, she blinks, her long hair sways a little"),
    "talk": ("set_stand_s100", "A chibi girl stands facing the viewer and talks, her mouth opens and closes again and again, she nods slightly while speaking"),
    "think": ("set_think_s101", "A chibi girl stands thinking with her hand on her chin, she tilts her head slowly from side to side, eyes looking up"),
    "sit": ("set_sit_s100", "A chibi girl sits on the ground with legs spread, breathing gently, she sways slightly from side to side and blinks"),
    "sleep": ("set_lie_s100", "A chibi girl sleeps lying on her stomach, eyes closed, her body rises and falls slowly with each breath"),
    "creep": ("set_creep_s100", "A chibi girl crawls on her stomach, her arms reach forward and pull one after the other, her body wiggles"),
    "resist": ("set_resist_s101", "A chibi girl struggles in midair, flailing her arms and kicking her legs quickly, eyes shut tight"),
    "fall": ("set_fall_s101", "A chibi girl falls through the air, her arms wave, her hair and clothes flutter upward in the wind"),
    "climb": ("set_ceiling2_s201", "A chibi girl climbs straight upward, her raised arms reach up one after the other, her legs kick alternately"),
    "ceiling": ("set_ceiling2_s200", "A chibi girl hangs from above by her raised hands, her legs dangle and swing gently from side to side"),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("clips", nargs="*")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    for clip in a.clips or CLIPS:
        if not a.clips and (COMFY / "output" / f"wan_{clip}_00001_.png").exists():
            continue
        image, prompt = CLIPS[clip]
        shutil.copy(COMFY / "output" / f"{image}_00001_.png", COMFY / "input" / f"{clip}_start.png")
        print(clip, flush=True)
        subprocess.run([sys.executable, str(VID), f"{clip}_start.png", prompt, "--name", f"wan_{clip}", "--seed", str(a.seed), "--loop"], check=True)


if __name__ == "__main__":
    main()
