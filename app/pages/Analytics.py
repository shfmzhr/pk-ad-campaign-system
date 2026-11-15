import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import db  # noqa: E402
import feedback  # noqa: E402

st.set_page_config(page_title="Analytics", layout="wide")
st.title("Campaign analytics")
st.caption("Reactions come from the demo feed. A viewer is one browser visit, so "
           "counts are demo-audience numbers, not a real audience measurement.")

ads = db.list_ads()
if not ads:
    st.info("No ads yet. Register one with: python src/register_ad.py outputs\\campaign_...")
    st.stop()

rows = []
for a in ads:
    m = feedback.metrics(a)
    rows.append({
        "ad": f"#{a['id']}", "headline": a["headline"],
        "language": feedback.LABELS.get(a["language"], a["language"]),
        "viewers": a["viewers"], "likes": a["likes"], "loves": a["loves"],
        "dislikes": a["dislikes"],
        "reaction rate": round(m["reaction_rate"], 2),
        "positive share": None if m["positive_share"] is None else round(m["positive_share"], 2),
        "score per viewer": round(m["score"], 2),
    })
df = pd.DataFrame(rows)

c1, c2, c3 = st.columns(3)
c1.metric("Ads", len(df))
c2.metric("Ad views (sessions x ads)", int(df["viewers"].sum()))
c3.metric("Reactions", int(df[["likes", "loves", "dislikes"]].sum().sum()))

st.subheader("Reactions per ad")
st.bar_chart(df.set_index("ad")[["likes", "loves", "dislikes"]])
st.dataframe(df, hide_index=True)
st.caption("Score per viewer = (2 x loves + likes - dislikes) / viewers.")

st.subheader("What the reactions suggest")
for item in feedback.insights(ads):
    getattr(st, item["level"])(item["text"])