import argparse
import base64
import subprocess
import time
from pathlib import Path

import imageio_ffmpeg
import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
MUSIC = ROOT / "assets" / "music"
MODEL = "@cf/black-forest-labs/flux-1-schnell"
SIZES = {"4x5": (1080, 1350), "1x1": (1080, 1080)}

DEFAULT_PROMPT = (
    "Elegant Pakistani lawn suit laid flat, pastel floral prints, "
    "soft studio lighting, clean background, no text, no logos"
)


def load_env():
    env = dotenv_values(ROOT / ".env", encoding="utf-8-sig")
    account = env.get("CLOUDFLARE_ACCOUNT_ID")
    token = env.get("CLOUDFLARE_API_TOKEN")
    if not account or not token:
        raise SystemExit("Missing CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN in .env")
    return account, token


def generate_image(prompt, path, steps=4, seed=None):
    account, token = load_env()
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}"
    body = {"prompt": prompt, "steps": steps}
    if seed is not None:
        body["seed"] = seed
    r = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                      json=body, timeout=120)
    if r.status_code != 200:
        raise SystemExit(f"Image generation failed ({r.status_code}): {r.text[:300]}")
    data = r.json()
    b64 = (data.get("result") or {}).get("image")
    if not b64:
        raise SystemExit(f"No image in response: {str(data)[:300]}")
    path.write_bytes(base64.b64decode(b64))


def pick_music():
    tracks = []
    for ext in ("*.mp3", "*.m4a", "*.wav"):
        tracks += sorted(MUSIC.glob(ext))
    return tracks[0] if tracks else None


def render_video(image, out, seconds=8, ratio="4x5"):
    w, h = SIZES[ratio]
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    music = pick_music()
    if music:
        print(f"Using music: {music.name}")
        audio_in = ["-stream_loop", "-1", "-i", str(music)]
    else:
        print("No music in assets/music, using a placeholder tone for this test.")
        audio_in = ["-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}"]

    graph = (
        f"[0:v]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,"
        f"crop={w * 2}:{h * 2},"
        "zoompan=z='min(zoom+0.0004,1.08)':x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':d={seconds * 25}:s={w}x{h}:fps=25,"
        "format=yuv420p[v];"
        f"[1:a]afade=t=in:d=0.5,afade=t=out:st={max(seconds - 1, 0)}:d=1[a]"
    )
    cmd = [ffmpeg, "-y", "-i", str(image), *audio_in,
           "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
           "-t", str(seconds), "-c:v", "libx264", "-c:a", "aac",
           "-movflags", "+faststart", str(out)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit("ffmpeg failed:\n" + res.stderr[-1500:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--image", default=None,
                    help="use this picture instead of generating one")
    ap.add_argument("--seconds", type=int, default=8)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--ratio", choices=list(SIZES), default="4x5")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    video = OUT / f"ad_{stamp}.mp4"

    if args.image:
        image = Path(args.image).expanduser()
        if not image.exists():
            raise SystemExit(f"Image not found: {image}")
        print(f"1/2 Using your picture: {image.name}")
    else:
        image = OUT / f"ad_{stamp}.png"
        print("1/2 Generating image...")
        generate_image(args.prompt, image, seed=args.seed)

    print("2/2 Rendering video...")
    render_video(image, video, args.seconds, args.ratio)
    print(f"Done:\n  {image}\n  {video}")


if __name__ == "__main__":
    main()