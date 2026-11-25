"""Write the one-page result: playbook.html, moves.csv, bill.csv, report.json."""

import csv
import html
import json
import os

REPO = "https://github.com/assisDevassy/growth-playbook-agent"
KIND_SOURCE = {"site": "DataForSEO website details", "competitors": "DataForSEO competitor domains",
               "ai_answer": "DataForSEO ChatGPT answers", "ranked": "DataForSEO ranked keywords",
               "meta_ads": "Meta Ad Library via ScrapeCreators", "x_posts": "X posts via ScrapeCreators",
               "linkedin_posts": "LinkedIn posts via ScrapeCreators"}


def e(x):
    return html.escape(str(x))


def num(v):
    return "–" if v is None else f"{int(round(v)):,}"


def engine(c):
    s = c.get("search")
    if not s or not s["keywords_sampled"]:
        return "No search data."
    if s["brand_share"] >= 50:
        return (f"{s['brand_share']:g}% of its search visits are people typing the name. "
                "Buyers hear about it somewhere else first, then search to sign up.")
    top = next(iter(s["type_share"].items()), None)
    if not top:
        return "No search data."
    return f"Most search visits land on {top[0]} ({top[1]:g}% of what we sampled)."


def row(c):
    s, a, li, x, ai = c.get("search"), c.get("ads"), c.get("linkedin"), c.get("x"), c.get("ai")
    top = next(iter(s["type_share"].items()), None) if s else None
    return [c["name"],
            num(s["est_monthly_visits"]) if s else "–",
            f"{s['brand_share']:g}%" if s else "–",
            f"{top[0]} ({top[1]:g}%)" if top else "–",
            ("30+" if a["active_ads"] >= 30 else str(a["active_ads"])) if a else "–",
            f"{li['per_week']:g}" if li and li.get("per_week") is not None else "–",
            num(x["median_views"]) if x and x.get("posts") else ("no posts in 12 months" if x else "–"),
            f"{len(ai['named_in'])} of {ai['asked']}" if ai else "–"]


CSS = """
body{background:#f6f1e7;color:#111;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;margin:0}
main{max-width:860px;margin:0 auto;padding:48px 24px 80px}
h1,h2,h3{font-family:Fraunces,"Cooper BT",Georgia,serif;font-weight:700;line-height:1.15}
h1{font-size:40px;margin:0 0 8px}h2{font-size:26px;margin:48px 0 12px}h3{font-size:20px;margin:0 0 6px}
.lede{font-size:19px;margin:0 0 4px}.meta{color:#555;font-size:14px}
table{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #d9d1c2;vertical-align:top}
th{font-weight:600;background:#efe7d8}
.move{background:#fff;border:1.5px solid #111;border-radius:14px;padding:20px 22px;margin:18px 0}
.tag{display:inline-block;font-size:12px;font-weight:600;border:1.5px solid #111;border-radius:99px;padding:2px 10px;margin-bottom:10px}
.label{font-weight:700}.proof li{margin:4px 0}.muted{color:#555}.small{font-size:13px}
.do{background:#f6f1e7;border-radius:10px;padding:10px 14px;margin-top:10px}
a{color:#111}footer{margin-top:56px;font-size:13px;color:#555}
"""


def render(report, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    a, you, comps = report["answers"], report["you"], report["competitors"]
    everyone = [you] + comps
    h = [f"<!doctype html><html lang=en><head><meta charset=utf-8>"
         f"<meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>Growth playbook: {e(a['company_name'])}</title><style>{CSS}</style></head><body><main>"]
    h.append(f"<h1>Growth playbook: {e(a['company_name'])}</h1>")
    h.append(f"<p class=lede>{e(a['company_name'])}: {e(a['sells'])}"
             + (f", for {e(a['to'])}" if a.get("to") else "") + ".</p>")
    h.append(f"<p class=meta>{e(report['site'])} · compared with "
             + ", ".join(e(c['name']) for c in comps)
             + f" · data pulled {e(report['date'])} · cost ${report['spent']:.2f}</p>")
    if a.get("example_note"):
        h.append(f"<p class='meta small'>{e(a['example_note'])}</p>")

    # How everyone grows
    h.append("<h2>How you grow, and how they grow</h2>")
    h.append("<table><tr><th>Company</th><th>Search visits a month (est.)</th><th>From people typing the name</th>"
             "<th>Where most search visits land</th><th>Active Meta ads</th><th>LinkedIn posts a week</th>"
             "<th>Median views on X (last 12 months)</th><th>Named by ChatGPT</th></tr>")
    for c in everyone:
        h.append("<tr>" + "".join(f"<td>{e(v)}</td>" for v in row(c)) + "</tr>")
    h.append("</table><ul>")
    for c in everyone:
        h.append(f"<li><span class=label>{e(c['name'])}:</span> {e(engine(c))}</li>")
    h.append("</ul>")

    # The moves
    moves = report["moves"]
    h.append(f"<h2>{len(moves) or 'No'} move{'s' if len(moves) != 1 else ''} to make</h2>")
    h.append("<p class=muted>Each move is something at least two of the three competitors do and that fits the "
             "team and budget you gave. Either you are not doing it yet, or you do it at less than half "
             "the level they do.</p>")
    for i, m in enumerate(moves, 1):
        tag = f"Done by {m['count']} of {len(m['competitors'])} competitors"
        if m.get("kind") == "more":
            tag += " · you do it, but far less"
        h.append(f"<div class=move><span class=tag>{e(tag)}</span><h3>{i}. {e(m['name'])}</h3>")
        h.append("<p class=label>The proof</p><ul class=proof>")
        for r in m["competitors"]:
            mark = "" if r["shows"] else " <span class=muted>(does not do this)</span>"
            name = next(c["name"] for c in comps if c["domain"] == r["domain"])
            h.append(f"<li><b>{e(name)}</b>{mark}: {e(r['proof'])}</li>")
        h.append(f"<li><b>You</b>: {e(m['you']['proof'])}</li></ul>")
        h.append(f"<p><span class=label>What it means.</span> {e(m['meaning'])}</p>")
        h.append(f"<div class=do><span class=label>Do this week.</span> {e(m['this_week'])}</div>")
        used = sorted({u for r in m["competitors"] for u in r["used"]})
        h.append(f"<p class='small muted'>Where this came from: {e(', '.join(KIND_SOURCE[u] for u in used))}, "
                 f"pulled {e(report['date'])}. Test: {e(m['test'])}</p></div>")

    # ChatGPT
    h.append("<h2>The ChatGPT check</h2><p class=muted>We asked ChatGPT three questions a buyer might ask. "
             "This shows which of the four companies it named, in the order it named them.</p><table>"
             "<tr><th>Question</th><th>Named, in order</th><th>Is "
             f"{e(a['company_name'])} named?</th></tr>")
    names = {c["brand"]: c["name"] for c in everyone}
    for q in report["ai"]:
        if q["named"] is None:
            h.append(f"<tr><td>{e(q['question'])}</td><td colspan=2>Not checked</td></tr>")
            continue
        order = ", ".join(names.get(b, b) for b in q["named"]) or "None of the four"
        yes = f"Yes, #{q['named'].index(you['brand']) + 1} of these four" if you["brand"] in q["named"] else "No"
        h.append(f"<tr><td>{e(q['question'])}</td><td>{e(order)}</td><td>{e(yes)}</td></tr>")
    h.append("</table>")

    # Left out / already
    if report["left_out"]:
        h.append("<h2>Moves we left out</h2><ul>")
        for m in report["left_out"]:
            h.append(f"<li><b>{e(m['name'])}</b> (done by {m['count']} of {len(m['competitors'])}). {e(m['why'])}</li>")
        h.append("</ul>")
    if report["already"]:
        h.append("<h2>What you already do well</h2><ul>")
        for m in report["already"]:
            h.append(f"<li><b>{e(m['name'])}</b>: {e(m['you']['proof'])}</li>")
        h.append("</ul>")

    # Why these competitors
    h.append("<h2>Why these three competitors</h2><ul>")
    cand = {c["domain"]: c for c in report.get("candidates") or []}
    for c in comps:
        info = cand.get(c["domain"])
        if info:
            why = f"named by ChatGPT in {info['ai_named']} of 3 answers, and ranks for {info['shared_searches']:,} of the same Google searches"
        else:
            why = "named by you"
        h.append(f"<li><b>{e(c['name'])}</b> ({e(c['domain'])}): {e(why)}.</li>")
    h.append("</ul>")

    # Bill
    h.append("<h2>The bill</h2><table><tr><th>Lookup</th><th>Source</th><th>Cost (USD)</th></tr>")
    for name, b in sorted(report["bill"].items()):
        h.append(f"<tr><td>{e(b['what'])}</td><td>{e(b['provider'])}</td><td>${b['usd']:.4f}</td></tr>")
    h.append(f"<tr><th>Total</th><th></th><th>${report['spent']:.4f} of a ${report['limit']:.2f} limit</th></tr></table>")
    if report["skipped"]:
        h.append("<p class=muted>Skipped to stay under the limit: " + e("; ".join(report["skipped"])) + "</p>")

    h.append("<footer>Meta ad counts show the first page of results, so 30+ means at least 30. "
             "A dash means no data: no account was found on the site or given in the answers. "
             "Search visits are estimates from DataForSEO, not anyone's real analytics. "
             "\"Sampled\" means the top 200 Google keywords for each site, by estimated visits. "
             "Every number traces to a saved raw file in this run's <code>raw/</code> folder. "
             f"Made with <a href='{REPO}'>Growth Playbook Agent</a>, open source.</footer>")
    h.append("</main></body></html>")
    with open(os.path.join(out_dir, "playbook.html"), "w") as f:
        f.write("\n".join(h))

    with open(os.path.join(out_dir, "moves.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "move", "competitors_doing_it", "proof", "what_it_means", "do_this_week"])
        for i, m in enumerate(moves, 1):
            proof = " | ".join(f"{r['domain']}: {r['proof']}" for r in m["competitors"] if r["shows"])
            w.writerow([i, m["name"] + (" (do more of it)" if m.get("kind") == "more" else ""), m["count"], proof,
                        m["meaning"], m["this_week"]])
    with open(os.path.join(out_dir, "bill.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lookup", "source", "usd"])
        for name, b in sorted(report["bill"].items()):
            w.writerow([b["what"], b["provider"], f"{b['usd']:.5f}"])
        w.writerow(["TOTAL", "", f"{report['spent']:.5f}"])
    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(report, f, indent=2, default=str)
