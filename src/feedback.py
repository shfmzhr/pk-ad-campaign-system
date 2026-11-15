"""Turn demo-audience reactions into simple, cautious guidance."""

MIN_VIEWERS = 20   # viewers per group before we compare anything
MARGIN = 0.25      # score gap needed before we call one group "ahead"
FIELDS = {"language": "caption language", "reference": "audience reference"}
LABELS = {"english": "English", "roman_urdu": "Roman Urdu", "urdu": "Urdu"}


def metrics(ad):
    v = ad["viewers"]
    r = ad["likes"] + ad["loves"] + ad["dislikes"]
    return {
        "viewers": v,
        "reactions": r,
        "reaction_rate": r / v if v else 0.0,
        "positive_share": (ad["likes"] + ad["loves"]) / r if r else None,
        "score": (2 * ad["loves"] + ad["likes"] - ad["dislikes"]) / v if v else 0.0,
    }


def _name(field, value):
    return LABELS.get(value, str(value)) if field == "language" else str(value)


def compare_by(ads, field):
    """Pool ads by a field. Returns (groups, ready) where ready means a fair comparison."""
    groups = {}
    for ad in ads:
        g = groups.setdefault(ad.get(field) or "unknown",
                              {"viewers": 0, "points": 0, "ads": 0})
        g["viewers"] += ad["viewers"]
        g["points"] += 2 * ad["loves"] + ad["likes"] - ad["dislikes"]
        g["ads"] += 1
    for g in groups.values():
        g["score"] = g["points"] / g["viewers"] if g["viewers"] else 0.0
    enough = {k: g for k, g in groups.items() if g["viewers"] >= MIN_VIEWERS}
    return groups, len(enough) >= 2


def insights(ads):
    """List of {'level', 'text', 'planner'}; 'planner' is a line safe to give the planner."""
    out = []
    if not ads:
        return [{"level": "info", "text": "No ads yet.", "planner": None}]

    short = [a for a in ads if a["viewers"] < MIN_VIEWERS]
    if short:
        names = ", ".join(f"#{a['id']} ({a['viewers']}/{MIN_VIEWERS})" for a in short)
        out.append({"level": "warning", "planner": None,
                    "text": f"Not enough viewers yet for: {names}. Share the feed "
                            f"until each ad has at least {MIN_VIEWERS} viewers."})

    for field, nice in FIELDS.items():
        groups, ready = compare_by(ads, field)
        if len(groups) < 2:
            out.append({"level": "info", "planner": None,
                        "text": f"Only one {nice} so far, so there is nothing to compare. "
                                f"Make a second ad with a different {nice}."})
            continue
        if not ready:
            out.append({"level": "info", "planner": None,
                        "text": f"Comparing by {nice} needs at least two groups with "
                                f"{MIN_VIEWERS}+ viewers each."})
            continue
        enough = {k: g for k, g in groups.items() if g["viewers"] >= MIN_VIEWERS}
        ranked = sorted(enough.items(), key=lambda kv: kv[1]["score"], reverse=True)
        (top, tg), (second, sg) = ranked[0], ranked[1]
        detail = "; ".join(f"{_name(field, k)} {g['score']:.2f} per viewer "
                           f"({g['viewers']} viewers)" for k, g in ranked)
        if tg["score"] - sg["score"] >= MARGIN:
            out.append({"level": "success",
                        "text": f"By {nice}: {_name(field, top)} is ahead ({detail}). "
                                "The audience is small and not random, so treat this as "
                                "a hint, not proof.",
                        "planner": (f"In a small demo feed, ads with {nice} "
                                    f"'{_name(field, top)}' got stronger reactions than "
                                    f"'{_name(field, second)}'. This is a weak signal.")})
        else:
            out.append({"level": "info", "planner": None,
                        "text": f"By {nice}: no clear difference ({detail})."})
    return out