import sys

import db

sys.stdout.reconfigure(encoding="utf-8")

if len(sys.argv) != 2:
    raise SystemExit("Usage: python src/register_ad.py outputs\\campaign_YYYYMMDD_HHMMSS")

ad_id, new = db.add_ad(sys.argv[1])
total = len(db.list_ads())
print(("Added" if new else "Already registered") + f" ad #{ad_id}. Ads in the library: {total}")