import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "ads.db"
KINDS = ["like", "love", "dislike"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT, brand TEXT, product TEXT, language TEXT, reference TEXT,
    headline TEXT, caption TEXT, call_to_action TEXT, hashtags TEXT,
    video_path TEXT, image_path TEXT, folder TEXT UNIQUE,
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS views (
    ad_id INTEGER, session_id TEXT, ts TEXT,
    PRIMARY KEY (ad_id, session_id)
);
CREATE TABLE IF NOT EXISTS reactions (
    ad_id INTEGER, session_id TEXT, kind TEXT, ts TEXT,
    PRIMARY KEY (ad_id, session_id)
);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def add_ad(folder):
    """Register a finished campaign folder (made by run_campaign.py)."""
    folder = Path(folder).resolve()
    brief_file = folder / "brief.json"
    if not brief_file.exists():
        raise SystemExit(f"No brief.json in {folder}. Is this a campaign folder?")
    try:
        rel = folder.relative_to(ROOT)
    except ValueError:
        raise SystemExit(f"{folder} is outside the project folder {ROOT}")
    rec = json.loads(brief_file.read_text(encoding="utf-8"))
    b, i = rec["brief"], rec["inputs"]
    with closing(connect()) as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO ads (created, brand, product, language, reference, "
            "headline, caption, call_to_action, hashtags, video_path, image_path, folder) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec.get("created") or _now(), i.get("brand_name"), i.get("product"),
             i.get("language"), i.get("reference"), b["headline"], b["caption"],
             b["call_to_action"], json.dumps(b["hashtags"], ensure_ascii=False),
             str(rel / "ad.mp4"), str(rel / "ad.png"), str(rel)))
        con.commit()
        new = cur.rowcount > 0
        ad_id = con.execute("SELECT id FROM ads WHERE folder = ?", (str(rel),)).fetchone()["id"]
    return ad_id, new


def list_ads():
    with closing(connect()) as con:
        rows = con.execute(
            "SELECT a.*, "
            "(SELECT COUNT(*) FROM views v WHERE v.ad_id = a.id) AS viewers, "
            "(SELECT COUNT(*) FROM reactions r WHERE r.ad_id = a.id AND r.kind = 'like') AS likes, "
            "(SELECT COUNT(*) FROM reactions r WHERE r.ad_id = a.id AND r.kind = 'love') AS loves, "
            "(SELECT COUNT(*) FROM reactions r WHERE r.ad_id = a.id AND r.kind = 'dislike') AS dislikes "
            "FROM ads a WHERE a.active = 1 ORDER BY a.id DESC").fetchall()
    return [dict(r) for r in rows]


def log_view(ad_id, session_id):
    with closing(connect()) as con:
        con.execute("INSERT OR IGNORE INTO views (ad_id, session_id, ts) VALUES (?,?,?)",
                    (ad_id, session_id, _now()))
        con.commit()


def set_reaction(ad_id, session_id, kind):
    """One reaction per viewer session per ad; a new click replaces the old one."""
    if kind not in KINDS:
        raise ValueError(kind)
    with closing(connect()) as con:
        con.execute("INSERT OR REPLACE INTO reactions (ad_id, session_id, kind, ts) "
                    "VALUES (?,?,?,?)", (ad_id, session_id, kind, _now()))
        con.commit()


def get_reaction(ad_id, session_id):
    with closing(connect()) as con:
        row = con.execute("SELECT kind FROM reactions WHERE ad_id = ? AND session_id = ?",
                          (ad_id, session_id)).fetchone()
    return row["kind"] if row else None