"""Turn raw provider answers into a few plain facts per company.

Nothing here calls the internet or guesses. Each function reads one saved
answer and returns small numbers the moves can be checked against.
"""

import re
from datetime import date, datetime, timezone
from statistics import median
from urllib.parse import urlparse


def dfs_result(data):
    """First result object of a DataForSEO answer, or {}."""
    try:
        return (data["tasks"][0]["result"] or [{}])[0] or {}
    except (KeyError, IndexError, TypeError):
        return {}


def brand_of(domain):
    """'app.tally.so' -> 'tally'. Used to spot brand-name searches."""
    parts = domain.lower().replace("www.", "").split(".")
    return parts[-2] if len(parts) >= 2 else parts[0]


# ------------------------------------------------------------ website

AFFILIATE_TOOLS = ["rewardful", "partnerstack", "firstpromoter", "tolt", "tapfiliate", "refersion",
                   "impact", "post affiliate pro", "affiliatewp", "promotekit", "dub partners"]
AD_PIXELS = {"facebook pixel": "Meta pixel", "meta pixel": "Meta pixel",
             "linkedin insight tag": "LinkedIn Insight Tag", "google ads": "Google Ads tag",
             "twitter ads": "X ads tag", "reddit ads": "Reddit pixel", "tiktok pixel": "TikTok pixel"}


def site_facts(data, domain):
    r = dfs_result(data)
    names = []
    for group in (r.get("technologies") or {}).values():
        for items in (group or {}).values():
            names.extend(items or [])
    lower = [n.lower() for n in names]
    socials = [u for u in (r.get("social_graph_urls") or []) if isinstance(u, str)]
    return {
        "domain": domain,
        "title": r.get("title") or "",
        "description": r.get("description") or "",
        "technologies": sorted(set(names)),
        "affiliate_tools": sorted({t for t in AFFILIATE_TOOLS for n in lower if t in n}),
        "ad_pixels": sorted({label for key, label in AD_PIXELS.items() for n in lower if key in n}),
        "linkedin_url": next((u for u in socials if "linkedin.com/company/" in u), None),
        "x_handle": next((x_handle(u) for u in socials if x_handle(u)), None),
    }


def x_handle(url):
    m = re.match(r"https?://(www\.)?(twitter|x)\.com/([A-Za-z0-9_]{1,15})/?$", url or "")
    return m.group(3) if m else None


# ------------------------------------------------------------ search

PAGE_TYPES = [  # checked in order; first match wins
    ("comparison", r"alternative|-vs-|/vs/|versus|compare|comparison|competitor"),
    ("user-made pages", r"^/\d{9,}|^/to/[a-z0-9]+|^/r/[a-z0-9]+|^/f/[a-z0-9]+"),
    ("login", r"login|signin|sign-in|signup|sign-up|register"),
    ("free tools", r"tool|generator|calculator|checker|converter|compress|/pdf/|free-|ai-[a-z-]*maker"),
    ("templates", r"template"),
    ("integrations", r"integration|/apps?/|marketplace"),
    ("help docs", r"help|docs|support|faq|knowledge|api-reference"),
    ("guides and blog", r"blog|guide|learn|resource|article|academy|how-to|what-is"),
    ("affiliate", r"affiliate|partner-program|referral"),
    ("pricing", r"pricing|plans"),
    ("product pages", r"builder|maker|creator|/try/|feature|/product|^/forms/?$|use-case|solution|widget"),
]


def page_type(relative_url):
    path = (relative_url or "/").lower()
    if path in ("/", "") or re.fullmatch(r"/(\?.*)?", path) or re.fullmatch(r"/[a-z]{2}(-[a-z]{2})?/?", path):
        return "home page"
    for name, pattern in PAGE_TYPES:
        if re.search(pattern, path):
            return name
    return "other pages"


def search_facts(data, domain):
    r = dfs_result(data)
    organic = ((r.get("metrics") or {}).get("organic") or {})
    brand = brand_of(domain)
    rows = []
    for item in r.get("items") or []:
        kw = (item.get("keyword_data") or {}).get("keyword") or ""
        serp = (item.get("ranked_serp_element") or {}).get("serp_item") or {}
        rows.append({"keyword": kw, "url": serp.get("url") or "",
                     "relative_url": serp.get("relative_url") or "/",
                     "etv": float(serp.get("etv") or 0)})
    sampled = sum(x["etv"] for x in rows) or 0.0
    by_type, pages = {}, {}
    for x in rows:
        t = page_type(x["relative_url"])
        by_type[t] = by_type.get(t, 0.0) + x["etv"]
        p = pages.setdefault(x["url"], {"url": x["url"], "type": t, "etv": 0.0, "keywords": 0})
        p["etv"] += x["etv"]
        p["keywords"] += 1
    branded = sum(x["etv"] for x in rows if brand in x["keyword"].replace(" ", "").lower())
    share = (lambda v: round(100 * v / sampled, 1) if sampled else 0.0)
    top_pages = sorted(pages.values(), key=lambda p: -p["etv"])
    return {
        "est_monthly_visits": round(float(organic.get("etv") or 0)),
        "keywords_total": int(organic.get("count") or r.get("total_count") or 0),
        "keywords_sampled": len(rows),
        "brand_share": share(branded),
        "type_share": {t: share(v) for t, v in sorted(by_type.items(), key=lambda kv: -kv[1])},
        "top_pages": [{**p, "etv": round(p["etv"])} for p in top_pages[:10]],
        "pages_by_type": {t: [{**p, "etv": round(p["etv"])} for p in top_pages if p["type"] == t][:5]
                          for t in by_type},
        "pages_count_by_type": {t: sum(1 for p in top_pages if p["type"] == t) for t in by_type},
    }


# ------------------------------------------------------------ ads

def meta_ads_facts(data, domain, today):
    brand = brand_of(domain)
    ads = []
    for ad in (data or {}).get("results") or []:
        snap = ad.get("snapshot") or {}
        page = (ad.get("page_name") or snap.get("page_name") or "").lower()
        link = (snap.get("link_url") or "").lower()
        if link and brand_of_url(link) != brand:
            continue  # links somewhere else: likely a different company with a similar name
        if not link and squash(page) != brand:
            continue
        start = ad.get("start_date")
        if not start:
            continue
        started = datetime.fromtimestamp(int(start), tz=timezone.utc).date()
        body = ((snap.get("body") or {}).get("text") or snap.get("title") or "").strip()
        ads.append({"started": started.isoformat(), "days": (today - started).days,
                    "text": " ".join(body.split())[:140], "url": ad.get("url") or ""})
    long_run = [a for a in ads if a["days"] >= 30]
    oldest = max(ads, key=lambda a: a["days"]) if ads else None
    return {"active_ads": len(ads), "running_30_days": len(long_run), "oldest": oldest}


def brand_of_url(url):
    host = urlparse(url if "://" in url else "https://" + url).hostname or ""
    return brand_of(host) if host else ""


# ------------------------------------------------------------ social

def x_facts(data, today=None):
    """Posts from the last 12 months only, so an old viral post or a quiet
    account does not look busier than it is."""
    tweets = []
    for t in (data or {}).get("tweets") or []:
        legacy = t.get("legacy") or {}
        if t.get("is_retweet") or legacy.get("retweeted_status_result") or (legacy.get("full_text") or "").startswith("RT @"):
            continue
        views = int(((t.get("views") or {}).get("count")) or 0)
        note = (((t.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {}).get("text")
        tweets.append({"views": views, "likes": int(legacy.get("favorite_count") or 0),
                       "date": parse_x_date(legacy.get("created_at")),
                       "text": (note or legacy.get("full_text") or "")[:140].replace("\n", " "),
                       "url": t.get("url") or ""})
    dated = sorted(x["date"] for x in tweets if x["date"])
    last_post = dated[-1] if dated else None
    if today:
        cutoff = date.fromordinal(today.toordinal() - 365).isoformat()
        tweets = [x for x in tweets if x["date"] and x["date"] >= cutoff]
    seen = [x for x in tweets if x["views"] > 0]
    if not seen:
        return {"posts": 0, "last_post": last_post}
    top = max(seen, key=lambda x: x["views"])
    return {"posts": len(seen), "median_views": int(median(x["views"] for x in seen)), "top": top,
            "first": min(x["date"] for x in seen), "last": max(x["date"] for x in seen), "last_post": last_post}


def parse_x_date(text):
    try:
        return datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def linkedin_facts(data, today=None):
    posts = [p for p in (data or {}).get("posts") or [] if p.get("datePublished")]
    if not posts:
        return {"posts": 0}
    dates = sorted(p["datePublished"][:10] for p in posts)
    out = {"posts": len(posts), "first": dates[0], "last": dates[-1], "per_week": None}
    if len(posts) >= 3:  # fewer than three posts is too little to judge a rhythm
        end = today or date.fromisoformat(dates[-1])
        span = max((end - date.fromisoformat(dates[0])).days, 7)
        out["per_week"] = round(len(posts) / span * 7, 1)
    return out


# ------------------------------------------------------------ AI answers

def ai_answer_text(data):
    r = dfs_result(data)
    text = r.get("markdown") or ""
    if not text:
        for item in r.get("items") or []:
            text += " " + (item.get("markdown") or item.get("text") or "")
    return text


def squash(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def ai_mentions(data, brands):
    """Which of these brands an answer names, in the order they first appear.

    Uses the brand names DataForSEO pulls out of the answer, so a brand like
    "forms" is not counted just because the word "forms" is in the text."""
    text = ai_answer_text(data).lower()
    entities = {squash(n) for n in ai_brand_names(data)}
    found = []
    for b in brands:
        if entities and squash(b) not in entities:
            continue
        m = re.search(r"\b" + re.escape(b.lower()) + r"\b", text)
        if m:
            found.append((m.start(), b))
        elif entities:
            found.append((len(text), b))
    return [b for _, b in sorted(found)]


def ai_brand_names(data):
    """Brand names DataForSEO pulled out of the answer, top level and per
    paragraph, in order, without repeats."""
    r = dfs_result(data)
    names = []
    groups = [r.get("brand_entities") or []] + [(i or {}).get("brand_entities") or [] for i in r.get("items") or []]
    for group in groups:
        for e in group:
            name = (e.get("markdown") or e.get("title")) if isinstance(e, dict) else None
            if name and name not in names:
                names.append(name)
    return names


def slug_domain(domain):
    return re.sub(r"[^a-z0-9]+", "-", domain.lower().replace("www.", "")).strip("-")
