# Product Recommendation Agent

Takes a user's stated preferences, past behavior, or a plain free-text
request, and returns a ranked, reasoned list of product recommendations —
falling back gracefully to popular picks when nothing is known about the
user yet.

## How it works

1. **SQLite database** — auto-created and seeded from `data/products.json`
   / `data/users.json` the first time `agent.py` runs. After that, the
   database (`agent.db`) is the source of truth.
2. **Gemini agent** (`gemini-2.5-flash`) is given two tools and decides for
   itself when to call them:
   - `filter_catalogue` — deterministic content-based scoring (category
     match, tag overlap, price fit, behavior boost), written in plain
     Python, no LLM involved.
   - `get_user_history` — reads the user's past recommendations from the
     database, so the agent can avoid repeating picks.
3. The model interprets the request, calls whichever tools it needs (Gemini's
   SDK handles the call-and-loop-back automatically — there's no manual
   orchestration loop in this code), and writes the final ranked answer as
   plain text.
4. The result is printed and logged back to the database.

## Project structure

```
product-recommendation-agent/
├── agent.py              # CLI entry point: DB, scoring, tools, orchestration
├── test_agent.py          # unit tests - no real API calls
├── data/
│   ├── products.json      # 21 products across 5 categories
│   └── users.json         # 4 sample profiles, incl. one cold-start case
├── agent.db                # auto-generated on first run - gitignored
├── requirements.txt
├── .gitignore
└── README.md
```

## Install

```bash
git clone <your-repo-url>
cd product-recommendation-agent
pip install -r requirements.txt
```

## Configure your API key

Get a free key at [Google AI Studio](https://aistudio.google.com) → "Get API key".

| Shell | Command |
|---|---|
| Command Prompt | `set GOOGLE_API_KEY=your-key-here` |
| PowerShell | `$env:GOOGLE_API_KEY = "your-key-here"` |
| macOS/Linux/Git Bash | `export GOOGLE_API_KEY="your-key-here"` |

Only lasts for the current terminal session. To persist it on Windows:
`setx GOOGLE_API_KEY "your-key-here"`, then open a **new** terminal window.

## Run it

```bash
python agent.py
```

- **1** — describe what you're looking for in your own words
- **2** — replay the 4 saved sample profiles (batch/demo mode)

## Capturing a sample run (the "Recommendation output" deliverable)

Option 2 only needs one keypress, so it can be captured non-interactively:

```bash
# Windows Command Prompt
echo 2| python agent.py > outputs\sample_run.txt

# macOS / Linux / Git Bash
echo 2 | python agent.py > outputs/sample_run.txt
```

## Testing

```bash
python -m unittest test_agent.py -v
```

8 tests: database round-trips against an in-memory SQLite DB, scoring math,
and the agent's tool-calling wired up against a mocked Gemini client. None
of them touch the real API or your daily quota.

## Sample user profiles

| ID | Name | Signal type |
|---|---|---|
| U1 | Budget Beth | Preferences + behavior |
| U2 | Loyal Leo | Behavior only (a past purchase) |
| U3 | Tag-Driven Tia | Preferences only |
| U4 | New User Nick | **Cold start** — no data at all |

## Design choices

- **Hybrid, not LLM-only:** `score_product` does the actual filtering math
  in plain Python — cheap, deterministic, and auditable. Gemini's job is
  deciding *when* to call it and *how* to parametrize it from a natural
  language request, then reasoning over the results.
- **Real orchestration, not a fixed pipeline:** `filter_catalogue` and
  `get_user_history` are passed directly as `tools=[...]` — Gemini's SDK
  detects plain Python functions automatically, calls them, and loops back
  with the result until the model has enough to answer. There's no
  hand-written "call tool → parse → call tool again" loop in this code;
  that behavior was confirmed against the SDK's own source, not assumed.
- **SQLite over a bigger database:** real persistence — specifically a
  recommendation history log that flat JSON files couldn't give — with zero
  server to run and no dependency beyond the Python standard library.
- **Cold start is detected inside the tool itself:** if Gemini calls
  `filter_catalogue` with empty categories and tags (because it has nothing
  to go on), the function falls back to a popularity ranking and flags
  `is_cold_start: true` in its response, so the model is instructed to say
  so plainly rather than inventing a personalized-sounding reason.
- **Plain text output, not structured JSON:** the system prompt asks for a
  numbered list directly, which removes JSON-parsing and error-handling
  code entirely while still giving a clearly ranked, readable answer.
- **Graceful degradation on API errors:** a rate limit or other API error
  on one user no longer crashes the whole batch run — it prints a clear
  skip message and the loop continues to the next profile.

## Tradeoffs & limitations

- No collaborative filtering — recommendations use only this one profile's
  preferences/behavior and product attributes, not what similar users liked.
- Free-tier Gemini quota is 20 requests/day for this model, and a single
  `recommend()` call can cost more than one request if the agent calls both
  tools — a full 4-profile batch run can use up the daily budget faster
  than it looks like it should.
- The "describe your own request" live path shares a single `LIVE` user ID,
  so recommendation history isn't tracked per distinct real person.
- No automatic retry/backoff on a rate-limited call — it's reported and
  skipped, not retried.

## Deliverables checklist

- [x] Product catalogue — `data/products.json` (21 products, 5 categories)
- [x] 3–4 sample user profiles — `data/users.json`, including one cold-start
  case (U4)
- [x] Rationale for every recommendation — enforced by the system prompt's
  "ONE sentence reason... never generic" instruction on every item
