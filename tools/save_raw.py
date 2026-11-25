"""Save a provider answer you fetched some other way into a run's raw/ folder,
so the agent can build the page from it with --replay.

Useful when an AI agent fetches the data for you through its own data tools.
The file can be the provider's JSON answer, or a wrapper with it under "body".

usage: python3 tools/save_raw.py <answer file> <dest raw json> [--trim-ranked|--trim-meta|--trim-x]

--trim-ranked keeps the DataForSEO ranked-keywords structure but drops the
fields the agent never reads (backlinks, SERP features, history), so example
files stay small. Everything the code reads is kept as it came back.
"""
import json, sys
src, dest = sys.argv[1], sys.argv[2]
d = json.load(open(src))
if isinstance(d, list):
    d = json.loads(d[0]["text"])
body = d["body"] if "body" in d else d
if "--trim-ranked" in sys.argv:
    for t in body["tasks"]:
        for r in t["result"] or []:
            r["items"] = [{"keyword_data": {"keyword": i["keyword_data"]["keyword"],
                                            "keyword_info": {"search_volume": i["keyword_data"]["keyword_info"].get("search_volume")}},
                           "ranked_serp_element": {"serp_item": {k: i["ranked_serp_element"]["serp_item"].get(k)
                                                                  for k in ("type", "rank_group", "url", "relative_url", "etv")}}}
                          for i in r.get("items") or []]
            r["metrics"] = {"organic": {k: r["metrics"]["organic"].get(k) for k in ("etv", "count")}}
    body["_note"] = "Trimmed to the fields the agent reads."
if "--trim-meta" in sys.argv:
    keep = ("ad_archive_id", "is_active", "page_id", "page_name", "start_date", "start_date_string", "url", "publisher_platform")
    body["results"] = [{**{k: a.get(k) for k in keep},
                        "snapshot": {"page_name": (a.get("snapshot") or {}).get("page_name"),
                                     "link_url": (a.get("snapshot") or {}).get("link_url"),
                                     "title": (a.get("snapshot") or {}).get("title"),
                                     "body": {"text": (((a.get("snapshot") or {}).get("body") or {}).get("text") or "")[:400]}}}
                       for a in body.get("results") or []]
    body["_note"] = "Trimmed to the fields the agent reads."
if "--trim-x" in sys.argv:
    out = []
    for t in body.get("tweets") or []:
        lg = t.get("legacy") or {}
        note = (((t.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {}).get("text")
        out.append({"rest_id": t.get("rest_id"), "url": t.get("url"), "views": t.get("views"),
                    "legacy": {k: lg.get(k) for k in ("created_at", "full_text", "favorite_count", "retweet_count", "reply_count")},
                    **({"note_tweet": {"note_tweet_results": {"result": {"text": note}}}} if note else {}),
                    **({"is_retweet": True} if lg.get("retweeted_status_result") else {})})
    body["tweets"] = out
    body["_note"] = "Trimmed to the fields the agent reads."
json.dump(body, open(dest, "w"))
print(dest, "cost", body.get("cost", body.get("credits_charged")))
