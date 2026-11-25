import json
import os
import tempfile
import unittest
from datetime import date
from unittest import mock

from gpa import signals as S
from gpa import sources
from gpa.moves import choose, load_moves
from gpa.run import run

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
EXAMPLES = os.path.join(ROOT, "examples")


def ranked(domain, rows, total_etv=1000):
    items = [{"keyword_data": {"keyword": k}, "ranked_serp_element": {"serp_item": {"url": f"https://{domain}{u}",
                                                                                   "relative_url": u, "etv": e}}}
             for k, u, e in rows]
    return {"tasks": [{"result": [{"metrics": {"organic": {"etv": total_etv, "count": len(rows)}}, "items": items}]}]}


class PageTypes(unittest.TestCase):
    def test_types(self):
        self.assertEqual(S.page_type("/"), "home page")
        self.assertEqual(S.page_type("/qr-code-generator/"), "free tools")
        self.assertEqual(S.page_type("/formstack-alternative/"), "comparison")
        self.assertEqual(S.page_type("/templates/job-application"), "templates")
        self.assertEqual(S.page_type("/262134348777061"), "user-made pages")
        self.assertEqual(S.page_type("/to/cVMXbdhw"), "user-made pages")
        self.assertEqual(S.page_type("/blog/what-is-a-dichotomous-question"), "guides and blog")
        self.assertEqual(S.page_type("/login"), "login")


class Search(unittest.TestCase):
    def test_shares_and_brand(self):
        data = ranked("acme.com", [("acme", "/", 50), ("acme login", "/login", 10),
                                   ("free pdf merger", "/pdf/merge/", 30), ("acme vs rival", "/acme-vs-rival", 10)])
        f = S.search_facts(data, "acme.com")
        self.assertEqual(f["brand_share"], 70.0)  # 'acme' appears in 3 keywords worth 70 of 100
        self.assertEqual(f["type_share"]["free tools"], 30.0)
        self.assertEqual(f["pages_count_by_type"]["comparison"], 1)
        self.assertEqual(f["est_monthly_visits"], 1000)


class AIAnswers(unittest.TestCase):
    def answer(self, text, brands):
        return {"tasks": [{"result": [{"markdown": text,
                                       "brand_entities": [{"markdown": b} for b in brands]}]}]}

    def test_word_forms_is_not_a_brand_mention(self):
        d = self.answer("Try Google Forms or Jotform. Both make forms.", ["Google Forms", "Jotform"])
        self.assertEqual(S.ai_mentions(d, ["forms", "jotform"]), ["jotform"])

    def test_order_follows_the_text(self):
        d = self.answer("Typeform is lovely. Jotform is best overall.", ["Jotform", "Typeform"])
        self.assertEqual(S.ai_mentions(d, ["jotform", "typeform"]), ["typeform", "jotform"])

    def test_subject_of_question_is_not_a_recommendation(self):
        d = self.answer("Alternatives to Youform: Tally and Fillout.", ["Tally", "Fillout"])
        self.assertEqual(S.ai_mentions(d, ["youform", "tally"]), ["tally"])


class Social(unittest.TestCase):
    def test_meta_ads_skip_other_companies(self):
        ads = {"results": [
            {"page_name": "TALLY WEiJL", "start_date": 1760000000, "snapshot": {"link_url": "https://tally-weijl.com"}},
            {"page_name": "Tally", "start_date": 1760000000, "snapshot": {"link_url": "https://tally.so/signup"}}]}
        f = S.meta_ads_facts(ads, "tally.so", date(2026, 11, 25))
        self.assertEqual(f["active_ads"], 1)

    def test_x_uses_last_12_months_and_ignores_missing_views(self):
        tweets = {"tweets": [
            {"views": {"count": "100"}, "legacy": {"created_at": "Mon Nov 10 10:00:00 +0000 2026", "full_text": "a"}},
            {"views": {"count": "300"}, "legacy": {"created_at": "Mon Nov 03 10:00:00 +0000 2026", "full_text": "b"}},
            {"legacy": {"created_at": "Mon Nov 03 10:00:00 +0000 2026", "full_text": "no views"}},
            {"views": {"count": "99999"}, "legacy": {"created_at": "Mon Jan 01 10:00:00 +0000 2024", "full_text": "old"}}]}
        f = S.x_facts(tweets, date(2026, 11, 25))
        self.assertEqual(f["posts"], 2)
        self.assertEqual(f["median_views"], 200)
        self.assertEqual(f["top"]["views"], 300)

    def test_linkedin_needs_three_posts_to_judge(self):
        one = {"posts": [{"datePublished": "2026-11-20T10:00:00Z"}]}
        self.assertIsNone(S.linkedin_facts(one, date(2026, 11, 25))["per_week"])


class Budget(unittest.TestCase):
    def test_never_spends_past_the_limit(self):
        with tempfile.TemporaryDirectory() as d:
            r = sources.Runner(d, limit_usd=0.05)
            fake = lambda req: {"cost": sources.ESTIMATE[req["kind"]]}
            with mock.patch.object(sources, "fetch", side_effect=fake):
                r.get(sources.ranked_request("a.com"))   # 0.036
                r.get(sources.ranked_request("b.com"))   # would make 0.072: skipped
                r.get(sources.site_request("a.com"))     # 0.012: fits
            self.assertLessEqual(r.spent, 0.05)
            self.assertEqual(len(r.skipped), 1)

    def test_replay_spends_nothing_and_lists_missing(self):
        with tempfile.TemporaryDirectory() as d:
            r = sources.Runner(d, replay=True)
            with mock.patch.object(sources, "fetch", side_effect=AssertionError("no live calls in replay")):
                self.assertIsNone(r.get(sources.site_request("a.com")))
            self.assertEqual(len(r.missing), 1)


def company(domain, free_tools=0, guides=0, ads30=0, ai=0):
    rows = [("x", "/", 100 - free_tools - guides)]
    if free_tools:
        rows.append(("free tool", "/free-tool", free_tools))
    if guides:
        rows.append(("how to", "/blog/how-to", guides))
    return {"domain": domain, "brand": S.brand_of(domain), "name": domain,
            "site": {"affiliate_tools": []}, "search": S.search_facts(ranked(domain, rows), domain),
            "ads": {"active_ads": ads30, "running_30_days": ads30,
                    "oldest": {"started": "2026-01-01", "days": 300, "text": ""}} if ads30 else
                   {"active_ads": 0, "running_30_days": 0, "oldest": None},
            "x": None, "linkedin": None, "ai": {"asked": 3, "named_in": ["q"] * ai}}


class Choosing(unittest.TestCase):
    def test_repeated_fit_and_gaps(self):
        you = company("you.com", free_tools=20)  # passes the 15% test, but far below the rivals
        rivals = [company("a.com", free_tools=50, ads30=5, ai=3), company("b.com", free_tools=40, ads30=4, ai=2),
                  company("c.com", guides=60, ai=1)]
        picked, already, left = choose(you, rivals, {"team_size": 2, "monthly_budget_usd": 200})
        weak = company("weak.com", free_tools=5)  # under the test: counted as not doing it yet
        self.assertEqual({m["id"]: m for m in choose(weak, rivals, {"team_size": 2})[0]}["free_tools"]["kind"], "new")
        ids = {m["id"]: m for m in picked}
        self.assertIn("ai_answers", ids)                     # all three are named, you are not
        self.assertEqual(ids["free_tools"]["kind"], "more")  # you do it, at under half their level
        left_ids = {m["id"]: m["why"] for m in left}
        self.assertIn("long_ads", left_ids)                  # repeated, but over the budget given
        self.assertIn("guides", left_ids)                    # only one rival does it
        self.assertIn("one-off", left_ids["guides"])

    def test_every_move_has_plain_text(self):
        for m in load_moves():
            for k in ("name", "test", "meaning", "this_week", "needs_text"):
                self.assertTrue(m[k].strip(), (m["id"], k))


class Examples(unittest.TestCase):
    def replay(self, name, site):
        with open(os.path.join(EXAMPLES, name, "answers.json")) as f:
            answers = json.load(f)
        with tempfile.TemporaryDirectory() as out:
            raw = os.path.join(out, "raw")
            os.makedirs(raw)
            src = os.path.join(EXAMPLES, name, "raw")
            for fn in os.listdir(src):
                with open(os.path.join(src, fn)) as a, open(os.path.join(raw, fn), "w") as b:
                    b.write(a.read())
            with mock.patch.object(sources, "fetch", side_effect=AssertionError("no live calls")):
                return run(site, answers, out, replay=True)

    def test_youform(self):
        r = self.replay("youform", "youform.com")
        self.assertEqual(r["status"], "done")
        self.assertEqual([c["domain"] for c in r["competitors"]], ["jotform.com", "typeform.com", "fillout.com"])
        self.assertEqual([m["id"] for m in r["moves"]], ["ai_answers", "free_tools"])
        self.assertLessEqual(r["spent"], 0.50)

    def test_tally(self):
        r = self.replay("tally", "tally.so")
        self.assertEqual([m["id"] for m in r["moves"]], ["free_tools"])
        self.assertEqual(r["moves"][0]["kind"], "more")
        self.assertIn("long_ads", [m["id"] for m in r["left_out"]])
        self.assertLessEqual(r["spent"], 0.50)


class Hygiene(unittest.TestCase):
    def test_only_named_data_sources(self):
        """The repo names its real data sources and no middleman."""
        banned = "tr" + "eg"
        for base, _, files in os.walk(ROOT):
            if ".git" in base:
                continue
            for fn in files:
                if fn.endswith((".py", ".md", ".json", ".html", ".csv", ".txt")):
                    with open(os.path.join(base, fn), errors="ignore") as f:
                        self.assertNotIn(banned, f.read().lower(), os.path.join(base, fn))


if __name__ == "__main__":
    unittest.main()
