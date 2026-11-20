"""Queue one text-to-image job on the local ComfyUI server and wait for it.

    python gen.py "1girl, chibi, full body, standing" --name stand --seed 1
"""
import argparse
import json
import time
import urllib.request

URL = "http://127.0.0.1:8188"
QUALITY = "masterpiece, best quality, absurdres, "
NEGATIVE = "worst quality, low quality, lowres, bad anatomy, bad hands, extra limbs, text, watermark, signature, multiple views"


def call(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(URL + path, body, {"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=30) as reply:
        return json.loads(reply.read())


def workflow(a):
    model = ["1", 0]
    clip = ["1", 1]
    nodes = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": a.ckpt}},
    }
    if a.lora:
        nodes["2"] = {
            "class_type": "LoraLoader",
            "inputs": {"lora_name": a.lora, "strength_model": a.lora_strength, "strength_clip": a.lora_strength, "model": model, "clip": clip},
        }
        model, clip = ["2", 0], ["2", 1]
    nodes.update({
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": QUALITY + a.prompt, "clip": clip}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": a.negative, "clip": clip}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": a.width, "height": a.height, "batch_size": a.batch}},
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": model, "positive": ["3", 0], "negative": ["4", 0], "latent_image": ["5", 0],
                "seed": a.seed, "steps": a.steps, "cfg": a.cfg,
                "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": a.name}},
    })
    return nodes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("prompt")
    p.add_argument("--name", default="out")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--steps", type=int, default=28)
    p.add_argument("--cfg", type=float, default=6.0)
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--height", type=int, default=1024)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--ckpt", default="Illustrious-XL-v1.0.safetensors")
    p.add_argument("--lora", default="")
    p.add_argument("--lora-strength", type=float, default=0.9)
    p.add_argument("--negative", default=NEGATIVE)
    a = p.parse_args()

    started = time.time()
    job = call("/prompt", {"prompt": workflow(a)})["prompt_id"]
    while True:
        time.sleep(1)
        try:
            history = call(f"/history/{job}")
        except OSError:  # the server stops answering while it loads a model
            continue
        if job in history:
            break
    entry = history[job]
    if entry["status"]["status_str"] != "success":
        raise SystemExit(json.dumps(entry["status"], ensure_ascii=False, indent=1))
    files = [i["filename"] for out in entry["outputs"].values() for i in out.get("images", [])]
    print(f"{time.time() - started:.1f}s", *files)


if __name__ == "__main__":
    main()
