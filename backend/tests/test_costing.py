import unittest
from unittest.mock import patch

from app.costing import CostTracker, estimate_tokens, normalize_currency


class CostingTests(unittest.TestCase):
    @patch("app.costing._openrouter_pricing_entries")
    def test_cost_tracker_prefers_live_openrouter_pricing_when_matched(self, mock_entries) -> None:
        mock_entries.return_value = (
            {
                "id": "nvidia/llama-3.1-nemotron-70b-instruct",
                "canonical_slug": "nvidia/llama-3.1-nemotron-70b-instruct",
                "name": "Nemotron 70B Instruct",
                "pricing": {"prompt": "0.00000047", "completion": "0.000002"},
            },
        )
        tracker = CostTracker()
        tracker.record_call(
            model_name="nemotron-70b",
            input_text="hello world",
            output_text="a short answer",
            operation="Council Assistant",
        )

        summary = tracker.summary("USD")

        self.assertEqual(summary["models"][0]["model"], "nemotron-70b")
        self.assertTrue(summary["models"][0]["pricing_live"])
        self.assertIn("OpenRouter live pricing", summary["rate_source"])
        self.assertGreater(summary["total"], 0)

    @patch("app.costing._openrouter_pricing_entries")
    def test_cost_tracker_groups_models_and_converts_currency(self, mock_entries) -> None:
        mock_entries.return_value = ()
        tracker = CostTracker()
        tracker.record_call(
            model_name="llama-3.1-8b",
            input_text="hello world",
            output_text="a short answer",
            operation="Council Assistant",
        )
        tracker.record_call(
            model_name="llama-3.1-8b",
            input_text="more context",
            output_text="another answer",
            operation="Council Assistant",
        )

        summary = tracker.summary("CNY")

        self.assertEqual(summary["currency"], "CNY")
        self.assertEqual(summary["calls"], 2)
        self.assertEqual(len(summary["models"]), 1)
        self.assertGreater(summary["total"], 0)
        self.assertFalse(summary["models"][0]["pricing_live"])

    def test_estimate_tokens_and_currency_normalization(self) -> None:
        self.assertGreaterEqual(estimate_tokens("Denying oneself"), 2)
        self.assertGreaterEqual(estimate_tokens("我们应该这样做，因为数据更清楚。"), 6)
        self.assertEqual(normalize_currency("sgp"), "SGD")
        self.assertEqual(normalize_currency("bad"), "USD")

    @patch("app.costing._openrouter_pricing_entries")
    def test_unknown_model_is_marked_unpriced_instead_of_silent_zero(self, mock_entries) -> None:
        mock_entries.return_value = ()
        tracker = CostTracker()
        tracker.record_call(
            model_name="unknown-model-for-test",
            input_text="hello world",
            output_text="a short answer",
            operation="Council Assistant",
        )

        summary = tracker.summary("USD")

        self.assertFalse(summary["pricing_complete"])
        self.assertGreaterEqual(len(summary["warnings"]), 1)
        self.assertIn("exclude that model", summary["warnings"][0])
        self.assertEqual(summary["models"][0]["cost"], 0.0)
        self.assertFalse(summary["models"][0]["pricing_available"])


if __name__ == "__main__":
    unittest.main()
