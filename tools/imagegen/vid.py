"""Animate one image with Wan 2.2 I2V (4-step Lightning) on the local ComfyUI server.

    python vid.py start.png "the girl walks in place" --name walk --loop

start.png must be in ComfyUI/input. --loop ends on the first image again, so the
frames repeat seamlessly. Frames are saved as PNGs in ComfyUI/output/<name>_#####_.png.
"""
import argparse
import json
import time
import urllib.request

URL = "http://127.0.0.1:8188"
STYLE = ", flat 2D cartoon animation, thick black outlines, plain solid green background, static camera, full body stays in frame"
NEGATIVE = (
    "camera movement, zoom, pan, shadow, floor, 3d, realistic, photo, blurry, motion blur, background change, "
    "scenery, text, watermark, extra limbs, deformed, color shift, flicker"
)


def call(path, data=None, timeout=30):
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(URL + path, body, {"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as reply:
        return json.loads(reply.read())


def workflow(a):
    def model(key, gguf, lora):
        return {
            f"{key}u": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": gguf}},
            f"{key}l": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": [f"{key}u", 0], "lora_name": lora, "strength_model": 1.0}},
            f"{key}s": {"class_type": "ModelSamplingSD3", "inputs": {"model": [f"{key}l", 0], "shift": 5.0}},
        }

    half = a.steps // 2
    nodes = {
        **model("h", "Wan2.2-I2V-A14B-HighNoise-Q4_K_S.gguf", "wan22_i2v_lightning_high.safetensors"),
        **model("w", "Wan2.2-I2V-A14B-LowNoise-Q4_K_S.gguf", "wan22_i2v_lightning_low.safetensors"),
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": a.prompt + STYLE, "clip": ["clip", 0]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["clip", 0]}},
        "img": {"class_type": "LoadImage", "inputs": {"image": a.image}},
        "fit": {"class_type": "ImageScale", "inputs": {"image": ["img", 0], "upscale_method": "lanczos", "width": a.size, "height": a.size, "crop": "center"}},
        "flf": {
            "class_type": "WanFirstLastFrameToVideo",
            "inputs": {
                "positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0],
                "width": a.size, "height": a.size, "length": a.frames, "batch_size": 1,
                "start_image": ["fit", 0],
            },
        },
        "k1": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["hs", 0], "positive": ["flf", 0], "negative": ["flf", 1], "latent_image": ["flf", 2],
                "add_noise": "enable", "noise_seed": a.seed, "steps": a.steps, "cfg": 1.0,
                "sampler_name": "euler", "scheduler": "simple",
                "start_at_step": 0, "end_at_step": half, "return_with_leftover_noise": "enable",
            },
        },
        "k2": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["ws", 0], "positive": ["flf", 0], "negative": ["flf", 1], "latent_image": ["k1", 0],
                "add_noise": "disable", "noise_seed": a.seed, "steps": a.steps, "cfg": 1.0,
                "sampler_name": "euler", "scheduler": "simple",
                "start_at_step": half, "end_at_step": a.steps, "return_with_leftover_noise": "disable",
            },
        },
        "dec": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["k2", 0], "vae": ["vae", 0], "tile_size": 256, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
        "save": {"class_type": "SaveImage", "inputs": {"images": ["dec", 0], "filename_prefix": a.name}},
    }
    if a.loop:
        nodes["flf"]["inputs"]["end_image"] = ["fit", 0]
    return nodes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image")
    p.add_argument("prompt")
    p.add_argument("--name", default="vid")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--size", type=int, default=480)
    p.add_argument("--frames", type=int, default=33, help="must be 4n+1")
    p.add_argument("--steps", type=int, default=4)
    p.add_argument("--loop", action="store_true")
    a = p.parse_args()

    started = time.time()
    job = call("/prompt", {"prompt": workflow(a)})["prompt_id"]
    while True:
        time.sleep(3)
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
    print(f"{time.time() - started:.0f}s {len(files)} frames, first {files[0]}")


if __name__ == "__main__":
    main()
