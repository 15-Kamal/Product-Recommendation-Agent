# Product Recommendation Agent

An AI agent that takes a user's stated preferences (and past behavior, when
available) and returns a ranked list of product recommendations, each with a
specific reason — falling back gracefully to popular picks when there's no
data on the user at all.

Built for the AI Agent Challenge — Product Recommendation Agent (Intermediate) track.

## How it works

1. **Content-based filtering (Python, no LLM):** every product is scored
   against the user's stated preferences (category match, tag overlap, price
   fit) and behavior (purchased/rated categories get a boost). The catalogue
   is narrowed to a shortlist of the top 8 candidates.
2. **Cold-start detection:** if a user has no preferences *and* no behavior
   on file, filtering skips straight to a popularity ranking (highest-rated
   products) instead of scoring against nothing.
3. **LLM ranking + reasoning:** the shortlist and user profile are sent to
   Google's Gemini API, which picks and ranks the best 3–5 and writes one
   grounded sentence explaining each pick — referencing the user's actual
   preferences or behavior, or explicitly flagging cold-start picks as
   popularity-based.
4. **Output:** shown in the terminal with explicit rank numbers.

## Project structure

```
product-recommendation-agent/
├── agent.py              # main script: filtering, LLM call, CLI, display
├── data/
│   ├── products.json     # product catalogue (category, price, tags, rating, ...)
│   └── users.json        # 3-4 sample user profiles, including one cold-start case
├── requirements.txt
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

This only lasts for the current terminal session. To persist it on Windows
across sessions: `setx GOOGLE_API_KEY "your-key-here"`, then open a **new**
terminal window.

## Run it

```bash
python agent.py
```

You'll be prompted to choose:
- **1** — type in your own preferences (interactive, live recommendation)
- **2** — replay the 4 saved sample profiles (batch/demo mode — this is what
  generates the sample deliverable output)

## Sample user profiles

| ID | Name | Signal type |
|---|---|---|
| U1 | Budget Beth | Preferences + behavior (viewed) |
| U2 | Loyal Leo | Behavior only (purchase + rating) |
| U3 | Tag-Driven Tia | Preferences only, no behavior |
| U4 | New User Nick | **Cold start** — no data at all |

## Design choices

- **Hybrid pipeline, not LLM-only:** cheap, transparent Python scoring
  narrows the catalogue before the LLM ever sees it. This keeps API calls
  fast/cheap and keeps the "similarity" step auditable — you can inspect
  exactly why a product was shortlisted without asking the model.
- **Content-based filtering:** weighted score = category match (+3) + tag
  overlap (+1 per matching tag) + price-range fit (+2) + behavior boost (+2
  if the user has purchased/rated something in that category).
- **Cold start handled structurally, not guessed:** `has_signal()` checks
  whether *any* value across preferences and behavior is non-empty. Only if
  both are fully empty does it fall back to a popularity ranking — and the
  LLM is explicitly told to say so in its reasoning, rather than pretending
  it's personalized.
- **Structured LLM output:** `response_mime_type="application/json"` on the
  Gemini call forces valid JSON back, and `thinking_budget=0` disables
  Gemini's default reasoning-token overhead — this task only needs ranking
  plus a one-line reason, not deep chain-of-thought, and disabling it fixed
  truncated responses during testing.

## Tradeoffs & limitations

- No collaborative filtering — recommendations only use this one profile's
  preferences/behavior and product attributes, not what similar users liked.
- Cold start falls back to global popularity rather than an onboarding quiz,
  to keep the CLI a single-turn interaction.
- The interactive ("type your own preferences") session isn't saved back
  into `data/users.json` — it's a one-off run, not a persisted profile.
- No retry logic on API failures (network issues, invalid key) — they
  surface directly rather than being retried, which is acceptable for this
  scope but would need hardening for production use.

## Deliverables checklist

- [x] Product catalogue — `data/products.json`
- [x] 3–4 sample user profiles — `data/users.json` (includes one cold-start
  case, U4)
- [x] Rationale for every recommendation — every ranked item includes a
  `reason` field grounded in the user's actual profile
