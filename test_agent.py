"""
Tests for the Product Recommendation Agent.
DB tests use a throwaway in-memory SQLite database. The orchestration tests
mock the Gemini client entirely, so running this file never touches the
real API or your daily quota.

Run with:
    python -m unittest test_agent.py -v
"""

import os
os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")

import json
import sqlite3
import unittest
from unittest.mock import MagicMock
import agent
from google.genai import errors


def make_test_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE products (id TEXT PRIMARY KEY, name TEXT, category TEXT, price REAL, tags TEXT, rating REAL)")
    conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, name TEXT, preferences TEXT, behavior TEXT)")
    conn.execute("CREATE TABLE log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, response TEXT)")
    conn.execute(
        "INSERT INTO products VALUES ('P1','Shoe','footwear',50,?,4.0)",
        (json.dumps(["running"]),),
    )
    conn.commit()
    return conn


class TestDatabase(unittest.TestCase):
    def test_get_products_parses_tags_back_into_a_list(self):
        products = agent.get_products(make_test_db())
        self.assertEqual(products[0]["tags"], ["running"])

    def test_log_and_read_back(self):
        conn = make_test_db()
        agent.log(conn, "U1", "some recommendation text")
        row = conn.execute("SELECT response FROM log WHERE user_id='U1'").fetchone()
        self.assertEqual(row["response"], "some recommendation text")


class TestScoreProduct(unittest.TestCase):
    def test_category_and_price_match_add_up(self):
        product = {"category": "footwear", "price": 50, "tags": ["running"]}
        prefs = {"categories": ["footwear"], "price_range": [0, 100]}
        self.assertEqual(agent.score_product(product, prefs, set()), 5)

    def test_out_of_range_price_scores_lower(self):
        product = {"category": "footwear", "price": 500, "tags": []}
        prefs = {"categories": ["footwear"], "price_range": [0, 100]}
        self.assertEqual(agent.score_product(product, prefs, set()), 3)


class TestRecommend(unittest.TestCase):
    def test_recommend_returns_the_models_text(self):
        catalogue = [{"id": "P1", "name": "Shoe", "category": "footwear",
                      "price": 50, "tags": ["running"], "rating": 4.0}]
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(
            text="1. Shoe - matches your running interest."
        )
        recommend = agent.build_recommender(mock_client, make_test_db(), catalogue)
        result = recommend("Recommend running shoes")

        self.assertIn("Shoe", result)
        mock_client.models.generate_content.assert_called_once()

    def test_tools_passed_are_plain_functions_afc_will_detect(self):
        import inspect
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text="ok")
        recommend = agent.build_recommender(mock_client, make_test_db(), [])
        recommend("test")
        tools = mock_client.models.generate_content.call_args.kwargs["config"].tools
        self.assertTrue(all(inspect.isfunction(t) for t in tools))

    def test_rate_limit_is_handled_gracefully_not_raised(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = errors.ClientError(
            429, {"error": {"message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
        )
        recommend = agent.build_recommender(mock_client, make_test_db(), [])
        result = recommend("test")
        self.assertIn("Skipped", result)
        self.assertIn("quota", result.lower())

    def test_other_api_errors_are_also_handled_gracefully(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = errors.ServerError(
            500, {"error": {"message": "Internal error", "status": "INTERNAL"}}
        )
        recommend = agent.build_recommender(mock_client, make_test_db(), [])
        result = recommend("test")
        self.assertIn("Skipped", result)


if __name__ == "__main__":
    unittest.main()