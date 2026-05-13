from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import os
import time

try:
    from litellm import acompletion
except Exception:  # pragma: no cover - import guard for environments without LiteLLM
    acompletion = None


PLACEHOLDER_VALUES = {
    "your_key_here",
    "your_openai_key",
    "your_anthropic_key",
    "your_google_key",
    "your_groq_key",
    "your_minimax_key",
    "your_moonshot_key",
    "changeme",
    "change_me",
    "none",
    "null",
    "false",
}
MODEL_ROUTE_FAILURE_TTL_SECONDS = 21_600
MODEL_RUNTIME_CACHE_TTL_SECONDS = 900
MODEL_RUNTIME_TEMP_FAILURE_TTL_SECONDS = 120
MODEL_RUNTIME_PROBE_TIMEOUT_SECONDS = 12

_MODEL_ROUTE_FAILURE_CACHE: dict[str, dict[str, object]] = {}
_MODEL_RUNTIME_CACHE: dict[tuple[str, str, str], dict[str, object]] = {}


def env_secret(env_name: str) -> str | None:
    value = os.getenv(env_name, "").strip()
    if not value:
        return None
    if value.lower() in PLACEHOLDER_VALUES:
        return None
    return value


def model_route_is_blocked(model_name: str) -> bool:
    model = MODEL_MAP.get(model_name)
    if model is None:
        return False
    route = model.route_without_blocklist
    cached = _MODEL_ROUTE_FAILURE_CACHE.get(model_name)
    if not cached:
        return False
    if route is None or cached.get("source") != route.source or cached.get("token") != route.api_key:
        _MODEL_ROUTE_FAILURE_CACHE.pop(model_name, None)
        return False
    if float(cached.get("expires_at", 0.0)) <= time.time():
        _MODEL_ROUTE_FAILURE_CACHE.pop(model_name, None)
        return False
    return True


def mark_model_unavailable(
    model_name: str,
    reason: str,
    *,
    ttl_seconds: int = MODEL_ROUTE_FAILURE_TTL_SECONDS,
) -> None:
    model = MODEL_MAP.get(model_name)
    if model is None:
        return
    route = model.route_without_blocklist
    if route is None:
        return
    _MODEL_ROUTE_FAILURE_CACHE[model_name] = {
        "token": route.api_key,
        "source": route.source,
        "reason": reason[:600],
        "expires_at": time.time() + ttl_seconds,
    }


def _runtime_cache_key(model: "SupportedModel", route: "ModelRoute") -> tuple[str, str, str]:
    return (model.name, route.source, route.api_key)


def _cached_runtime_availability(
    model: "SupportedModel", route: "ModelRoute"
) -> "ModelAvailability" | None:
    cached = _MODEL_RUNTIME_CACHE.get(_runtime_cache_key(model, route))
    if not cached:
        return None
    ttl = (
        MODEL_RUNTIME_CACHE_TTL_SECONDS
        if cached.get("available")
        else int(cached.get("ttl", MODEL_RUNTIME_TEMP_FAILURE_TTL_SECONDS))
    )
    checked_at = float(cached.get("checked_at", 0.0))
    if time.time() - checked_at > ttl:
        _MODEL_RUNTIME_CACHE.pop(_runtime_cache_key(model, route), None)
        return None
    return ModelAvailability(
        available=bool(cached.get("available")),
        reason=str(cached.get("reason")) if cached.get("reason") else None,
        checked_at=checked_at,
    )


def _store_runtime_availability(
    model: "SupportedModel",
    route: "ModelRoute",
    availability: "ModelAvailability",
    *,
    ttl_seconds: int,
) -> "ModelAvailability":
    _MODEL_RUNTIME_CACHE[_runtime_cache_key(model, route)] = {
        "available": availability.available,
        "reason": availability.reason,
        "checked_at": availability.checked_at or time.time(),
        "ttl": ttl_seconds,
    }
    return availability


def _probe_error_reason(model: "SupportedModel", error_text: str) -> tuple[str, int]:
    lower = error_text.lower()
    if "authentication" in lower or "invalid api key" in lower or "incorrect api key" in lower:
        return (
            f"The API key for {model.provider_label} was rejected during a live check.",
            MODEL_RUNTIME_CACHE_TTL_SECONDS,
        )
    if "unauthorized" in lower or "401" in lower:
        return (
            f"{model.provider_label} denied the request during a live check.",
            MODEL_RUNTIME_CACHE_TTL_SECONDS,
        )
    if "rate limit" in lower or "429" in lower:
        return (
            f"{model.provider_label} is rate limiting this model right now. Try again shortly.",
            MODEL_RUNTIME_TEMP_FAILURE_TTL_SECONDS,
        )
    if "quota" in lower or "exceeded your current quota" in lower or "insufficient_quota" in lower:
        return (
            f"{model.provider_label} Quota Exceeded. Please check your billing details.",
            MODEL_RUNTIME_CACHE_TTL_SECONDS,
        )
    if "overload" in lower or "overloaded" in lower or "529" in lower or "temporarily unavailable" in lower:
        return (
            f"{model.provider_label} is temporarily overloaded for this model right now.",
            MODEL_RUNTIME_TEMP_FAILURE_TTL_SECONDS,
        )
    if "timeout" in lower:
        return (
            f"{model.provider_label} did not answer the live model check in time.",
            MODEL_RUNTIME_TEMP_FAILURE_TTL_SECONDS,
        )
    if any(
        marker in lower
        for marker in (
            "unknown model",
            "model not found",
            "not found the model",
            "unsupported model",
            "not support",
            "invalid model",
            "permission denied",
            "404",
        )
    ):
        return (
            f"{model.provider_label} rejected this model name or endpoint.",
            MODEL_RUNTIME_CACHE_TTL_SECONDS,
        )
    return (
        f"{model.provider_label} could not verify this model right now.",
        MODEL_RUNTIME_TEMP_FAILURE_TTL_SECONDS,
    )


async def verify_model_runtime(
    model: "SupportedModel", *, force_refresh: bool = False
) -> "ModelAvailability":
    route = model.route
    if route is None:
        return ModelAvailability(
            available=False,
            reason=f"{model.api_key_env} is missing or this model is temporarily hidden.",
            checked_at=time.time(),
        )
    if model.provider == "mock":
        return ModelAvailability(available=True, checked_at=time.time())
    if not force_refresh:
        cached = _cached_runtime_availability(model, route)
        if cached is not None:
            return cached
    if acompletion is None:
        return _store_runtime_availability(
            model,
            route,
            ModelAvailability(
                available=False,
                reason="LiteLLM is unavailable, so live model verification could not run.",
                checked_at=time.time(),
            ),
            ttl_seconds=MODEL_RUNTIME_CACHE_TTL_SECONDS,
        )
    last_exc: Exception | None = None
    for candidate_model in (route.litellm_model, *route.fallback_models):
        try:
            await acompletion(
                model=candidate_model,
                messages=[{"role": "user", "content": "Reply with OK."}],
                api_key=route.api_key,
                stream=False,
                temperature=0.0,
                max_tokens=4,
                timeout=MODEL_RUNTIME_PROBE_TIMEOUT_SECONDS,
            )
            return _store_runtime_availability(
                model,
                route,
                ModelAvailability(available=True, checked_at=time.time()),
                ttl_seconds=MODEL_RUNTIME_CACHE_TTL_SECONDS,
            )
        except Exception as exc:
            last_exc = exc
    if last_exc is None:
        raise RuntimeError("Model probe loop exited without success or exception")
    reason, ttl_seconds = _probe_error_reason(model, str(last_exc))
    if any(
        marker in reason.lower()
        for marker in ("rejected", "denied", "unknown model", "authentication")
    ):
        mark_model_unavailable(model.name, reason, ttl_seconds=ttl_seconds)
    return _store_runtime_availability(
        model,
        route,
        ModelAvailability(available=False, reason=reason, checked_at=time.time()),
        ttl_seconds=ttl_seconds,
    )


async def verify_models_runtime(models: list["SupportedModel"]) -> dict[str, "ModelAvailability"]:
    results = await asyncio.gather(*(verify_model_runtime(model) for model in models))
    return {model.name: result for model, result in zip(models, results, strict=True)}


@dataclass(frozen=True)
class ModelRoute:
    litellm_model: str
    api_key: str
    source: str
    fallback_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelAvailability:
    available: bool
    reason: str | None = None
    checked_at: float = 0.0


@dataclass(frozen=True)
class SupportedModel:
    name: str
    provider: str
    provider_label: str
    api_key_env: str
    litellm_model: str

    @property
    def configured(self) -> bool:
        if self.provider == "mock":
            return os.getenv(self.api_key_env, "false").strip().lower() == "true"
        return self.route is not None

    @property
    def runtime_available(self) -> bool:
        return self.route is not None

    @property
    def api_key(self) -> str | None:
        route = self.route
        return route.api_key if route else None

    @property
    def route_without_blocklist(self) -> ModelRoute | None:
        if self.provider == "mock":
            if os.getenv(self.api_key_env, "false").strip().lower() == "true":
                return ModelRoute(self.litellm_model, "mock", "mock")
            return None
        direct_key = self.direct_api_key
        if direct_key:
            fallback_models: tuple[str, ...] = ()
            if self.provider == "moonshot":
                fallback_models = (self.name,)
            return ModelRoute(self.litellm_model, direct_key, "provider", fallback_models)
        return None

    @property
    def route(self) -> ModelRoute | None:
        if model_route_is_blocked(self.name):
            return None
        return self.route_without_blocklist

    @property
    def direct_api_key(self) -> str | None:
        return env_secret(self.api_key_env)

    def public_dict(self, *, configured: bool | None = None) -> dict:
        payload = asdict(self)
        payload["configured"] = self.runtime_available if configured is None else configured
        return payload


MODEL_MAP: dict[str, SupportedModel] = {
    "gpt-4o": SupportedModel("gpt-4o", "openai", "OpenAI", "OPENAI_API_KEY", "gpt-4o"),
    "gpt-4o-mini": SupportedModel(
        "gpt-4o-mini", "openai", "OpenAI", "OPENAI_API_KEY", "gpt-4o-mini"
    ),
    "claude-opus-4-6": SupportedModel(
        "claude-opus-4-6",
        "anthropic",
        "Anthropic",
        "ANTHROPIC_API_KEY",
        "anthropic/claude-opus-4-6",
    ),
    "claude-sonnet-4-6": SupportedModel(
        "claude-sonnet-4-6",
        "anthropic",
        "Anthropic",
        "ANTHROPIC_API_KEY",
        "anthropic/claude-sonnet-4-6",
    ),
    "claude-haiku-4-5": SupportedModel(
        "claude-haiku-4-5",
        "anthropic",
        "Anthropic",
        "ANTHROPIC_API_KEY",
        "anthropic/claude-haiku-4-5",
    ),
    "claude-3.5-sonnet": SupportedModel(
        "claude-3.5-sonnet",
        "anthropic",
        "Anthropic",
        "ANTHROPIC_API_KEY",
        "anthropic/claude-3.5-sonnet",
    ),
    "gemini-3.1-pro": SupportedModel(
        "gemini-3.1-pro",
        "google",
        "Google",
        "GOOGLE_API_KEY",
        "gemini/gemini-2.5-pro",
    ),
    "gemini-3-flash": SupportedModel(
        "gemini-3-flash",
        "google",
        "Google",
        "GOOGLE_API_KEY",
        "gemini/gemini-2.5-flash",
    ),
    "gemini-2.5-flash-lite": SupportedModel(
        "gemini-2.5-flash-lite",
        "google",
        "Google",
        "GOOGLE_API_KEY",
        "gemini/gemini-2.5-flash-lite",
    ),
    "llama-3.1-8b-instant": SupportedModel(
        "llama-3.1-8b-instant",
        "groq",
        "Llama via Groq",
        "GROQ_API_KEY",
        "groq/llama-3.1-8b-instant",
    ),
    "llama-3.3-70b-versatile": SupportedModel(
        "llama-3.3-70b-versatile",
        "groq",
        "Llama via Groq",
        "GROQ_API_KEY",
        "groq/llama-3.3-70b-versatile",
    ),
    "minimax-m2.7": SupportedModel(
        "minimax-m2.7",
        "minimax",
        "MiniMax",
        "MINIMAX_API_KEY",
        "fireworks_ai/accounts/fireworks/models/minimax-m2p7",
    ),
    "kimi-latest": SupportedModel(
        "kimi-latest",
        "moonshot",
        "Moonshot",
        "MOONSHOT_API_KEY",
        "moonshot/kimi-latest",
    ),
    "kimi-k2-thinking": SupportedModel(
        "kimi-k2-thinking",
        "moonshot",
        "Moonshot",
        "MOONSHOT_API_KEY",
        "moonshot/kimi-k2-thinking",
    ),
    "kimi-k2-turbo-preview": SupportedModel(
        "kimi-k2-turbo-preview",
        "moonshot",
        "Moonshot",
        "MOONSHOT_API_KEY",
        "moonshot/kimi-k2-turbo-preview",
    ),
    "kimi-k2.5-vision": SupportedModel(
        "kimi-k2.5-vision",
        "moonshot",
        "Moonshot",
        "MOONSHOT_API_KEY",
        "moonshot/kimi-k2.5-vision",
    ),
    "moonshot-v1-128k": SupportedModel(
        "moonshot-v1-128k",
        "moonshot",
        "Moonshot",
        "MOONSHOT_API_KEY",
        "moonshot/moonshot-v1-128k",
    ),
    "kimi-fw": SupportedModel(
        "kimi-fw",
        "fireworks",
        "Kimi via Fireworks",
        "FIREWORKS_API_KEY",
        "fireworks_ai/accounts/fireworks/models/kimi-k2p6",
    ),
    "llama-3.1-70b-fw": SupportedModel(
        "llama-3.1-70b-fw",
        "fireworks",
        "Llama via Fireworks",
        "FIREWORKS_API_KEY",
        "fireworks_ai/accounts/fireworks/models/llama-v3p1-70b-instruct",
    ),
    "openrouter-auto": SupportedModel(
        "openrouter-auto",
        "openrouter",
        "OpenRouter",
        "OPENROUTER_API_KEY",
        "openrouter/auto",
    ),
    "llama-3.3-70b-or": SupportedModel(
        "llama-3.3-70b-or",
        "openrouter",
        "OpenRouter",
        "OPENROUTER_API_KEY",
        "openrouter/meta-llama/llama-3.3-70b-instruct",
    ),
    "claude-3.5-sonnet-or": SupportedModel(
        "claude-3.5-sonnet-or",
        "openrouter",
        "OpenRouter",
        "OPENROUTER_API_KEY",
        "openrouter/anthropic/claude-3.5-sonnet",
    ),
}

SUPPORTED_MODELS: tuple[SupportedModel, ...] = tuple(MODEL_MAP.values())
MOCK_MODEL = SupportedModel(
    "mock-debate-model",
    "mock",
    "Mock",
    "MOCK_LLM_RESPONSES",
    "mock-debate-model",
)

PROVIDER_ORDER = ("google", "groq", "moonshot", "minimax", "fireworks", "openai", "openrouter", "anthropic")


def all_models() -> list[SupportedModel]:
    return list(SUPPORTED_MODELS)


def available_models() -> list[SupportedModel]:
    models = [model for model in SUPPORTED_MODELS if model.runtime_available]
    openai_preferred_order = {"gpt-4o-mini": 0, "gpt-4o": 1}
    return sorted(
        models,
        key=lambda model: (
            PROVIDER_ORDER.index(model.provider) if model.provider in PROVIDER_ORDER else 999,
            openai_preferred_order.get(model.name, 100),
            model.name,
        ),
    )


def get_model(model_name: str) -> SupportedModel | None:
    return MODEL_MAP.get(model_name)


def get_available_model(model_name: str) -> SupportedModel | None:
    model = get_model(model_name)
    if model and model.runtime_available:
        return model
    return None


def available_model_payloads(*, include_mock: bool = False) -> list[dict]:
    payloads = [model.public_dict() for model in available_models()]
    if include_mock:
        payloads.insert(0, MOCK_MODEL.public_dict(configured=True))
    return payloads


def provider_summaries(*, unlocked_only: bool = True) -> list[dict]:
    summaries = []
    for provider in PROVIDER_ORDER:
        provider_models = [model for model in SUPPORTED_MODELS if model.provider == provider]
        if not provider_models:
            continue
        unlocked_models = [model for model in provider_models if model.runtime_available]
        direct_configured = any(model.direct_api_key for model in provider_models)
        if unlocked_only and not unlocked_models and not direct_configured:
            continue
        visible_models = unlocked_models if unlocked_only else provider_models
        summaries.append(
            {
                "provider": provider,
                "provider_label": provider_models[0].provider_label,
                "api_key_env": provider_models[0].api_key_env,
                "configured": bool(unlocked_models),
                "unlocked_model_count": len(unlocked_models),
                "total_model_count": len(provider_models),
                "models": [model.public_dict() for model in visible_models],
            }
        )
    return summaries
