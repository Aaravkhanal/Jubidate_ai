import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from app.model_registry import (
    MODEL_MAP,
    _MODEL_RUNTIME_CACHE,
    _MODEL_ROUTE_FAILURE_CACHE,
    available_models,
    get_available_model,
    mark_model_unavailable,
    verify_model_runtime,
)


class ModelRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        _MODEL_ROUTE_FAILURE_CACHE.clear()
        _MODEL_RUNTIME_CACHE.clear()

    def test_model_map_knows_all_supported_models(self) -> None:
        self.assertEqual(len(MODEL_MAP), 21)
        self.assertEqual(MODEL_MAP["gpt-4o"].provider, "openai")
        self.assertEqual(MODEL_MAP["claude-sonnet-4-6"].provider, "anthropic")
        self.assertEqual(MODEL_MAP["llama-4-maverick"].provider, "groq")

    def test_one_provider_key_unlocks_all_models_for_that_provider(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            names = {model.name for model in available_models()}

        self.assertEqual(
            names,
            {"gpt-5.4-pro", "gpt-5.4-mini", "gpt-4o", "gpt-4o-mini"},
        )

    def test_multiple_provider_keys_unlock_combined_dropdown_models(self) -> None:
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key", "ANTHROPIC_API_KEY": "test-key"},
            clear=True,
        ):
            names = {model.name for model in available_models()}

        self.assertEqual(len(names), 8)
        self.assertIn("gpt-4o", names)
        self.assertIn("claude-opus-4-6", names)

    def test_locked_model_cannot_be_selected(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            self.assertIsNotNone(get_available_model("gpt-4o"))
            self.assertIsNone(get_available_model("claude-sonnet-4-6"))

    def test_blank_or_placeholder_key_does_not_unlock_provider(self) -> None:
        with patch.dict(
            os.environ,
            {"MOONSHOT_API_KEY": "   ", "MINIMAX_API_KEY": "your_minimax_key"},
            clear=True,
        ):
            names = {model.name for model in available_models()}

        self.assertNotIn("kimi-latest", names)
        self.assertNotIn("minimax-m2.7", names)

    def test_mark_model_unavailable_temporarily_hides_direct_provider_model(self) -> None:
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True):
            self.assertIn("llama-4-maverick", [model.name for model in available_models()])
            mark_model_unavailable("llama-4-maverick", "Provider rejected this model name.")
            self.assertNotIn("llama-4-maverick", [model.name for model in available_models()])

    def test_verify_model_runtime_marks_successful_direct_provider_model_available(self) -> None:
        response = {"choices": [{"message": {"content": "OK"}}]}
        completion = AsyncMock(return_value=response)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True), patch(
            "backend.app.model_registry.acompletion", completion
        ):
            availability = asyncio.run(verify_model_runtime(MODEL_MAP["gpt-4o"]))

        self.assertTrue(availability.available)
        self.assertIsNone(availability.reason)

    def test_verify_model_runtime_marks_rejected_model_unavailable(self) -> None:
        completion = AsyncMock(
            side_effect=RuntimeError("MoonshotException - Not found the model kimi-k2-turbo-preview | 404")
        )
        with patch.dict(os.environ, {"MOONSHOT_API_KEY": "test-key"}, clear=True), patch(
            "backend.app.model_registry.acompletion", completion
        ):
            availability = asyncio.run(verify_model_runtime(MODEL_MAP["kimi-k2-turbo-preview"]))
            available_names = [model.name for model in available_models()]

        self.assertFalse(availability.available)
        self.assertIn("rejected this model name or endpoint", availability.reason or "")
        self.assertNotIn("kimi-k2-turbo-preview", available_names)

    def test_verify_model_runtime_can_fall_back_to_raw_moonshot_model_name(self) -> None:
        completion = AsyncMock(
            side_effect=[
                RuntimeError("MoonshotException - Not found the model moonshot/kimi-latest | 404"),
                {"choices": [{"message": {"content": "OK"}}]},
            ]
        )
        with patch.dict(os.environ, {"MOONSHOT_API_KEY": "test-key"}, clear=True), patch(
            "backend.app.model_registry.acompletion", completion
        ):
            availability = asyncio.run(verify_model_runtime(MODEL_MAP["kimi-latest"]))

        self.assertTrue(availability.available)
        attempted_models = [call.kwargs["model"] for call in completion.await_args_list]
        self.assertEqual(attempted_models, ["moonshot/kimi-latest", "kimi-latest"])


if __name__ == "__main__":
    unittest.main()
