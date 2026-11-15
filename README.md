# pk-ad-campaign-system

Course project (Big Data Analytics, UMT Lahore) by Shifa Mazhar. A small "intelligent campaign system" that turns audience sentiment data from Pakistani clothing ads into AI-generated picture ads, shows them in a feed, and tracks viewer reactions.

This is a follow-up to [pk-clothing-ad-sentiment](https://github.com/shfmzhr/pk-clothing-ad-sentiment), which analysed 1,977 YouTube comments on Khaadi, Gul Ahmed and Sana Safinaz ads.

## What it does

1. **Audience insights** (src/build_insights.py): reads the sentiment predictions from Project 1 and writes data/insights.json (counts only, no comment text).
2. **Campaign planner** (src/plan_campaign.py): builds a brief (headline, caption, call to action, hashtags, image prompt, music mood) in English, Roman Urdu or Urdu. The "why" line is built in code from the audience numbers, not written by the model.
3. **Ad generator** (src/run_campaign.py): one command that plans, generates an image (Cloudflare Workers AI, FLUX schnell), adds a text overlay, and renders an MP4 with a slow zoom and background music (ffmpeg via imageio-ffmpeg).
4. **Ad library** (src/db.py, src/register_ad.py): SQLite database of ads, views and reactions.
5. **Feed** (app/feed.py): Streamlit ad feed with thumbs up, heart and thumbs down.
6. **Analytics** (app/pages/Analytics.py, src/feedback.py): compares ad groups only when each has at least 20 viewers and the score gap is at least 0.25; otherwise it says there is not enough data. The planner flag --use-feedback adds one cautious line from this.

Score per viewer = (2 x loves + likes - dislikes) / viewers.

## Setup

    pip install -r requirements.txt

Create a .env file (never commit it) that defines these two variables:

    CLOUDFLARE_ACCOUNT_ID=
    CLOUDFLARE_API_TOKEN=

The token needs Workers AI access. Put a royalty-free track at assets/music/track1.mp3 (git-ignored, not redistributed).

## Run

    python src/build_insights.py --source "../pk-clothing-ad-sentiment/data/processed/predictions.csv"
    python src/run_campaign.py --language roman_urdu --channel "Instagram DM"
    $latest = Get-ChildItem outputs -Directory -Filter "campaign_*" | Sort-Object LastWriteTime | Select-Object -Last 1
    python src/register_ad.py $latest.FullName
    streamlit run app/feed.py

## Design decisions

- **Fictional demo brand "Shifi".** No real brand names or logos appear in ads. Data from other brands' ads is background only and says nothing about Shifi's own audience.
- **Picture ads, not video**, because video ads are too expensive. Music is added with ffmpeg.
- **Every ad is labelled AI-generated**, since the reviewed research suggests trust can drop when viewers learn content is AI-made.
- **Local storage first.** Cloud storage (Cloudflare R2, ImageKit) is not implemented.
- **Studio Adwexy not used.** It is an ad maker rather than an ad display tool, and no API was found.
- **Image safety filter.** FLUX sometimes rejects prompts such as a model wearing the product, so the generator retries with a product-on-hanger prompt, then a flat lay.

## Limitations

- Project 1 labels are weak for negative comments (about 4% of hand labels), so the 2% negative share is a lower bound.
- Sentiment comes from other brands' YouTube comments, not from Shifi's audience.
- Reactions are demo numbers: one reaction per browser session per ad, and a refresh counts as a new viewer. They are not a real audience measurement.
- FLUX cannot draw text, so text is added as an overlay or baked into a hand-made poster (--no-overlay).
- Urdu-script text overlay is not supported (Pillow without text shaping).
- The feed plays videos from local files in outputs/, which is git-ignored, so a hosted copy would show "Video file is missing".
- Simulated results in the cited advertising papers are not treated as real-world evidence.

## Ethics and data

- Comment text is not in this repo (YouTube API terms). Only counts are stored.
- API keys live in .env, which is git-ignored.
