# Instructions for an AI coding agent

You are running Growth Playbook Agent for someone. Follow these steps in order.

1. **Check the keys.** The person needs `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` and
   `SCRAPECREATORS_API_KEY` set in the environment. If any is missing, stop and point them to
   the "Accounts you need" section of the README. Never ask them to paste a password into the chat.

2. **Ask four things**, in plain words, and write the answers to `runs/<site>/answers.json`:
   - What they sell, in the words a buyer would type into Google (for example "online form builder").
   - Who they sell to (optional).
   - How many people work on growth, including them.
   - Their monthly marketing budget in US dollars (0 is a fine answer).

   Also fill `company_name`. If they know their LinkedIn page or X handle, or their competitors',
   add them under `socials` (see `examples/tally/answers.json`). Do not guess handles.

3. **Run it with the price check on:**

   ```
   python3 -m gpa run <site>
   ```

   Each paid lookup asks before it runs. Show the person the price and let them answer.
   The default spending limit is $0.50. Change it only if the person asks (`--limit`).

4. **Open the page** at `runs/<site>/playbook.html` and walk the person through it:
   start with the moves, then "Moves we left out", then the bill. Do not add moves the page
   does not contain, and do not round or restate numbers differently from the page.

5. **If they want a change** (different competitors, a bigger budget answer), edit
   `answers.json` and run again with `--replay` for anything already fetched. Saved lookups are
   never paid for twice.

The agent only reads public data and writes a report. It never posts, sends or spends.
