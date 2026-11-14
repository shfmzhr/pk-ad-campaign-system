import json
import sys
import uuid
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import db  # noqa: E402

st.set_page_config(page_title="Ad feed", layout="wide")

if "sid" not in st.session_state:
    st.session_state.sid = uuid.uuid4().hex
sid = st.session_state.sid

ICONS = {"like": "\U0001F44D", "love": "\u2764\uFE0F", "dislike": "\U0001F44E"}

st.title("Ad feed")
st.caption("Demo ads made by an AI campaign system. All ads are AI-generated. "
           "Your reaction is counted once per ad per visit.")

ads = db.list_ads()
if not ads:
    st.info("No ads yet. Register one with: python src/register_ad.py outputs\\campaign_...")
    st.stop()

for ad in ads:
    db.log_view(ad["id"], sid)
    left, mid, right = st.columns([1, 2, 1])
    with mid:
        video = ROOT / ad["video_path"]
        if video.exists():
            st.video(str(video))
        else:
            st.warning("Video file is missing on this computer.")
        st.markdown(f"**{ad['headline']}**")
        st.write(ad["caption"])
        st.caption(" ".join("#" + str(h).lstrip("# ") for h in json.loads(ad["hashtags"]))
                   + "  |  AI-generated ad")

        mine = db.get_reaction(ad["id"], sid)
        cols = st.columns(3)
        for col, kind in zip(cols, db.KINDS):
            col.button(ICONS[kind], key=f"{kind}_{ad['id']}",
                       type="primary" if mine == kind else "secondary",
                       on_click=db.set_reaction, args=(ad["id"], sid, kind))
        fresh = next(a for a in db.list_ads() if a["id"] == ad["id"])
        st.caption(f"{fresh['viewers']} viewers  |  {ICONS['like']} {fresh['likes']}  "
                   f"{ICONS['love']} {fresh['loves']}  {ICONS['dislike']} {fresh['dislikes']}")
        st.divider()