"""Command line.

  python3 -m gpa ask yoursite.com              # 1 lookup, then 4 quick questions
  python3 -m gpa run yoursite.com              # the full run, under the limit
  python3 -m gpa run yoursite.com --replay     # rebuild the page from saved data, free
"""

import argparse
import json
import os
import sys

from . import signals as S
from .page import render
from .run import run
from .sources import Runner, site_request


def ask(args):
    out = args.out or os.path.join("runs", S.slug_domain(args.site))
    runner = Runner(os.path.join(out, "raw"), limit_usd=args.limit, replay=args.replay)
    data = runner.get(site_request(args.site))
    facts = S.site_facts(data, args.site) if data else {"title": "", "description": ""}
    print(f"\nYour homepage says: {facts['title']}\n  {facts['description']}\n")
    a = {"company_name": input("Company name: ").strip() or S.brand_of(args.site).title(),
         "sells": input("What you sell, in the words a buyer would search (e.g. 'online form builder'): ").strip(),
         "to": input("Who you sell to (e.g. 'small marketing teams'), or leave blank: ").strip(),
         "team_size": int(input("How many people work on growth, including you? ") or 1),
         "monthly_budget_usd": float(input("Monthly budget for marketing, in US dollars (0 is fine): ") or 0),
         "tried": [t.strip() for t in input("What have you already tried? (comma separated) ").split(",") if t.strip()]}
    with open(os.path.join(out, "answers.json"), "w") as f:
        json.dump(a, f, indent=2)
    print(f"\nSaved {out}/answers.json. Next: python3 -m gpa run {args.site}")


def confirm(req, est):
    reply = input(f"Next: {req['what']} ({req['provider']}, about ${est:.3f}). Go ahead? [Y/n] ")
    return reply.strip().lower() in ("", "y", "yes")


def run_cmd(args):
    out = args.out or os.path.join("runs", S.slug_domain(args.site))
    path = args.answers or os.path.join(out, "answers.json")
    if not os.path.exists(path):
        sys.exit(f"No answers yet. Run: python3 -m gpa ask {args.site}")
    with open(path) as f:
        answers = json.load(f)
    report = run(args.site, answers, out, limit_usd=args.limit, replay=args.replay,
                 confirm=None if (args.yes or args.replay) else confirm)
    if report["status"] == "missing":
        print("Saved data is missing for these lookups:")
        for r in report["missing"]:
            print(json.dumps({k: r[k] for k in r if k in ("name", "provider", "method", "path", "body", "query")}))
        sys.exit(3)
    render(report, out)
    print(f"Done. {len(report['moves'])} moves. Spent ${report['spent']:.4f} of ${args.limit:.2f}.")
    print(f"Open {os.path.join(out, 'playbook.html')}")


def main():
    p = argparse.ArgumentParser(prog="gpa", description="Growth Playbook Agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("ask", ask), ("run", run_cmd)):
        s = sub.add_parser(name)
        s.add_argument("site", help="your website, e.g. tally.so")
        s.add_argument("--out", help="run folder (default runs/<site>)")
        s.add_argument("--limit", type=float, default=0.50, help="spending limit in USD (default 0.50)")
        s.add_argument("--replay", action="store_true", help="only use saved data, spend nothing")
        if name == "run":
            s.add_argument("--answers", help="answers file (default <run folder>/answers.json)")
            s.add_argument("--yes", action="store_true", help="skip the price check before each lookup")
        s.set_defaults(fn=fn)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
