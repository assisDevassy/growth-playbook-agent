"""Every paid lookup the agent can make, and the one place that makes it.

Two data accounts cover everything:
  DataForSEO      search data, competitors, website details, ChatGPT answers
  ScrapeCreators  Meta ads, LinkedIn company posts, X posts

A run never spends past its limit. Each lookup has a price estimate; before a
lookup goes out, the runner checks that what was already spent plus that
estimate stays under the limit. If not, the lookup is skipped and the page
says so.

Every answer is saved as raw JSON in the run folder, so a run can be read
again, checked, or rebuilt later without paying twice ("replay").
"""

import base64
import json
import os
import re
import urllib.parse
import urllib.request

DATAFORSEO = "https://api.dataforseo.com/v3"
SCRAPECREATORS = "https://api.scrapecreators.com"

# Price per ScrapeCreators credit, used for the bill. Check what your own plan
# charges per credit and change it here.
CREDIT_USD = 0.00188

# Price estimates per lookup, in US dollars. DataForSEO reports the exact
# charge in every answer; that number goes in the bill when it is there.
ESTIMATE = {
    "site": 0.012,         # website details and technologies
    "competitors": 0.0124,  # sites that rank for the same searches
    "ai_answer": 0.004,    # one ChatGPT answer
    "ranked": 0.036,       # top 200 keywords a site ranks for
    "meta_ads": CREDIT_USD,
    "x_posts": CREDIT_USD,
    "linkedin_posts": CREDIT_USD,
}

US = 2840  # DataForSEO location code for the United States


class OverBudget(Exception):
    pass


class Missing(Exception):
    """Replay mode found no saved answer for a lookup."""


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


# ---------------------------------------------------------------- requests

def site_request(domain):
    return {"name": f"site__{slug(domain)}", "kind": "site", "provider": "DataForSEO",
            "method": "POST", "path": "/domain_analytics/technologies/domain_technologies/live",
            "body": [{"target": domain}],
            "what": f"Website details and technologies for {domain}"}


def competitors_request(domain, limit=20):
    return {"name": f"competitors__{slug(domain)}", "kind": "competitors", "provider": "DataForSEO",
            "method": "POST", "path": "/dataforseo_labs/google/competitors_domain/live",
            "body": [{"target": domain, "location_code": US, "language_code": "en",
                      "exclude_top_domains": True, "limit": limit}],
            "what": f"Sites that rank for the same Google searches as {domain} (US)"}


def ai_answer_request(question):
    return {"name": f"ai__{slug(question)}", "kind": "ai_answer", "provider": "DataForSEO",
            "method": "POST", "path": "/ai_optimization/chat_gpt/llm_scraper/live/advanced",
            "body": [{"keyword": question, "location_code": US, "language_code": "en"}],
            "what": f'ChatGPT\'s answer to "{question}"'}


def ranked_request(domain, limit=200):
    return {"name": f"ranked__{slug(domain)}", "kind": "ranked", "provider": "DataForSEO",
            "method": "POST", "path": "/dataforseo_labs/google/ranked_keywords/live",
            "body": [{"target": domain, "location_code": US, "language_code": "en", "limit": limit,
                      "order_by": ["ranked_serp_element.serp_item.etv,desc"]}],
            "what": f"Top {limit} Google keywords {domain} ranks for (US), by estimated visits"}


def meta_ads_request(company):
    return {"name": f"meta__{slug(company)}", "kind": "meta_ads", "provider": "ScrapeCreators",
            "method": "GET", "path": "/v1/facebook/adLibrary/company/ads",
            "query": {"companyName": company, "status": "ACTIVE"},
            "what": f"Active ads in the Meta Ad Library for {company}"}


def x_posts_request(handle):
    return {"name": f"x__{slug(handle)}", "kind": "x_posts", "provider": "ScrapeCreators",
            "method": "GET", "path": "/v1/twitter/user-tweets", "query": {"handle": handle},
            "what": f"Recent posts from @{handle} on X"}


def linkedin_posts_request(url):
    return {"name": f"linkedin__{slug(url.rstrip('/').split('/')[-1])}", "kind": "linkedin_posts",
            "provider": "ScrapeCreators", "method": "GET", "path": "/v1/linkedin/company/posts",
            "query": {"url": url}, "what": f"Recent posts from the LinkedIn page {url}"}


# ---------------------------------------------------------------- runner

class Runner:
    """Makes lookups (live) or reads saved ones (replay), within a budget."""

    def __init__(self, raw_dir, limit_usd=0.50, replay=False, confirm=None):
        self.raw_dir = raw_dir
        self.limit = limit_usd
        self.replay = replay
        self.confirm = confirm  # callable(request, estimate) -> bool, or None
        os.makedirs(raw_dir, exist_ok=True)
        self.ledger_path = os.path.join(raw_dir, "_ledger.json")
        self.ledger = self._load_ledger()
        self.missing = []
        self.skipped = []

    def _load_ledger(self):
        if os.path.exists(self.ledger_path):
            with open(self.ledger_path) as f:
                return json.load(f)
        return {}

    def _save_ledger(self):
        with open(self.ledger_path, "w") as f:
            json.dump(self.ledger, f, indent=2, sort_keys=True)

    @property
    def spent(self):
        return round(sum(e["usd"] for e in self.ledger.values()), 5)

    def get(self, req):
        """Return the provider's answer for a request, or None if skipped."""
        path = os.path.join(self.raw_dir, req["name"] + ".json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            if req["name"] not in self.ledger:
                self.ledger[req["name"]] = self._entry(req, data)
                self._save_ledger()
            return data
        if self.replay:
            self.missing.append(req)
            return None
        est = ESTIMATE[req["kind"]]
        if self.spent + est > self.limit + 1e-9:
            self.skipped.append(req)
            return None
        if self.confirm and not self.confirm(req, est):
            self.skipped.append(req)
            return None
        data = fetch(req)
        with open(path, "w") as f:
            json.dump(data, f)
        self.ledger[req["name"]] = self._entry(req, data)
        self._save_ledger()
        return data

    def _entry(self, req, data):
        return {"what": req["what"], "provider": req["provider"], "kind": req["kind"],
                "usd": actual_cost(req, data)}


def actual_cost(req, data):
    if req["provider"] == "DataForSEO" and isinstance(data, dict) and "cost" in data:
        return float(data["cost"] or 0)
    if req["provider"] == "ScrapeCreators" and isinstance(data, dict) and "credits_charged" in data:
        return round(float(data["credits_charged"] or 0) * CREDIT_USD, 5)
    return ESTIMATE[req["kind"]]


def fetch(req):
    """Live call. Needs your own keys in environment variables."""
    if req["provider"] == "DataForSEO":
        login = os.environ.get("DATAFORSEO_LOGIN")
        password = os.environ.get("DATAFORSEO_PASSWORD")
        if not (login and password):
            raise SystemExit("Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD first (see README).")
        token = base64.b64encode(f"{login}:{password}".encode()).decode()
        r = urllib.request.Request(DATAFORSEO + req["path"], method="POST",
                                   data=json.dumps(req["body"]).encode(),
                                   headers={"Authorization": "Basic " + token,
                                            "Content-Type": "application/json"})
    else:
        key = os.environ.get("SCRAPECREATORS_API_KEY")
        if not key:
            raise SystemExit("Set SCRAPECREATORS_API_KEY first (see README).")
        url = SCRAPECREATORS + req["path"] + "?" + urllib.parse.urlencode(req["query"])
        r = urllib.request.Request(url, headers={"x-api-key": key})
    with urllib.request.urlopen(r, timeout=180) as resp:
        return json.loads(resp.read().decode())
