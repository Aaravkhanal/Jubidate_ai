from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import logging
import os
import time

try:
    from litellm import acompletion
except Exception:  # pragma: no cover - import guard for environments without LiteLLM
    acompletion = None


logger = logging.getLogger("jubidate.model_registry")

NVIDIA_API_BASE = "https://integrate.api.nvidia.com/v1"

PLACEHOLDER_VALUES = {
    "your_key_here",
    "your_nvidia_key",
    "your_nvidia_api_key_here",
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
MODEL_RUNTIME_PROBE_TIMEOUT_SECONDS = 8  # Reduced from 30s to prevent frontend timeouts

_MODEL_ROUTE_FAILURE_CACHE: dict[str, dict[str, object]] = {}
_MODEL_RUNTIME_CACHE: dict[tuple[str, str, str], dict[str, object]] = {}

# Background verification state
_BACKGROUND_VERIFICATION_RESULTS: dict[str, "ModelAvailability"] = {}
_BACKGROUND_VERIFICATION_RUNNING = False
_BACKGROUND_VERIFICATION_COMPLETED = False


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
            kwargs: dict = dict(
                model=candidate_model,
                messages=[{"role": "user", "content": "Reply with OK."}],
                api_key=route.api_key,
                stream=False,
                temperature=0.0,
                max_tokens=4,
                timeout=MODEL_RUNTIME_PROBE_TIMEOUT_SECONDS,
            )
            if route.api_base:
                kwargs["api_base"] = route.api_base
            await acompletion(**kwargs)
            logger.info("Model %s verified successfully via %s", model.name, candidate_model)
            return _store_runtime_availability(
                model,
                route,
                ModelAvailability(available=True, checked_at=time.time()),
                ttl_seconds=MODEL_RUNTIME_CACHE_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("Model %s probe failed for %s: %s", model.name, candidate_model, exc)
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


async def run_background_verification() -> None:
    """Run model verification in the background. Called during app startup."""
    global _BACKGROUND_VERIFICATION_RUNNING, _BACKGROUND_VERIFICATION_COMPLETED, _BACKGROUND_VERIFICATION_RESULTS
    if _BACKGROUND_VERIFICATION_RUNNING:
        return
    _BACKGROUND_VERIFICATION_RUNNING = True
    logger.info("Starting background model verification for %d models...", len(SUPPORTED_MODELS))
    configured = available_models()
    if not configured:
        logger.warning("No configured models found (API key missing?)")
        _BACKGROUND_VERIFICATION_RUNNING = False
        _BACKGROUND_VERIFICATION_COMPLETED = True
        return
    try:
        results = await verify_models_runtime(configured)
        _BACKGROUND_VERIFICATION_RESULTS = results
        verified_count = sum(1 for r in results.values() if r.available)
        failed = [name for name, r in results.items() if not r.available]
        logger.info(
            "Background verification complete: %d/%d verified. Failed: %s",
            verified_count, len(results), failed or "none"
        )
    except Exception as exc:
        logger.error("Background verification failed: %s", exc)
    finally:
        _BACKGROUND_VERIFICATION_RUNNING = False
        _BACKGROUND_VERIFICATION_COMPLETED = True


def get_background_verification_results() -> dict[str, "ModelAvailability"]:
    """Get cached background verification results."""
    return _BACKGROUND_VERIFICATION_RESULTS.copy()


def is_background_verification_completed() -> bool:
    """Check if background verification has completed."""
    return _BACKGROUND_VERIFICATION_COMPLETED


@dataclass(frozen=True)
class ModelRoute:
    litellm_model: str
    api_key: str
    source: str
    fallback_models: tuple[str, ...] = ()
    api_base: str | None = None


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
    fallback_models: tuple[str, ...] = ()

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
            api_base = NVIDIA_API_BASE if self.provider == "nvidia" else None
            return ModelRoute(
                self.litellm_model,
                direct_key,
                "provider",
                self.fallback_models,
                api_base,
            )
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


# ─────────────────────────────────────────────────────────────────────────────
# NVIDIA NIM Model Registry
# All models route through https://integrate.api.nvidia.com/v1 via LiteLLM's
# OpenAI-compatible provider (prefix: "openai/").
#
# Fallback order: llama-3.1-70b → mixtral-8x7b → llama-3.1-8b → mistral-7b
# ─────────────────────────────────────────────────────────────────────────────

MODEL_MAP: dict[str, SupportedModel] = {
    # ── Custom orchestration selections ──
    "mistral-nemotron": SupportedModel(
        "mistral-nemotron",
        "nvidia",
        "NVIDIA",
        "NVIDIA_API_KEY",
        "openai/nvidia/llama-3.1-nemotron-70b-instruct",
        fallback_models=("openai/meta/llama-3.1-70b-instruct",),
    ),
    "seed-oss-36b-instruct": SupportedModel(
        "seed-oss-36b-instruct",
        "nvidia",
        "NVIDIA",
        "NVIDIA_API_KEY",
        "openai/nvidia/llama-3.1-nemotron-70b-instruct",
        fallback_models=("openai/meta/llama-3.1-8b-instruct",),
    ),
    "mistral-large-3-675b-instruct-2512": SupportedModel(
        "mistral-large-3-675b-instruct-2512",
        "nvidia",
        "NVIDIA",
        "NVIDIA_API_KEY",
        "openai/nvidia/llama-3.1-nemotron-70b-instruct",
        fallback_models=("openai/meta/llama-3.1-70b-instruct",),
    ),

    # ── Flagship reasoning (Nemotron 70B) ──
    "nemotron-70b": SupportedModel(
        "nemotron-70b",
        "nvidia",
        "NVIDIA",
        "NVIDIA_API_KEY",
        "openai/nvidia/llama-3.1-nemotron-70b-instruct",
        fallback_models=("openai/meta/llama-3.1-70b-instruct",),
    ),

    # ── Chat / General Reasoning ──
    "llama-3.1-70b": SupportedModel(
        "llama-3.1-70b",
        "nvidia",
        "NVIDIA",
        "NVIDIA_API_KEY",
        "openai/meta/llama-3.1-70b-instruct",
        fallback_models=("openai/nvidia/llama-3.1-nemotron-70b-instruct",),
    ),
    "llama-3.1-8b": SupportedModel(
        "llama-3.1-8b",
        "nvidia",
        "NVIDIA",
        "NVIDIA_API_KEY",
        "openai/meta/llama-3.1-8b-instruct",
    ),
    "mixtral-8x7b": SupportedModel(
        "mixtral-8x7b",
        "nvidia",
        "NVIDIA",
        "NVIDIA_API_KEY",
        "openai/mistralai/mixtral-8x7b-instruct-v0.1",
    ),
    "mistral-7b": SupportedModel(
        "mistral-7b",
        "nvidia",
        "NVIDIA",
        "NVIDIA_API_KEY",
        "openai/mistralai/mistral-7b-instruct-v0.3",
    ),

    # ── Vision ──
    "llama-3.2-90b-vision": SupportedModel(
        "llama-3.2-90b-vision",
        "nvidia",
        "NVIDIA",
        "NVIDIA_API_KEY",
        "openai/meta/llama-3.2-90b-vision-instruct",
    ),
}

# Models that were renamed/removed — map old names to new defaults for migration
_MODEL_NAME_ALIASES: dict[str, str] = {
    "llama-3.3-70b": "llama-3.1-70b",
    "mistral-large-2": "mixtral-8x7b",
    "mixtral-8x22b": "mixtral-8x7b",
}

# Default fallback chain when a specific model is unavailable
DEFAULT_FALLBACK_ORDER = ("llama-3.1-70b", "mixtral-8x7b", "llama-3.1-8b", "mistral-7b")

SUPPORTED_MODELS: tuple[SupportedModel, ...] = tuple(MODEL_MAP.values())
MOCK_MODEL = SupportedModel(
    "mock-debate-model",
    "mock",
    "Mock",
    "MOCK_LLM_RESPONSES",
    "mock-debate-model",
)

PROVIDER_ORDER = ("nvidia",)


def all_models() -> list[SupportedModel]:
    return list(SUPPORTED_MODELS)


def available_models() -> list[SupportedModel]:
    models = [model for model in SUPPORTED_MODELS if model.runtime_available]
    return sorted(
        models,
        key=lambda model: (
            PROVIDER_ORDER.index(model.provider) if model.provider in PROVIDER_ORDER else 999,
            model.name,
        ),
    )


def get_model(model_name: str) -> SupportedModel | None:
    model = MODEL_MAP.get(model_name)
    if model is None:
        # Check aliases for renamed/removed models
        alias = _MODEL_NAME_ALIASES.get(model_name)
        if alias:
            model = MODEL_MAP.get(alias)
    if model is None and model_name.strip():
        name = model_name.strip()
        provider = "nvidia"
        provider_label = "NVIDIA"
        api_key_env = "NVIDIA_API_KEY"
        litellm_model = f"openai/nvidia/{name}" if not name.startswith("openai/") else name
        return SupportedModel(
            name=name,
            provider=provider,
            provider_label=provider_label,
            api_key_env=api_key_env,
            litellm_model=litellm_model
        )
    return model


def get_available_model(model_name: str) -> SupportedModel | None:
    model = get_model(model_name)
    if model and model.runtime_available:
        return model
    # Try fallback chain
    for fallback_name in DEFAULT_FALLBACK_ORDER:
        fallback = MODEL_MAP.get(fallback_name)
        if fallback and fallback.runtime_available:
            logger.info("Model %s unavailable, falling back to %s", model_name, fallback_name)
            return fallback
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


def provider_status() -> dict:
    """Return detailed provider status for debugging."""
    configured = available_models()
    bg_results = get_background_verification_results()

    providers = {}
    for provider in PROVIDER_ORDER:
        provider_models = [m for m in SUPPORTED_MODELS if m.provider == provider]
        if not provider_models:
            continue
        key_env = provider_models[0].api_key_env
        key_value = env_secret(key_env)
        masked_key = f"{key_value[:8]}...{key_value[-4:]}" if key_value and len(key_value) > 12 else ("set" if key_value else "missing")

        model_statuses = []
        for m in provider_models:
            bg = bg_results.get(m.name)
            model_statuses.append({
                "name": m.name,
                "litellm_model": m.litellm_model,
                "configured": m.runtime_available,
                "verified": bg.available if bg else None,
                "reason": bg.reason if bg else ("pending" if not is_background_verification_completed() else "not checked"),
            })

        providers[provider] = {
            "provider_label": provider_models[0].provider_label,
            "api_key_env": key_env,
            "api_key": masked_key,
            "total_models": len(provider_models),
            "configured_models": len([m for m in provider_models if m.runtime_available]),
            "verified_models": len([m for m in provider_models if bg_results.get(m.name) and bg_results[m.name].available]),
            "models": model_statuses,
        }

    return {
        "providers": providers,
        "background_verification_completed": is_background_verification_completed(),
        "total_configured": len(configured),
        "default_fallback_order": list(DEFAULT_FALLBACK_ORDER),
    }
