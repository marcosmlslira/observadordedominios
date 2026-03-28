"""OpenRouter HTTP client — OpenAI-compatible, free-model fallback chain."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Free models ordered by quality/reliability preference.
# If the first is unavailable or returns an error, the client falls through.
OPENROUTER_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-3-27b-it:free",
    "arcee-ai/trinity-mini:free",
    "meta-llama/llama-3.2-3b-instruct:free",
]

_SITE_URL = "https://observadordedominios.com.br"
_APP_TITLE = "Observador de Dominios"


class OpenRouterClient:
    """Thin wrapper around the OpenAI SDK pointed at OpenRouter.

    Tries each free model in sequence and returns the first successful response.
    Raises RuntimeError if all models fail.
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
            RuntimeError: If all models fail.
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
                logger.warning("OpenRouter model=%s failed: %s", model, exc)
                last_error = exc

        raise RuntimeError(
            f"All OpenRouter models exhausted. Last error: {last_error}"
        )
