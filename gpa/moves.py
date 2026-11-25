"""Spot the moves, keep the repeated ones, and check each against you.

A move counts as "repeated" when at least two of the three competitors show
it. It makes your page only if it also fits your team and budget and you are
not already doing it.
"""

import json
import os

HERE = os.path.dirname(__file__)


def load_moves():
    with open(os.path.join(HERE, "moves.json")) as f:
        return json.load(f)["moves"]


def n(v):
    return f"{int(round(v)):,}"


# Each check returns (shows_the_move, proof_sentence, lookups_used, strength) or None when
# the data for that check is missing, so "no data" is never read as "no".

def check(move, c):
    s, ads, x, li, ai, site = c.get("search"), c.get("ads"), c.get("x"), c.get("linkedin"), c.get("ai"), c.get("site")
    t = move["threshold"]
    mid = move["id"]
    if mid == "free_tools":
        if not s or not s["keywords_sampled"]:
            return None
        share = s["type_share"].get("free tools", 0) + s["type_share"].get("templates", 0)
        pages = s["pages_by_type"].get("free tools", []) + s["pages_by_type"].get("templates", [])
        top = max(pages, key=lambda p: p["etv"]) if pages else None
        proof = f"{share:g}% of the search visits we sampled land on free tool and template pages"
        if top:
            proof += f". Top one: {top['url']} (about {n(top['etv'])} visits a month)"
        return share >= t, proof + ".", ["ranked"], share
    if mid in ("comparison",):
        if not s or not s["keywords_sampled"]:
            return None
        pages = s["pages_by_type"].get("comparison", [])
        count = s["pages_count_by_type"].get("comparison", 0)
        visits = sum(p["etv"] for p in pages)
        proof = f"{count} comparison pages rank in Google"
        if pages:
            proof += f", bringing about {n(visits)} visits a month. Top one: {pages[0]['url']}"
        return count >= t, proof + ".", ["ranked"], count
    if mid in ("guides", "integrations", "user_pages"):
        if not s or not s["keywords_sampled"]:
            return None
        key = {"guides": "guides and blog", "integrations": "integrations", "user_pages": "user-made pages"}[mid]
        share = s["type_share"].get(key, 0)
        pages = s["pages_by_type"].get(key, [])
        label = {"guides and blog": "guide and blog pages", "integrations": "integration pages",
                 "user-made pages": "pages its users made"}[key]
        proof = f"{share:g}% of the search visits we sampled land on {label}"
        if pages:
            proof += f". Top one: {pages[0]['url']}"
        return share >= t, proof + ".", ["ranked"], share
    if mid == "long_ads":
        if ads is None:
            return None
        if not ads["active_ads"]:
            return False, "No active ads found in the Meta Ad Library.", ["meta_ads"], 0
        o = ads["oldest"]
        count = "30+" if ads["active_ads"] >= 30 else str(ads["active_ads"])
        proof = (f"{count} active Meta ads, {ads['running_30_days']} of them running 30 days or more. "
                 f"The oldest started {o['started']} ({o['days']} days ago)")
        if o["text"]:
            proof += f': "{o["text"]}"'
        return ads["running_30_days"] >= t, proof + ".", ["meta_ads"], ads["running_30_days"]
    if mid == "affiliates":
        if not site and not s:
            return None
        tools = (site or {}).get("affiliate_tools") or []
        pages = (s or {}).get("pages_by_type", {}).get("affiliate", []) if s else []
        if tools:
            return True, f"Affiliate software on the site: {', '.join(tools)}.", ["site"], 1
        if pages:
            return True, f"Its affiliate page ranks in Google: {pages[0]['url']}.", ["ranked"], 1
        return False, "No affiliate software or affiliate page found.", ["site", "ranked"], 0
    if mid == "attention":
        if not s or not s["keywords_sampled"]:
            return None
        proof = (f"{s['brand_share']:g}% of the search visits we sampled come from people typing "
                 f"the name \"{c['brand']}\"")
        used = ["ranked"]
        if x and x.get("posts"):
            top = x["top"]
            proof += (f". On X, its {x['posts']} posts from the last 12 months had a median of "
                      f"{n(x['median_views'])} views; the top one got {n(top['views'])} views on {top['date']}")
            used.append("x_posts")
        return s["brand_share"] >= t, proof + ".", used, s["brand_share"]
    if mid == "linkedin":
        if li is None:
            return None
        if not li["posts"]:
            return False, "No recent LinkedIn company posts found.", ["linkedin_posts"], 0
        if li["per_week"] is None:
            return None
        proof = f"{li['posts']} LinkedIn posts between {li['first']} and {li['last']}, about {li['per_week']:g} a week."
        return li["per_week"] >= t, proof, ["linkedin_posts"], li["per_week"]
    if mid == "ai_answers":
        if ai is None:
            return None
        k, total = len(ai["named_in"]), ai["asked"]
        proof = f"Named by ChatGPT in {k} of {total} buyer questions"
        if ai["named_in"]:
            proof += ": " + "; ".join(f'"{q}"' for q in ai["named_in"])
        return k >= t, proof + ".", ["ai_answer"], k
    raise ValueError(mid)


def choose(you, competitors, answers, max_moves=5):
    """Sort every move into: make it, do more of it, already done, or left out."""
    team = int(answers.get("team_size") or 1)
    budget = float(answers.get("monthly_budget_usd") or 0)
    picked, already, left_out = [], [], []
    for order, move in enumerate(load_moves()):
        rows = []
        for c in competitors:
            res = check(move, c)
            rows.append({"domain": c["domain"], "shows": bool(res and res[0]), "known": res is not None,
                         "proof": res[1] if res else "No data.", "used": res[2] if res else [],
                         "strength": res[3] if res else None})
        doing = [r for r in rows if r["shows"]]
        mine = check(move, you)
        entry = {**move, "order": order, "competitors": rows, "count": len(doing), "kind": "new",
                 "you": {"shows": bool(mine and mine[0]), "proof": mine[1] if mine else "No data.",
                         "strength": mine[3] if mine else None}}
        entry["fits"] = team >= move["needs"]["team"] and budget >= move["needs"]["budget"]
        if not doing:
            continue
        theirs = sorted(r["strength"] for r in doing if r["strength"] is not None)
        typical = theirs[len(theirs) // 2] if theirs else None
        if entry["you"]["shows"]:
            mine_s = entry["you"]["strength"]
            if len(doing) >= 2 and typical and mine_s is not None and mine_s < typical / 2:
                entry["kind"] = "more"  # you do it, but at less than half of what they do
            else:
                entry["why"] = "You already do this about as much as they do."
                already.append(entry)
                continue
        if len(doing) < 2:
            entry["why"] = "Only one of the three competitors does this, so it may be a one-off."
            left_out.append(entry)
        elif not entry["fits"]:
            entry["why"] = f"It needs {move['needs_text']}, which is more than the team and budget you gave."
            left_out.append(entry)
        else:
            picked.append(entry)
    picked.sort(key=lambda e: (-e["count"], e["kind"] == "more", e["effort"], e["order"]))
    for e in picked[max_moves:]:
        e["why"] = "Repeated and a fit, but outside the top five this time."
        left_out.append(e)
    return picked[:max_moves], already, left_out
