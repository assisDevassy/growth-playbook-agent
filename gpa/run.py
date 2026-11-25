"""The whole run, step by step. Each step reads or fetches through the Runner,
so a run can stop part way (budget, missing keys) and pick up again later."""

import json
import os
from datetime import date

from . import signals as S
from .moves import choose
from .sources import (Runner, ai_answer_request, competitors_request, linkedin_posts_request,
                      meta_ads_request, ranked_request, site_request, x_posts_request)

# Big sites that rank for everything. They are never picked as competitors.
NOT_COMPETITORS = {"g2.com", "capterra.com", "getapp.com", "softwareadvice.com", "trustradius.com",
                   "producthunt.com", "reddit.com", "youtube.com", "medium.com", "forbes.com",
                   "techradar.com", "zapier.com", "hubspot.com", "github.com", "wikipedia.org",
                   "linkedin.com", "quora.com", "nerdwallet.com", "investopedia.com", "pcmag.com",
                   "canva.com", "microsoft.com", "google.com", "apple.com", "adobe.com", "amazon.com"}


def questions(answers):
    sells = answers["sells"]
    name = answers["company_name"]
    q = [f"What is the best {sells}?", f"What are the best alternatives to {name}?"]
    q.append(f"What is the best {sells} for {answers['to']}?" if answers.get("to")
             else f"Which {sells} should a small business use?")
    return q


def pick_competitors(you_domain, comp_data, ai_data, limit=3):
    """Rank candidates: named by ChatGPT first, then shared Google searches."""
    r = S.dfs_result(comp_data)
    you_brand = S.brand_of(you_domain)
    cands = []
    for item in r.get("items") or []:
        d = (item.get("domain") or "").lower().replace("www.", "")
        if not d or d in NOT_COMPETITORS or S.brand_of(d) == you_brand:
            continue
        brand = S.brand_of(d)
        named = sum(1 for d in ai_data if d and S.ai_mentions(d, [brand]))
        cands.append({"domain": d, "brand": brand, "shared_searches": int(item.get("intersections") or 0),
                      "ai_named": named})
    cands.sort(key=lambda c: (-c["ai_named"], -c["shared_searches"]))
    named_first = [c for c in cands if c["ai_named"]] + [c for c in cands if not c["ai_named"]]
    return named_first[:limit], cands[:12]


def company(runner, domain, display_name, answers, today, ai_data, ai_qs):
    socials = (answers.get("socials") or {}).get(domain, {})
    site_data = runner.get(site_request(domain))
    site = S.site_facts(site_data, domain) if site_data else None
    c = {"domain": domain, "brand": S.brand_of(domain), "name": display_name, "site": site,
         "socials_source": {}}
    linkedin = socials.get("linkedin") or (site or {}).get("linkedin_url")
    handle = socials.get("x") or (site or {}).get("x_handle")
    c["socials_source"] = {"linkedin": "given" if socials.get("linkedin") else ("site" if linkedin else None),
                           "x": "given" if socials.get("x") else ("site" if handle else None)}
    ranked = runner.get(ranked_request(domain))
    c["search"] = S.search_facts(ranked, domain) if ranked else None
    ads = runner.get(meta_ads_request(display_name))
    c["ads"] = S.meta_ads_facts(ads, domain, today) if ads is not None else None
    c["x"] = S.x_facts(runner.get(x_posts_request(handle)), today) if handle else None
    c["x_handle"] = handle
    c["linkedin"] = S.linkedin_facts(runner.get(linkedin_posts_request(linkedin)), today) if linkedin else None
    c["linkedin_url"] = linkedin
    named = [q for q, d in zip(ai_qs, ai_data) if d and S.ai_mentions(d, [c["brand"]])]
    c["ai"] = {"asked": sum(1 for d in ai_data if d), "named_in": named} if any(ai_data) else None
    return c


def run(site, answers, out_dir, limit_usd=0.50, replay=False, confirm=None):
    raw = os.path.join(out_dir, "raw")
    runner = Runner(raw, limit_usd=limit_usd, replay=replay, confirm=confirm)
    meta_path = os.path.join(raw, "_run.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            today = date.fromisoformat(json.load(f)["date"])
    else:
        today = date.today()
        with open(meta_path, "w") as f:
            json.dump({"date": today.isoformat(), "site": site}, f)

    # Step 1: you, the competitor list, and three ChatGPT answers.
    runner.get(site_request(site))
    comp_data = runner.get(competitors_request(site))
    ai_qs = questions(answers)
    ai_data = [runner.get(ai_answer_request(q)) for q in ai_qs]
    if runner.missing:
        return {"status": "missing", "missing": runner.missing}

    # Step 2: pick three competitors, unless you named them.
    if answers.get("competitors"):
        chosen = [{"domain": d, "brand": S.brand_of(d), "given": True} for d in answers["competitors"][:3]]
        candidates = []
    else:
        chosen, candidates = pick_competitors(site, comp_data or {}, ai_data)

    # Step 3: the same lookups for all four sites.
    names = answers.get("names") or {}
    you = company(runner, site, answers["company_name"], answers, today, ai_data, ai_qs)
    rivals = [company(runner, c["domain"], names.get(c["domain"], c["brand"].title()), answers, today,
                      ai_data, ai_qs) for c in chosen]
    if runner.missing:
        return {"status": "missing", "missing": runner.missing}

    # Who ChatGPT named, per question, among the four.
    brands = [you["brand"]] + [r["brand"] for r in rivals]
    ai_table = [{"question": q, "named": S.ai_mentions(d, brands) if d else None,
                 "other_brands": S.ai_brand_names(d)[:8] if d else []}
                for q, d in zip(ai_qs, ai_data)]

    picked, already, left_out = choose(you, rivals, answers)
    return {"status": "done", "date": today.isoformat(), "site": site, "answers": answers,
            "you": you, "competitors": rivals, "candidates": candidates, "ai": ai_table,
            "moves": picked, "already": already, "left_out": left_out,
            "bill": runner.ledger, "spent": runner.spent, "limit": limit_usd,
            "skipped": [r["what"] for r in runner.skipped]}
