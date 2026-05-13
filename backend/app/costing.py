from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import logging
import math
import os
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


SUPPORTED_CURRENCIES = ("USD", "CNY", "HKD", "EUR", "JPY", "GBP", "AUD", "CAD", "SGD")

# Fallback exchange rates relative to 1 USD. Kept local to avoid adding a fragile
# runtime currency dependency to the setup path.
EXCHANGE_RATES_PER_USD = {
    "USD": 1.0,
    "CNY": 7.25,
    "HKD": 7.8,
    "EUR": 0.92,
    "JPY": 155.0,
    "GBP": 0.79,
    "AUD": 1.52,
    "CAD": 1.36,
    "SGD": 1.35,
}

# Local fallback prices are USD per 1M input/output tokens for normal pay-as-you-go text use.
# These stay in the repo as a safety net when live pricing cannot be verified.
LOCAL_FALLBACK_MODEL_PRICES_USD_PER_1M = {
    "gpt-5.4-pro": (30.0, 180.0),
    "gpt-5.4-mini": (0.75, 4.5),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-3.5-sonnet": (3.0, 15.0),
    "gemini-3.1-pro": (2.0, 12.0),
    "gemini-3-flash": (0.5, 3.0),
    "gemini-2.5-flash-lite": (0.1, 0.4),
    "llama-4-maverick": (0.2, 0.6),
    "llama-4-scout": (0.11, 0.34),
    "llama-3.3-70b": (0.59, 0.79),
    "minimax-m2.7": (0.3, 1.2),
    "minimax-m2.5-lightning": (0.6, 2.4),
    "kimi-latest": (0.6, 2.0),
    "kimi-k2-thinking": (0.6, 2.0),
    "kimi-k2-turbo-preview": (0.6, 2.0),
    "kimi-k2.5-vision": (0.6, 2.0),
    "moonshot-v1-128k": (0.6, 2.0),
    "mock-debate-model": (0.0, 0.0),
}
OPENROUTER_MODELS_API_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_PRICING_CACHE_TTL_SECONDS = 3600
OPENROUTER_PRICING_TIMEOUT_SECONDS = 6
OPENROUTER_PRICING_ENV = "OPENROUTER_API_KEY"
OPENROUTER_MODEL_ALIASES: dict[str, tuple[str, ...]] = {
    "gpt-5.4-pro": ("openai/gpt-5.4", "gpt-5.4"),
    "gpt-5.4-mini": ("openai/gpt-5.4-mini", "gpt-5.4-mini"),
    "gpt-4o": ("openai/gpt-4o", "gpt-4o"),
    "gpt-4o-mini": ("openai/gpt-4o-mini", "gpt-4o-mini"),
    "claude-opus-4-6": ("anthropic/claude-opus-4.6", "claude-opus-4.6"),
    "claude-sonnet-4-6": ("anthropic/claude-sonnet-4.6", "claude-sonnet-4.6"),
    "claude-haiku-4-5": ("anthropic/claude-haiku-4.5", "claude-haiku-4.5"),
    "claude-3.5-sonnet": ("anthropic/claude-3.5-sonnet", "claude-3.5-sonnet"),
    "gemini-3.1-pro": ("google/gemini-3.1-pro", "gemini-3.1-pro"),
    "gemini-3-flash": ("google/gemini-3-flash", "gemini-3-flash"),
    "gemini-2.5-flash-lite": ("google/gemini-2.5-flash-lite", "gemini-2.5-flash-lite"),
    "llama-4-maverick": ("meta-llama/llama-4-maverick", "llama-4-maverick"),
    "llama-4-scout": ("meta-llama/llama-4-scout", "llama-4-scout"),
    "llama-3.3-70b": ("meta-llama/llama-3.3-70b-instruct", "llama-3.3-70b"),
    "minimax-m2.7": ("minimax/minimax-m2.7", "minimax-m2.7"),
    "minimax-m2.5-lightning": ("minimax/minimax-m2.5-lightning", "minimax-m2.5-lightning"),
    "kimi-latest": ("moonshotai/kimi-latest", "kimi-latest"),
    "kimi-k2-thinking": ("moonshotai/kimi-k2-thinking", "kimi-k2-thinking"),
    "kimi-k2-turbo-preview": ("moonshotai/kimi-k2-turbo-preview", "kimi-k2-turbo-preview"),
    "kimi-k2.5-vision": ("moonshotai/kimi-k2.5-vision", "kimi-k2.5-vision"),
    "moonshot-v1-128k": ("moonshotai/moonshot-v1-128k", "moonshot-v1-128k"),
}
_OPENROUTER_PRICING_CACHE: dict[str, Any] = {
    "fetched_at": 0.0,
    "entries": (),
    "error": None,
}


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_1m: float
    output_usd_per_1m: float
    source: str
    live: bool
    available: bool = True


@dataclass
class CostEntry:
    model: str
    input_tokens: int
    output_tokens: int
    input_usd_per_1m: float
    output_usd_per_1m: float
    cost_usd: float | None
    operation: str
    pricing_source: str
    pricing_live: bool
    pricing_available: bool


def _normalize_model_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _parse_price_string(value: object) -> float | None:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed * 1_000_000


def _openrouter_request_headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "AI-Debate-Council/1.0"}
    token = os.getenv(OPENROUTER_PRICING_ENV, "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_openrouter_pricing_entries() -> tuple[dict[str, Any], ...]:
    request = Request(
        OPENROUTER_MODELS_API_URL,
        headers=_openrouter_request_headers(),
        method="GET",
    )
    with urlopen(request, timeout=OPENROUTER_PRICING_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return ()
    return tuple(item for item in data if isinstance(item, dict))


def _openrouter_pricing_entries() -> tuple[dict[str, Any], ...]:
    now = time.time()
    if now - float(_OPENROUTER_PRICING_CACHE["fetched_at"]) < OPENROUTER_PRICING_CACHE_TTL_SECONDS:
        return _OPENROUTER_PRICING_CACHE["entries"]
    try:
        entries = _fetch_openrouter_pricing_entries()
        error = None
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        entries = ()
        error = str(exc)
        logger.info("OpenRouter pricing lookup unavailable, using local fallback prices: %s", exc)
    _OPENROUTER_PRICING_CACHE.update({"fetched_at": now, "entries": entries, "error": error})
    return entries


def _openrouter_aliases_for_model(model_name: str) -> set[str]:
    aliases = {_normalize_model_key(model_name)}
    aliases.update(_normalize_model_key(alias) for alias in OPENROUTER_MODEL_ALIASES.get(model_name, ()))
    if model_name in LOCAL_FALLBACK_MODEL_PRICES_USD_PER_1M:
        aliases.add(_normalize_model_key(model_name.replace("-4-6", "-4.6").replace("-4-5", "-4.5")))
    return {alias for alias in aliases if alias}


def _entry_aliases(entry: dict[str, Any]) -> set[str]:
    aliases = set()
    for key in ("id", "canonical_slug", "name"):
        value = str(entry.get(key) or "").strip()
        if not value:
            continue
        aliases.add(_normalize_model_key(value))
        if "/" in value:
            aliases.add(_normalize_model_key(value.split("/")[-1]))
    return {alias for alias in aliases if alias}


def _is_free_variant(entry: dict[str, Any]) -> bool:
    for key in ("id", "canonical_slug", "name"):
        value = str(entry.get(key) or "").lower()
        if ":free" in value or value.endswith(" free") or "(free)" in value:
            return True
    return False


def _openrouter_model_pricing(model_name: str) -> ModelPricing | None:
    target_aliases = _openrouter_aliases_for_model(model_name)
    if not target_aliases:
        return None
    for entry in _openrouter_pricing_entries():
        if _is_free_variant(entry):
            continue
        if not (_entry_aliases(entry) & target_aliases):
            continue
        pricing = entry.get("pricing") or {}
        if not isinstance(pricing, dict):
            continue
        prompt_price = _parse_price_string(pricing.get("prompt"))
        completion_price = _parse_price_string(pricing.get("completion"))
        if prompt_price is None or completion_price is None:
            continue
        if model_name != "mock-debate-model" and prompt_price == 0.0 and completion_price == 0.0:
            continue
        source_id = str(entry.get("canonical_slug") or entry.get("id") or "OpenRouter model catalog")
        return ModelPricing(
            input_usd_per_1m=prompt_price,
            output_usd_per_1m=completion_price,
            source=f"OpenRouter live pricing for {source_id}",
            live=True,
        )
    return None


def resolve_model_pricing(model_name: str) -> ModelPricing:
    live_pricing = _openrouter_model_pricing(model_name)
    if live_pricing is not None:
        return live_pricing
    fallback = LOCAL_FALLBACK_MODEL_PRICES_USD_PER_1M.get(model_name)
    if fallback is not None:
        return ModelPricing(
            input_usd_per_1m=fallback[0],
            output_usd_per_1m=fallback[1],
            source="Local fallback model price table",
            live=False,
        )
    return ModelPricing(
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        source="Pricing unavailable for this model",
        live=False,
        available=False,
    )


class CostTracker:
    def __init__(self) -> None:
        self.entries: list[CostEntry] = []
        self._warned_unknown_models: set[str] = set()

    def record_call(
        self,
        *,
        model_name: str,
        input_text: str,
        output_text: str,
        operation: str,
    ) -> None:
        input_tokens = estimate_tokens(input_text)
        output_tokens = estimate_tokens(output_text)
        pricing = resolve_model_pricing(model_name)
        if not pricing.available and model_name not in self._warned_unknown_models:
            logger.warning(
                "Unknown model pricing for %s. Cost tracking will mark this model as unpriced instead of silently showing a trustworthy total.",
                model_name,
            )
            self._warned_unknown_models.add(model_name)
        cost_usd = None
        if pricing.available:
            cost_usd = (
                input_tokens * pricing.input_usd_per_1m
                + output_tokens * pricing.output_usd_per_1m
            ) / 1_000_000
        self.entries.append(
            CostEntry(
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_usd_per_1m=pricing.input_usd_per_1m,
                output_usd_per_1m=pricing.output_usd_per_1m,
                cost_usd=cost_usd,
                operation=operation,
                pricing_source=pricing.source,
                pricing_live=pricing.live,
                pricing_available=pricing.available,
            )
        )

    def summary(self, currency: str) -> dict[str, Any]:
        return self._summary_for_entries(self.entries, currency)

    def summary_since(self, start_index: int, currency: str) -> dict[str, Any]:
        return self._summary_for_entries(self.entries[max(0, start_index) :], currency)

    def _summary_for_entries(self, entries: list[CostEntry], currency: str) -> dict[str, Any]:
        normalized_currency = normalize_currency(currency)
        rate = EXCHANGE_RATES_PER_USD[normalized_currency]
        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "model": "",
                "input_tokens": 0,
                "output_tokens": 0,
                "calls": 0,
                "cost_usd": 0.0,
                "input_usd_per_1m": 0.0,
                "output_usd_per_1m": 0.0,
                "pricing_source": "",
                "pricing_live": False,
                "pricing_available": True,
            }
        )
        warnings: list[str] = []
        pricing_source_labels: set[str] = set()
        pricing_complete = True
        for entry in entries:
            item = grouped[entry.model]
            item["model"] = entry.model
            item["input_tokens"] += entry.input_tokens
            item["output_tokens"] += entry.output_tokens
            item["calls"] += 1
            if entry.cost_usd is not None:
                item["cost_usd"] += entry.cost_usd
            item["input_usd_per_1m"] = entry.input_usd_per_1m
            item["output_usd_per_1m"] = entry.output_usd_per_1m
            item["pricing_source"] = entry.pricing_source
            item["pricing_live"] = entry.pricing_live
            item["pricing_available"] = entry.pricing_available
            pricing_source_labels.add(entry.pricing_source)
            if not entry.pricing_available:
                pricing_complete = False
                warning = (
                    f"{entry.model} pricing is unavailable, so totals exclude that model instead of faking a $0 price."
                )
                if warning not in warnings:
                    warnings.append(warning)

        model_items = []
        for item in grouped.values():
            converted = item["cost_usd"] * rate
            model_items.append(
                {
                    **item,
                    "cost": round(converted, 8),
                    "cost_usd": round(item["cost_usd"], 8),
                }
            )
        model_items.sort(key=lambda item: item["cost_usd"], reverse=True)
        total_usd = sum(entry.cost_usd or 0.0 for entry in entries)
        pricing_source_summary = (
            "; ".join(sorted(pricing_source_labels))
            if pricing_source_labels
            else "No model prices were recorded."
        )
        return {
            "currency": normalized_currency,
            "total": round(total_usd * rate, 8),
            "total_usd": round(total_usd, 8),
            "input_tokens": sum(entry.input_tokens for entry in entries),
            "output_tokens": sum(entry.output_tokens for entry in entries),
            "calls": len(entries),
            "models": model_items,
            "estimated": True,
            "pricing_complete": pricing_complete,
            "warnings": warnings,
            "rate_source": f"Model pricing: {pricing_source_summary}. Exchange rates: local fallback exchange rates.",
        }


def normalize_currency(currency: str) -> str:
    cleaned = str(currency or "USD").upper().strip()
    if cleaned == "SGP":
        cleaned = "SGD"
    return cleaned if cleaned in SUPPORTED_CURRENCIES else "USD"


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_tokens(message.get("content", "")) + 4 for message in messages)


def estimate_tokens(text: str) -> int:
    if not text or not text.strip():
        return 0
    cjk_chars = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
    without_cjk = re.sub(r"[\u3400-\u9fff\uf900-\ufaff]", " ", text)
    wordish = len(re.findall(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", without_cjk))
    return max(1, math.ceil(cjk_chars * 1.6 + wordish * 1.3))


def message_input_text(messages: list[dict[str, str]]) -> str:
    return "\n".join(f"{message.get('role', 'user')}: {message.get('content', '')}" for message in messages)
