"""Generate the animation clips for the pet, one after another.

    python vid_set.py            # every clip that has no frames yet
    python vid_set.py sit sleep  # only these (overwrites nothing: bump --seed for a retry)

Frames land in ComfyUI/output as <clip>_#####_.png.

The floor clips all grow from ONE standing image. A move between two poses (stand -> sit) is
generated first, and one of its frames becomes the start and end of the loop that follows
(sitting). That keeps the head and body the same size in every clip, which separately
generated start images never do, and gives the pet the moves between poses for free.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMFY = HERE.parent / "ComfyUI_windows_portable" / "ComfyUI"
VID = HERE.parent / "vid.py"
SAME = ", her big head keeps exactly the same size"

# clip -> (start: an image in output/, or (clip, frame) to continue from that clip; loops?; what happens)
# Order matters: a clip must come after the one it continues from.
CLIPS = {
    # floor: everything continues from the standing image
    "wan_idle": ("set_stand_s100", True, "A chibi girl stands still facing the viewer, breathing gently, her body bobs up and down slightly, she blinks, her long hair sways a little"),
    "wan_talk": ("set_stand_s100", True, "A chibi girl stands facing the viewer and talks, her mouth opens and closes again and again, she nods slightly while speaking"),
    "u_look": ("set_stand_s100", True, "A chibi girl standing facing the viewer tilts her head back and looks up at the sky with curious eyes, then lowers her head again"),
    "u_land": ("set_stand_s100", True, "A chibi girl standing facing the viewer quickly crouches down low bending her knees deeply, then stands back up straight"),
    "u_towalk": ("set_stand_s100", False, "A chibi girl standing facing the viewer turns her whole body to face the left side of the screen, then walks in place in side view, her legs step alternately and her arms swing, her big head and small body keep exactly the same size and proportions"),
    "u_walk": (("u_towalk", 17), True, "A chibi girl seen from the side walks in place toward the left with big lively steps, her knees lift high and her legs stride wide alternately, her arms swing back and forth, her long hair bounces" + SAME),
    "u_tothink": ("set_stand_s100", False, "A chibi girl standing facing the viewer raises one hand to her chin and tilts her head in thought, eyes looking up, then holds the thinking pose still"),
    "u_think": (("u_tothink", 33), True, "A chibi girl stands thinking with her hand on her chin, she tilts her head slowly from side to side, eyes looking up, blinking"),
    "u_tosit": ("set_stand_s100", False, "A chibi girl standing facing the viewer slowly bends her knees and sits down on the ground with her legs stretched forward toward the viewer, then stays sitting still" + SAME),
    "u_sit": (("u_tosit", 17), True, "A chibi girl sits on the ground facing the viewer, breathing gently, she sways slightly from side to side and blinks"),
    "u_tolie": (("u_tosit", 17), False, "A chibi girl sitting on the ground turns to the left and lies down flat on her stomach, her body stretched out sideways with her head on the left and her feet on the right, her eyes stay open" + SAME),
    "u_creep": (("u_tolie", 33), True, "A chibi girl lying flat on her stomach crawls in place toward the left, her arms reach forward and pull one after the other, her body wiggles" + SAME),
    "u_tosleep": (("u_tolie", 33), False, "A chibi girl lying flat on her stomach slowly closes her eyes, lowers her head onto the ground and falls asleep, then sleeps still with her eyes closed"),
    "u_sleep": (("u_tosleep", 33), True, "A chibi girl sleeps lying flat on her stomach with her eyes closed, her body rises and falls slowly with each breath"),
    "u_towall": (("u_towalk", 17), False, "A chibi girl seen from the side facing left reaches both hands forward and grabs a vertical wall at the left edge of the picture, then climbs straight up the wall in side view, her hands reach up one after the other and her feet push against the wall alternately, her body stays close to the wall" + SAME),
    "u_wall": (("u_towall", 33), True, "A chibi girl seen from the side climbs straight up a vertical wall at the left edge of the picture, her hands reach up one after the other and her feet step up alternately, her body stays close to the wall and bobs slightly, her long hair sways" + SAME),
    # gestures: she stays in place and inside the frame (no high jumps, no arms far above the head),
    # and ends back in the standing pose
    "g_sleepy": ("set_stand_s100", True, "A chibi girl standing facing the viewer stays in place, yawns widely with one hand over her mouth, then rubs her sleepy eyes with her fist" + SAME),
    "g_sulky": ("set_stand_s100", True, "A chibi girl standing facing the viewer stays in place, puffs out her cheeks sulkily, then turns her head away sharply to the side with a pout" + SAME),
    "g_bored": ("set_stand_s100", True, "A chibi girl standing facing the viewer stays in place, taps the floor with her toes while swaying slowly from side to side, bored" + SAME),
    "g_happy": ("set_stand_s100", True, "A chibi girl standing facing the viewer stays in place, clasps her hands together happily and bounces lightly on her toes, her feet barely leave the ground" + SAME),
    "g_calm": ("set_stand_s100", True, "A chibi girl standing facing the viewer stays in place, closes her eyes and puts her hands together in a short calm prayer, then opens her eyes again" + SAME),
    "g_thrown": ("set_stand_s100", True, "A chibi girl standing facing the viewer stays in place, holds her head with both hands and wobbles dizzily, her eyes are swirling" + SAME),
    "g_released": ("set_stand_s100", True, "A chibi girl standing facing the viewer stays in place, puts one hand on her chest and lets out a long sigh of relief" + SAME),
    "g_lunch": ("set_stand_s100", True, "A chibi girl standing facing the viewer stays in place, rubs her tummy with one hand and looks shyly embarrassed" + SAME),
    "g_evening": ("set_stand_s100", True, "A chibi girl standing facing the viewer stays in place and waves one hand at shoulder height in greeting, smiling" + SAME),
    "g_late_night": ("set_stand_s100", True, "A chibi girl standing facing the viewer stays in place and waves one hand at shoulder height with sleepy eyes, then nods off for a moment" + SAME),
    "g_woke": (("u_tolie", 33), True, "A chibi girl lying flat on her stomach with her eyes open lifts her head and upper body, stretches both arms forward, then lies back down the same way" + SAME),
    # in the air and on the ceiling: each from its own image (build.py sizes them to match)
    "wan_resist": ("set_resist_s101", True, "A chibi girl struggles in midair, flailing her arms and kicking her legs quickly, eyes shut tight"),
    "wan_fall": ("set_fall_s101", True, "A chibi girl falls through the air, her arms wave, her hair and clothes flutter upward in the wind"),
    "wan_ceiling": ("set_ceiling2_s200", True, "A chibi girl hangs from above by her raised hands, her legs dangle and swing gently from side to side"),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("clips", nargs="*")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    for clip in a.clips or CLIPS:
        if not a.clips and (COMFY / "output" / f"{clip}_00001_.png").exists():
            continue
        start, loop, prompt = CLIPS[clip]
        source = f"{start}_00001_.png" if isinstance(start, str) else f"{start[0]}_{start[1]:05d}_.png"
        shutil.copy(COMFY / "output" / source, COMFY / "input" / f"{clip}_start.png")
        print(clip, flush=True)
        command = [sys.executable, str(VID), f"{clip}_start.png", prompt, "--name", clip, "--seed", str(a.seed)]
        subprocess.run(command + (["--loop"] if loop else []), check=True)


if __name__ == "__main__":
    main()
