"""OpenRouter HTTP client — OpenAI-compatible, free-model fallback chain."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Free models ordered by quality/reliability preference.
# If the first is unavailable or returns an error, the client falls through.
OPENROUTER_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-3-27b-it:free",
    "google/gemma-2-9b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "qwen/qwen-2-7b-instruct:free",
]

_SITE_URL = "https://observadordedominios.com.br"
_APP_TITLE = "Observador de Dominios"

# Error substrings that indicate the account-level daily quota is exhausted.
# When detected, we stop the fallback chain immediately since all free models
# share the same quota — retrying other models just wastes the remaining budget.
_DAILY_QUOTA_MARKERS = [
    "free-models-per-day",
    "Add 10 credits to unlock",
]


class DailyQuotaExhaustedError(RuntimeError):
    """Raised when the OpenRouter account-level free daily quota is exhausted."""


class OpenRouterClient:
    """Thin wrapper around the OpenAI SDK pointed at OpenRouter.

    Tries each free model in sequence and returns the first successful response.
    Raises DailyQuotaExhaustedError when the daily free quota is exhausted.
    Raises RuntimeError if all models fail for other reasons.
    """

    def __init__(self, api_key: str, base_url: str, timeout: float = 20.0) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout

    def complete(self, messages: list[dict], *, json_mode: bool = False) -> str:
        """Send a chat completion request, trying each model in order.

        Args:
            messages: Standard OpenAI messages array.
            json_mode: If True, requests JSON object response format.

        Returns:
            The assistant message content string.

        Raises:
            DailyQuotaExhaustedError: If the account free daily quota is exhausted.
            RuntimeError: If all models fail for other reasons.
        """
        from openai import OpenAI

        client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
            default_headers={
                "HTTP-Referer": _SITE_URL,
                "X-Title": _APP_TITLE,
            },
        )

        kwargs: dict = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None
        for model in OPENROUTER_MODELS:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    **kwargs,
                )
                content = response.choices[0].message.content or ""
                if content.strip():
                    logger.debug("OpenRouter success via model=%s", model)
                    return content
                logger.warning("OpenRouter model=%s returned empty content, trying next", model)
            except Exception as exc:
                error_str = str(exc)
                if any(marker in error_str for marker in _DAILY_QUOTA_MARKERS):
                    raise DailyQuotaExhaustedError(
                        f"OpenRouter free daily quota exhausted. Add credits to continue. ({exc})"
                    ) from exc
                logger.warning("OpenRouter model=%s failed: %s", model, exc)
                last_error = exc

        raise RuntimeError(
            f"All OpenRouter models exhausted. Last error: {last_error}"
        )
