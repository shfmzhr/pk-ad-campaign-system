import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "insights.json"
SENT = ["positive", "neutral", "negative"]

TOPICS = {
    "price": r"price|expensive|overpriced|costly|\bcost\b|\brate\b|\brs\b|mehng|mahng|sasta|sasti|discount|\bsale\b|paisa",
    "design_clothes": r"dress|\bsuits?\b|lawn|print|design|colou?r|kapra|kapray|kapre|outfit|embroider|dupatta|shalwar|kurta|collection",
    "quality": r"quality|stitch|material|fabric|fitting|\bwash",
    "delivery_availability": r"delivery|shipping|courier|parcel|\border\b|branch|\bstore\b|available|\bstock\b|\bsizes?\b",
    "music": r"song|music|soundtrack|voice|singer|lyrics|\bost\b|gana|gaana|awaz",
    "model_or_actress": r"actress|\bmodels?\b|celebrity|\bface\b",
}
ASK = r"\?|\bpl+[sz]+\b|\bplease\b|\bname\b|\blink\b|batao|bata do|\bshare\b|release|\bkahan\b|\bkaise\b|\bkab\b"

CAVEATS = [
    "Sentiment is predicted by a model trained on 570 hand-labeled comments; negative comments are under-detected.",
    "Source is YouTube comments on three brand channels; commenter location is unknown.",
    "Khaadi data comes from a single music-led campaign, so brand differences partly reflect campaign type.",
    "Topic counts are keyword matches, not aspect-based sentiment.",
]


def share(series, order):
    counts = series.value_counts()
    total = int(counts.sum())
    return {k: round(float(counts.get(k, 0)) / total, 3) if total else 0.0 for k in order}


def summarize(d):
    text = d["comment_clean"].astype(str)
    out = {
        "n": int(len(d)),
        "sentiment_share": share(d["sentiment_pred"], SENT),
        "language_share": share(d["lang_guess"],
                                ["english", "roman_urdu", "urdu_script", "emoji_only"]),
        "asks_question_or_request_share": round(
            float(text.str.contains(ASK, case=False, regex=True).mean()), 3),
        "topics": {},
    }
    for name, pattern in TOPICS.items():
        hit = text.str.contains(pattern, case=False, regex=True)
        sub = d[hit]
        out["topics"][name] = {
            "mentions": int(hit.sum()),
            "share_of_comments": round(float(hit.mean()), 3),
            "sentiment_counts": {s: int((sub["sentiment_pred"] == s).sum()) for s in SENT},
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True,
                    help="path to predictions.csv from pk-clothing-ad-sentiment")
    args = ap.parse_args()

    df = pd.read_csv(args.source, encoding="utf-8-sig")
    need = {"brand", "comment_clean", "sentiment_pred", "lang_guess"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"Missing columns in source file: {sorted(missing)}")

    excluded = int((df["lang_guess"] == "turkish_likely").sum())
    df = df[df["lang_guess"] != "turkish_likely"]

    result = {
        "source": "pk-clothing-ad-sentiment predictions (aggregated counts only, no comment text)",
        "excluded_likely_turkish": excluded,
        "overall": summarize(df),
        "brands": {b: summarize(g) for b, g in df.groupby("brand") if len(g) >= 30},
        "caveats": CAVEATS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Comments used: {len(df)} (excluded {excluded} likely-Turkish)")
    for name, s in {"ALL": result["overall"], **result["brands"]}.items():
        sh = s["sentiment_share"]
        print(f"\n{name}: n={s['n']}  pos {sh['positive']:.0%} / "
              f"neu {sh['neutral']:.0%} / neg {sh['negative']:.0%}  "
              f"asks {s['asks_question_or_request_share']:.0%}")
        print("   topics: " + ", ".join(f"{t}={v['mentions']}" for t, v in s["topics"].items()))
    print(f"\nSaved -> {OUT}")


if __name__ == "__main__":
    main()