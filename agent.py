"""
Product Recommendation Agent
Takes a user's stated preferences (and past behavior, when available) and
produces a ranked list of product recommendations, each with a specific
reason - falling back gracefully to popular picks when there's no data on
the user at all.
"""

import json
import os
import sys
from google import genai
from google.genai import types

if not os.environ.get("GOOGLE_API_KEY"):
    sys.exit(
        "ERROR: GOOGLE_API_KEY is not set in this terminal session.\n"
        "Command Prompt : set GOOGLE_API_KEY=your-key-here\n"
        "PowerShell     : $env:GOOGLE_API_KEY = \"your-key-here\"\n"
        "Then run 'python agent.py' again in that SAME window.\n"
        "(Don't wrap the value in quotes in Command Prompt - quotes become part of the key.)"
    )

client = genai.Client()  # reads GOOGLE_API_KEY from the environment

SYSTEM_PROMPT = """You are a product recommendation assistant.
You receive a user profile and a shortlist of candidate products already
filtered for relevance by a separate algorithm.
Pick and rank the best 3-5. For each, give ONE sentence explaining why,
referencing a SPECIFIC preference, tag, or behavior from the user's
profile - never a generic reason.
If is_cold_start is true, say plainly these are popular picks since we
don't know this user yet.
Return ONLY valid JSON: [{"product_id": "...", "reason": "..."}]"""


# ---------- Content-based filtering ----------

def has_signal(d):
    """True if any value in the dict is non-empty."""
    return any(v for v in d.values())


def score_product(product, prefs, liked_categories):
    score = 0
    if product["category"] in prefs.get("categories", []):
        score += 3
    score += len(set(product["tags"]) & set(prefs.get("tags", [])))
    lo, hi = prefs.get("price_range", [0, float("inf")])
    if lo <= product["price"] <= hi:
        score += 2
    if product["category"] in liked_categories:
        score += 2  # behavior boost
    return score


def get_candidates(user, catalogue, top_n=8):
    prefs = user.get("preferences", {})
    behavior = user.get("behavior", {})
    is_cold_start = not has_signal(prefs) and not has_signal(behavior)

    if is_cold_start:
        ranked = sorted(catalogue, key=lambda p: -p["rating"])  # popularity fallback
    else:
        liked_ids = behavior.get("purchased", []) + list(behavior.get("ratings", {}))
        liked_categories = {p["category"] for p in catalogue if p["id"] in liked_ids}
        ranked = sorted(catalogue, key=lambda p: -score_product(p, prefs, liked_categories))

    return ranked[:top_n], is_cold_start


# ---------- LLM ranking + reasoning ----------

def recommend(user, candidates, is_cold_start):
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            f"User: {json.dumps(user)}\n"
            f"Candidates: {json.dumps(candidates)}\n"
            f"is_cold_start: {is_cold_start}"
        ),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=1024,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    try:
        return json.loads(resp.text)
    except (json.JSONDecodeError, TypeError):
        print("Model didn't return valid JSON, raw response below:")
        print(resp.text)
        return []


# ---------- Input ----------

def get_user_input_profile():
    print("\nTell us what you're looking for (press Enter to skip a question):")
    name = input("Your name: ").strip() or "Guest"
    cats = input("Categories (comma-separated, e.g. footwear,electronics): ").strip()
    tags = input("Tags/keywords (comma-separated, e.g. wireless,running): ").strip()
    price = input("Price range as low-high (e.g. $0-$200): ").strip()

    preferences = {}
    if cats:
        preferences["categories"] = [c.strip() for c in cats.split(",")]
    if tags:
        preferences["tags"] = [t.strip() for t in tags.split(",")]
    if price and "-" in price:
        try:
            lo, hi = price.split("-", 1)
            preferences["price_range"] = [float(lo), float(hi)]
        except ValueError:
            print("Couldn't parse that price range, skipping it.")

    return {
        "user_id": "LIVE",
        "name": name,
        "preferences": preferences,
        "behavior": {"viewed": [], "purchased": [], "ratings": {}},
    }


# ---------- Output ----------

def show(user, recs, catalogue, is_cold_start):
    prefs = user.get("preferences", {})
    print(f"\n{'=' * 60}")
    print(f"USER PROFILE: {user['name']}  (id: {user['user_id']})")
    print(f"Preferences on file: {prefs if prefs else 'none'}")
    if is_cold_start:
        print("Status: COLD START — no preference/behavior data, showing popular picks")
    print("=" * 60)
    if not recs:
        print("(no recommendations returned)")
        return
    print("RANKED RECOMMENDATIONS:")
    for rank, r in enumerate(recs, start=1):
        p = next((p for p in catalogue if p["id"] == r["product_id"]), None)
        if p:
            print(f"  #{rank}  {p['name']} (${p['price']})")
            print(f"       Reason: {r['reason']}")

# ---------- Main loop ----------

def main():
    catalogue = json.load(open("data/products.json"))
    users = json.load(open("data/users.json"))

    print("=== Product Recommendation Agent ===")
    print("1. Type in your own preferences")
    print("2. Run all saved sample profiles (for testing)")
    choice = input("Choose 1 or 2: ").strip()

    if choice == "1":
        user = get_user_input_profile()
        candidates, cold = get_candidates(user, catalogue)
        recs = recommend(user, candidates, cold)
        show(user, recs, catalogue, cold)
        
    else:
        for user in users:
            candidates, cold = get_candidates(user, catalogue)
            recs = recommend(user, candidates, cold)
            show(user, recs, catalogue, cold)


if __name__ == "__main__":
    main()