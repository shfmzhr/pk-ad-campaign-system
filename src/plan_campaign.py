import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
INSIGHTS = ROOT / "data" / "insights.json"
OUTDIR = ROOT / "data" / "campaigns"

MODEL_ENGLISH = "@cf/meta/llama-3.1-8b-instruct-fast"
MODEL_MULTILINGUAL = "@cf/google/gemma-4-26b-a4b-it"
DEFAULT_MODELS = {"english": MODEL_ENGLISH,
                  "roman_urdu": MODEL_MULTILINGUAL,
                  "urdu": MODEL_MULTILINGUAL}

LANG_RULES = {
    "english": "Write the copy in simple, natural English.",
    "roman_urdu": ("Write the headline, caption and call to action in Roman Urdu "
                   "(Urdu written in English letters, the way Pakistanis text). "
                   "Do not write them in English, except the brand name and "
                   "common loanwords."),
    "urdu": "Write the headline, caption and call to action in Urdu script.",
}
KEYS = ["headline", "caption", "call_to_action", "hashtags",
        "image_prompt", "music_mood"]
RU_WORDS = {"hai", "hain", "ka", "ki", "ke", "ko", "se", "mein", "aur", "yeh", "ye",
            "woh", "apna", "apni", "apne", "abhi", "naya", "nayi", "naye", "hamari",
            "hamara", "liye", "kar", "karo", "karein", "kijiye", "dekho", "bohat",
            "bahut", "zabardast", "pyara", "pyari", "aap", "aapka", "aapki", "tum",
            "tumhara", "tumhari", "pehno", "pehnein", "khoobsurat", "hasil",
            "zaroor", "kharid", "dein"}


def load_env():
    env = dotenv_values(ROOT / ".env", encoding="utf-8-sig")
    account = env.get("CLOUDFLARE_ACCOUNT_ID")
    token = env.get("CLOUDFLARE_API_TOKEN")
    if not account or not token:
        raise SystemExit("Missing CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN in .env")
    return account, token


def build_facts(ins, ref):
    if ref == "overall":
        s, label = ins["overall"], "Khaadi, Gul Ahmed and Sana Safinaz"
    else:
        s, label = ins["brands"].get(ref), ref
        if s is None:
            raise SystemExit(f"Unknown reference '{ref}'. Use: overall, "
                             + ", ".join(ins["brands"]))
    sh, t = s["sentiment_share"], s["topics"]
    music = t["music"]["share_of_comments"]
    price = t["price"]["share_of_comments"]
    design = t["design_clothes"]["share_of_comments"]
    asks = s["asks_question_or_request_share"]
    facts = [
        f"Source: {s['n']} YouTube comments on {label} video ads.",
        (f"Predicted sentiment: {sh['positive']:.0%} positive, {sh['neutral']:.0%} neutral, "
         f"{sh['negative']:.0%} negative (negative comments are under-detected)."),
        f"{music:.0%} of comments mention the song or music.",
        f"{design:.0%} mention the clothes or design.",
        (f"{price:.0%} mention price, {t['quality']['share_of_comments']:.0%} quality, "
         f"{t['delivery_availability']['share_of_comments']:.0%} delivery or availability."),
        f"{asks:.0%} of comments contain a question or request.",
    ]
    guide, why = [], []
    if music >= 0.25:
        guide.append("Viewers talk a lot about music in video ads, so choose the "
                     "music mood on purpose. Do not claim the product is for music lovers.")
        why.append(f"{music:.0%} mention the music, so the music mood is a deliberate choice.")
    if asks >= 0.25:
        guide.append("Many viewers ask questions, so make the call to action clear "
                     "and easy to follow.")
        why.append(f"{asks:.0%} contain a question or request, so the call to action is kept clear.")
    if price < 0.03:
        guide.append("Price is rarely discussed, so do not lead with price; "
                     "evidence for price messaging is weak.")
        why.append(f"Only {price:.0%} mention price, so the ad does not lead with price "
                   "(the evidence either way is weak).")
    if design < 0.15:
        guide.append("Few comments discuss the clothes, so show the product clearly; "
                     "evidence on design preferences is thin.")
        why.append(f"Only {design:.0%} discuss the clothes, so the product is shown clearly.")
    prefix = (f"Based on {s['n']:,} YouTube comments on {label} video ads "
              "(not this brand's own audience): ")
    why_text = prefix + (" ".join(why) if why else
                         "no strong signals, so the copy follows the brief inputs only.")
    return label, facts, guide, why_text


def call_model(model, system, user):
    account, token = load_env()
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    max_tokens = 1000 if model == MODEL_ENGLISH else 3000
    body = {"messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens, "temperature": 0.7}
    r = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                      json=body, timeout=180)
    if r.status_code != 200:
        raise SystemExit(f"Model call failed ({r.status_code}): {r.text[:400]}")
    result = r.json().get("result") or {}
    if result.get("response"):
        return result["response"]
    choices = result.get("choices") or []
    if not choices:
        raise SystemExit(f"Unexpected response shape: {str(result)[:400]}")
    choice = choices[0]
    content = (choice.get("message") or {}).get("content")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not content:
        raise SystemExit(f"The model returned no text (finish_reason: "
                         f"{choice.get('finish_reason')}). Thinking models can use up "
                         "the token budget. Try again or use another --model.")
    return content


def parse_json(text):
    if isinstance(text, dict):
        return text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def tidy(v):
    if isinstance(v, str):
        return " ".join(v.split())
    if isinstance(v, list):
        return [tidy(x) for x in v]
    return v


def language_check(language, brief):
    text = " ".join(str(brief.get(k, "")) for k in ("headline", "caption", "call_to_action"))
    if language == "roman_urdu":
        words = re.findall(r"[a-z']+", text.lower())
        return "ok" if sum(w in RU_WORDS for w in words) >= 2 else "failed"
    if language == "urdu":
        return "ok" if re.search(r"[\u0600-\u06FF]", text) else "failed"
    return "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand-name", default="Shifi")
    ap.add_argument("--product", default="pink graphic tee")
    ap.add_argument("--goal", default="build awareness for a new collection")
    ap.add_argument("--tone", default="playful, confident")
    ap.add_argument("--language", choices=list(LANG_RULES), default="english")
    ap.add_argument("--reference", default="overall",
                    help="overall, Khaadi, 'Gul Ahmed' or 'Sana Safinaz'")
    ap.add_argument("--channel", default="link in bio",
                    help="the only place to buy or ask (for example 'Instagram DM')")
    ap.add_argument("--visual-style", default="retro pink scrapbook poster, y2k, glitter stickers")
    ap.add_argument("--model", default=None)
    ap.add_argument("--use-feedback", action="store_true",
                    help="add a cautious line from demo-feed reactions when the data is clear")
    args = ap.parse_args()

    model = args.model or DEFAULT_MODELS[args.language]
    ins = json.loads(INSIGHTS.read_text(encoding="utf-8"))
    label, facts, guide, why_text = build_facts(ins, args.reference)

    if args.use_feedback:
        import db
        import feedback
        lines = [i["planner"] for i in feedback.insights(db.list_ads()) if i["planner"]]
        if lines:
            guide.extend(lines)
            why_text += " Demo-feed signal: " + " ".join(lines)
            print("Using demo-feed reactions: " + " ".join(lines))
        else:
            print("No clear feedback signal yet (needs 2+ ad groups with "
                  f"{feedback.MIN_VIEWERS}+ viewers each), so nothing was added.")

    system = (
        "You are a marketing copywriter for a small fashion brand in Pakistan. "
        "Return ONLY valid JSON with no markdown. Never invent prices, discounts, "
        "sales numbers, reviews, or performance claims. Never mention a website, "
        "store, shipping, returns, or sizes. The background facts describe viewers "
        "of OTHER brands' ads, so never say 'our audience' or 'our customers' and "
        "never claim results for this brand."
    )
    user = (
        f"Brand: {args.brand_name}\nProduct: {args.product}\nGoal: {args.goal}\n"
        f"Tone: {args.tone}\nThe only place to buy or ask: {args.channel}\n"
        f"Visual style: {args.visual_style}\n{LANG_RULES[args.language]}\n\n"
        "Background facts (viewers of OTHER Pakistani clothing brands' video ads; "
        "they say nothing about this brand's own customers):\n"
        + "\n".join(f"- {f}" for f in facts)
        + "\n\nGuidance:\n" + "\n".join(f"- {g}" for g in guide)
        + "\n\nReturn a JSON object with exactly these keys:\n"
        "headline (max 6 words), caption (max 40 words), call_to_action (max 8 words, "
        "using only the place to buy or ask above), hashtags (array of 3 to 5), "
        "image_prompt (English, for a text-to-image model: one model wearing the "
        "product, product clearly visible, simple background, follow the visual style, "
        "no extra props, no text, no logos), music_mood (3 to 6 words)."
    )

    print(f"Planning a {args.language} campaign for {args.brand_name} "
          f"(facts from: {label}; model: {model})...")
    raw = call_model(model, system, user)
    brief = parse_json(raw)
    if not brief or not all(k in brief for k in KEYS):
        print("Could not read a valid brief. Raw model output:\n")
        print(raw)
        raise SystemExit(1)

    brief = {k: tidy(brief[k]) for k in KEYS}
    if isinstance(brief["hashtags"], str):
        brief["hashtags"] = [h.strip("# ,") for h in brief["hashtags"].split() if h.strip("# ,")]
    check = language_check(args.language, brief)
    record = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": model,
        "inputs": {"brand_name": args.brand_name, "product": args.product,
                   "goal": args.goal, "tone": args.tone, "language": args.language,
                   "reference": args.reference, "channel": args.channel,
                   "visual_style": args.visual_style},
        "audience_facts": facts,
        "guidance": guide,
        "brief": {**brief, "why": why_text},
        "language_check": check,
        "disclosure": "AI-generated ad",
    }
    OUTDIR.mkdir(parents=True, exist_ok=True)
    path = OUTDIR / f"brief_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    b = record["brief"]
    print(f"\nHEADLINE : {b['headline']}\nCAPTION  : {b['caption']}")
    print(f"CTA      : {b['call_to_action']}\nHASHTAGS : {b['hashtags']}")
    print(f"IMAGE    : {b['image_prompt']}\nMUSIC    : {b['music_mood']}")
    print(f"WHY      : {b['why']}\n\nLANGUAGE CHECK: {check}")
    if check == "failed":
        print("The copy does not look like the requested language. "
              "Try another model with --model.")
    print(f"Saved -> {path}")


if __name__ == "__main__":
    main()
