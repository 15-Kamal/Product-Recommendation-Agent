"""
Product Recommendation Agent
Takes a user's stated preferences (and past behavior, when available) and
produces a ranked, reasoned list of product recommendations - falling back
gracefully to popular picks when nothing is known about the user.

Backed by local SQLite (auto-created from data/*.json on first run) - no
external database dependency, no second thing that can fail over the
network during a live demo.

Orchestrated with Gemini's automatic function calling: the model decides
when to call filter_catalogue / get_user_history, using them as real tools
rather than a fixed "always filter, then always ask the LLM" pipeline.

CLI only - run with: python agent.py
"""

import json
import os
import sqlite3
import sys
from google import genai
from google.genai import types, errors

DB_PATH = "agent.db"

SYSTEM_PROMPT = """You are a product recommendation agent with two tools:
filter_catalogue and get_user_history.

If you have a user_id, call get_user_history first, so you don't repeat
picks already made for them.

Then call filter_catalogue with whatever you know about what the user
wants - pass empty lists and a wide price range if you know nothing about
them yet.

filter_catalogue's response includes "is_cold_start". If true, say plainly
that these are popular picks since nothing is known about this user yet -
do not invent a personalized-sounding reason.

Pick and rank the best 3-5 products it returns. For each, give ONE sentence
reason tied to a SPECIFIC preference, tag, or behavior - never generic.
Format your answer as a numbered list, one line per product."""


# ---------- Database ----------

def get_db():
    """Connects to SQLite, creating and seeding tables from data/*.json on first run."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
    ).fetchone()
    if not exists:
        conn.execute("CREATE TABLE products (id TEXT PRIMARY KEY, name TEXT, category TEXT, price REAL, tags TEXT, rating REAL)")
        conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, name TEXT, preferences TEXT, behavior TEXT)")
        conn.execute("CREATE TABLE log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, response TEXT)")
        for p in json.load(open("data/products.json")):
            conn.execute(
                "INSERT INTO products VALUES (?,?,?,?,?,?)",
                (p["id"], p["name"], p["category"], p["price"], json.dumps(p["tags"]), p["rating"]),
            )
        for u in json.load(open("data/users.json")):
            conn.execute(
                "INSERT INTO users VALUES (?,?,?,?)",
                (u["user_id"], u["name"], json.dumps(u["preferences"]), json.dumps(u.get("behavior", {}))),
            )
        conn.commit()
    return conn


def get_products(conn):
    rows = conn.execute("SELECT * FROM products").fetchall()
    return [
        {"id": r["id"], "name": r["name"], "category": r["category"],
         "price": r["price"], "tags": json.loads(r["tags"]), "rating": r["rating"]}
        for r in rows
    ]


def get_users(conn):
    rows = conn.execute("SELECT * FROM users").fetchall()
    return [
        {"user_id": r["user_id"], "name": r["name"],
         "preferences": json.loads(r["preferences"]), "behavior": json.loads(r["behavior"])}
        for r in rows
    ]


def log(conn, user_id, response_text):
    conn.execute("INSERT INTO log (user_id, response) VALUES (?,?)", (user_id, response_text))
    conn.commit()


# ---------- Content-based scoring (unchanged logic, still auditable) ----------

def score_product(product, prefs, liked_categories):
    score = 0
    if product["category"] in prefs.get("categories", []):
        score += 3
    score += len(set(product["tags"]) & set(prefs.get("tags", [])))
    lo, hi = prefs.get("price_range", [0, float("inf")])
    if lo <= product["price"] <= hi:
        score += 2
    if product["category"] in liked_categories:
        score += 2
    return score


# ---------- Agent orchestration ----------

def get_client():
    if not os.environ.get("GOOGLE_API_KEY"):
        sys.exit(
            "ERROR: GOOGLE_API_KEY is not set.\n"
            "Command Prompt : set GOOGLE_API_KEY=your-key-here\n"
            "PowerShell     : $env:GOOGLE_API_KEY = \"your-key-here\""
        )
    return genai.Client()


def build_recommender(client, conn, catalogue):
    """Returns a recommend(message) function. filter_catalogue/get_user_history
    close over catalogue/conn so those never appear in the schema Gemini sees -
    only the parameters the model actually fills in do."""

    def filter_catalogue(categories: list[str], tags: list[str], price_min: float, price_max: float) -> str:
        """Filter and score the product catalogue by category, tags, and price range."""
        is_cold = not categories and not tags
        if is_cold:
            ranked = sorted(catalogue, key=lambda p: -p["rating"])
        else:
            prefs = {"categories": categories, "tags": tags, "price_range": [price_min, price_max]}
            ranked = sorted(catalogue, key=lambda p: -score_product(p, prefs, set()))
        return json.dumps({"is_cold_start": is_cold, "products": ranked[:8]})

    def get_user_history(user_id: str) -> str:
        """Look up what was recently recommended to this user, to avoid repeating picks."""
        rows = conn.execute(
            "SELECT response FROM log WHERE user_id=? ORDER BY id DESC LIMIT 3", (user_id,)
        ).fetchall()
        return json.dumps([r["response"] for r in rows])

    def recommend(message):
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[filter_catalogue, get_user_history],
                ),
            )
            return resp.text
        except errors.APIError as e:
            if e.code == 429:
                return (
                    "[Skipped: hit today's free Gemini quota (20 requests/day/model). "
                    "Check usage at https://ai.dev/rate-limit, or wait and rerun later.]"
                )
            return f"[Skipped: Gemini API error {e.code} - {e.message}]"

    return recommend


# ---------- CLI ----------

def main():
    conn = get_db()
    catalogue = get_products(conn)
    recommend = build_recommender(get_client(), conn, catalogue)

    print("=== Product Recommendation Agent ===")
    print("1. Describe what you're looking for")
    print("2. Run all saved sample profiles (for testing)")
    choice = input("Choose 1 or 2: ").strip()

    if choice == "1":
        name = input("Your name: ").strip() or "Guest"
        request = input("What are you looking for? ").strip()
        print(f"\n{'=' * 60}\nUSER: {name}\n{'=' * 60}")
        result = recommend(f"User '{name}' (id: LIVE) says: {request}")
        print(result)
        log(conn, "LIVE", result)
    else:
        for user in get_users(conn):
            print(f"\n{'=' * 60}\nUSER: {user['name']} (id: {user['user_id']})\n{'=' * 60}")
            result = recommend(f"Recommend products for this user profile: {json.dumps(user)}")
            print(result)
            log(conn, user["user_id"], result)


if __name__ == "__main__":
    main()