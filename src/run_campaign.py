import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import make_ad

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
W, H = 1080, 1350
PINK = (255, 62, 150)

HEAD_FONTS = ["C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/System/Library/Fonts/Supplemental/Impact.ttf"]
BODY_FONTS = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
NEG = re.compile(r",?\s*\b(?:no|without)\s+(?:extra\s+props|text|logos?|watermarks?|words)\b",
                 re.I)
ARABIC = re.compile(r"[\u0600-\u06FF]")


def load_font(candidates, size):
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def clean_prompt(prompt):
    p = NEG.sub("", str(prompt))
    p = re.sub(r"\s+", " ", p).strip(" ,.")
    return p + ", professional fashion photography, sharp focus, high quality"


def cover(img, w, h):
    img = img.convert("RGB")
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)),
                     Image.LANCZOS)
    left, top = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        test = (cur + " " + word).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def pill(draw, xy, text, font, fill, text_fill=(255, 255, 255, 255), pad=(30, 16)):
    x, y = xy
    box = draw.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    rect = (x, y, x + w + pad[0] * 2, y + h + pad[1] * 2)
    draw.rounded_rectangle(rect, radius=(rect[3] - rect[1]) // 2, fill=fill)
    draw.text((x + pad[0] - box[0], y + pad[1] - box[1]), text, font=font, fill=text_fill)
    return rect


def add_overlay(base, brand, headline, cta, label="AI-generated"):
    img = cover(base, W, H).convert("RGBA")

    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    top_y = int(H * 0.40)
    for y in range(top_y, H):
        a = int(238 * ((y - top_y) / (H - top_y)) ** 0.9)
        sd.line([(0, y), (W, y)], fill=(40, 0, 25, a))
    img = Image.alpha_composite(img, shade)

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    margin = 70

    small = load_font(BODY_FONTS, 32)
    pill(d, (margin, 60), brand.upper(), small, PINK + (255,))
    box = d.textbbox((0, 0), label, font=small)
    pill(d, (W - margin - (box[2] - box[0]) - 60, 60), label, small, (0, 0, 0, 150))

    cta_font = load_font(BODY_FONTS, 44)
    cb = d.textbbox((0, 0), cta, font=cta_font)
    cta_h = cb[3] - cb[1] + 44
    cta_y = H - 110 - cta_h
    pill(d, (margin, cta_y), cta, cta_font, PINK + (255,), pad=(40, 22))

    text = headline.upper()
    max_w = W - margin * 2
    for size in range(100, 52, -4):
        font = load_font(HEAD_FONTS, size)
        lines = wrap(d, text, font, max_w)
        line_h = int(size * 1.08)
        if len(lines) <= 3 and all(d.textlength(l, font=font) <= max_w for l in lines):
            break
    block_h = line_h * len(lines)
    y = cta_y - 45 - block_h
    for line in lines:
        d.text((margin + 4, y + 4), line, font=font, fill=(0, 0, 0, 170))
        d.text((margin, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_h

    return Image.alpha_composite(img, layer).convert("RGB")


def plan(passthrough):
    cmd = [sys.executable, str(ROOT / "src" / "plan_campaign.py"), *passthrough]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr[-1500:])
        raise SystemExit("Planning failed.")
    m = re.search(r"Saved -> (.+)", res.stdout)
    if not m:
        raise SystemExit("Could not find the saved brief path.")
    return Path(m.group(1).strip())


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False,
                                 description="Plan a campaign, then make the ad picture and video. "
                                             "Other options (--language, --channel, ...) go to plan_campaign.py")
    ap.add_argument("--brief", help="reuse a saved brief JSON instead of planning a new one")
    ap.add_argument("--base-image", help="use this picture instead of generating one")
    ap.add_argument("--no-overlay", action="store_true",
                    help="skip the text overlay (for ads that already contain text)")
    ap.add_argument("--seconds", type=int, default=8)
    ap.add_argument("--seed", type=int, default=None)
    args, passthrough = ap.parse_known_args()

    brief_path = Path(args.brief) if args.brief else plan(passthrough)
    record = json.loads(brief_path.read_text(encoding="utf-8"))
    brief, inputs = record["brief"], record["inputs"]
    if record.get("language_check") == "failed":
        print("Warning: the copy does not look like the requested language.")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    folder = OUT / f"campaign_{stamp}"
    folder.mkdir(parents=True, exist_ok=True)

    raw = folder / "base.png"
    if args.base_image:
        src = Path(args.base_image).expanduser()
        if not src.exists():
            raise SystemExit(f"Image not found: {src}")
        shutil.copy(src, raw)
        print(f"Using your picture: {src.name}")
    else:
        prompt = clean_prompt(brief["image_prompt"])
        print(f"Generating image from: {prompt}")
        make_ad.generate_image(prompt, raw, seed=args.seed)

    base = Image.open(raw)
    text_parts = f"{brief['headline']} {brief['call_to_action']}"
    if args.no_overlay:
        final = cover(base, W, H)
    elif ARABIC.search(text_parts):
        print("Urdu-script text is not supported in the overlay yet; skipping it.")
        final = cover(base, W, H)
    else:
        final = add_overlay(base, inputs["brand_name"], brief["headline"],
                            brief["call_to_action"])
    ad_png = folder / "ad.png"
    final.save(ad_png)

    ad_mp4 = folder / "ad.mp4"
    make_ad.render_video(ad_png, ad_mp4, args.seconds, "4x5")

    tags = " ".join("#" + str(h).lstrip("# ") for h in brief["hashtags"])
    (folder / "caption.txt").write_text(
        f"{brief['caption']}\n\n{tags}\n\n{record.get('disclosure', 'AI-generated ad')}\n",
        encoding="utf-8")
    shutil.copy(brief_path, folder / "brief.json")

    print(f"\nDone. Folder: {folder}\n  ad.png, ad.mp4, caption.txt, brief.json")


if __name__ == "__main__":
    main()