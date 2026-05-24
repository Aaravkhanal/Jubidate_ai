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
        self.assertEqual(len(MODEL_MAP), 9)
        self.assertEqual(MODEL_MAP["nemotron-70b"].provider, "nvidia")
        self.assertEqual(MODEL_MAP["llama-3.1-8b"].provider, "nvidia")
        self.assertEqual(MODEL_MAP["mixtral-8x7b"].provider, "nvidia")

    def test_one_provider_key_unlocks_all_models_for_that_provider(self) -> None:
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"}, clear=True):
            names = {model.name for model in available_models()}

        self.assertEqual(
            names,
            {"nemotron-70b", "llama-3.1-70b", "llama-3.1-8b",
             "llama-3.2-90b-vision", "mixtral-8x7b", "mistral-7b",
             "mistral-nemotron", "seed-oss-36b-instruct", "mistral-large-3-675b-instruct-2512"},
        )

    def test_multiple_provider_keys_unlock_combined_dropdown_models(self) -> None:
        # With single NVIDIA provider, all models unlock with one key
        with patch.dict(
            os.environ,
            {"NVIDIA_API_KEY": "test-key"},
            clear=True,
        ):
            names = {model.name for model in available_models()}

        self.assertEqual(len(names), 9)
        self.assertIn("nemotron-70b", names)
        self.assertIn("llama-3.1-8b", names)

    def test_locked_model_cannot_be_selected(self) -> None:
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"}, clear=True):
            self.assertIsNotNone(get_available_model("nemotron-70b"))
        # Without the key, nothing is available
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(get_available_model("nemotron-70b"))

    def test_blank_or_placeholder_key_does_not_unlock_provider(self) -> None:
        with patch.dict(
            os.environ,
            {"NVIDIA_API_KEY": "   "},
            clear=True,
        ):
            names = {model.name for model in available_models()}

        self.assertEqual(len(names), 0)

    def test_mark_model_unavailable_temporarily_hides_direct_provider_model(self) -> None:
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"}, clear=True):
            self.assertIn("mixtral-8x7b", [model.name for model in available_models()])
            mark_model_unavailable("mixtral-8x7b", "Provider rejected this model name.")
            self.assertNotIn("mixtral-8x7b", [model.name for model in available_models()])

    def test_verify_model_runtime_marks_successful_direct_provider_model_available(self) -> None:
        response = {"choices": [{"message": {"content": "OK"}}]}
        completion = AsyncMock(return_value=response)
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"}, clear=True), patch(
            "app.model_registry.acompletion", completion
        ):
            availability = asyncio.run(verify_model_runtime(MODEL_MAP["nemotron-70b"]))

        self.assertTrue(availability.available)
        self.assertIsNone(availability.reason)

    def test_verify_model_runtime_marks_rejected_model_unavailable(self) -> None:
        completion = AsyncMock(
            side_effect=RuntimeError("Model not found: nvidia/llama-3.1-nemotron-70b-instruct | 404")
        )
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"}, clear=True), patch(
            "app.model_registry.acompletion", completion
        ):
            availability = asyncio.run(verify_model_runtime(MODEL_MAP["nemotron-70b"]))
            available_names = [model.name for model in available_models()]

        self.assertFalse(availability.available)
        self.assertIn("rejected", (availability.reason or "").lower())
        self.assertNotIn("nemotron-70b", available_names)

    def test_verify_model_runtime_passes_api_base_for_nvidia(self) -> None:
        response = {"choices": [{"message": {"content": "OK"}}]}
        completion = AsyncMock(return_value=response)
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"}, clear=True), patch(
            "app.model_registry.acompletion", completion
        ):
            asyncio.run(verify_model_runtime(MODEL_MAP["llama-3.1-8b"]))

        self.assertTrue(completion.await_count > 0)
        call_kwargs = completion.call_args.kwargs
        self.assertEqual(call_kwargs["api_base"], "https://integrate.api.nvidia.com/v1")


if __name__ == "__main__":
    unittest.main()
