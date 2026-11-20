"""Copy the reference cuts into the training folder and write one caption per image.

The fixed look (hair, eyes, outfit) is left out of the captions on purpose so it
gets tied to the trigger word; only pose, expression, props and place are tagged.
"""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFS = HERE.parent / "refs"
OUT = HERE / "img"
TRIGGER = "phoebechobi, 1girl, solo, chibi"

CAPTIONS = {
    "01": "full body, standing, outstretched arms, open mouth, angry, fork, strawberry, cake, indoors",
    "02": "full body, lying, on stomach, floating, open mouth, angry, fork, strawberry, indoors",
    "03": "full body, standing on one leg, kicking, leg up, open mouth, strawberry, indoors",
    "04": "full body, standing, hand on own chest, closed mouth, :3, strawberry, indoors",
    "05": "full body, standing, hand on own hip, smug, closed mouth, :3, kitchen",
    "06": "full body, standing, hands on own hips, closed eyes, open mouth, smile, happy, kitchen",
    "07": "full body, sitting, spread legs, smug, closed mouth, :3, simple background",
    "08": "full body, sitting, spread legs, open mouth, simple background",
    "09": "full body, standing, arm up, closed mouth, living room, couch, table",
    "10": "full body, walking, from side, looking to the side, arm up, living room, couch",
    "12": "upper body, from side, profile, sitting, bowl, table, restaurant",
    "13": "standing, holding, milk carton, covering own mouth, closed eyes, >_<, table, restaurant",
    "14": "full body, from behind, standing, hands on own hips, restaurant",
    "15": "full body, from behind, standing, hands on own hips, leaning to the side, restaurant",
}

OUT.mkdir(exist_ok=True)
for key, tags in CAPTIONS.items():
    shutil.copy(REFS / f"ref_{key}.png", OUT / f"ref_{key}.png")
    (OUT / f"ref_{key}.txt").write_text(f"{TRIGGER}, {tags}", encoding="utf-8")
print(len(CAPTIONS), "images")
