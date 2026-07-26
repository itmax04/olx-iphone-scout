"""OpenAI Responses API adapter. Tests always inject a fake client."""

import logging
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


class AiProviderError(Exception):
    def __init__(self, message: str, *, code: str = "AI_UNAVAILABLE") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AiRawResponse:
    text: str
    model_id: str
    input_tokens: int
    output_tokens: int


class OpenAiResponsesClient:
    """Thin wrapper over the official SDK's Responses API."""

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise AiProviderError("OPENAI_API_KEY не задан.", code="CONFIGURATION_ERROR")
        from openai import OpenAI

        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=settings.OPENAI_MAX_RETRIES,
        )

    def generate(self, *, model: str, system: str, user: str, schema: dict) -> AiRawResponse:
        from openai import APIError, APITimeoutError, RateLimitError

        request: dict = {
            "model": model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "iphone_listing_facts",
                    "schema": schema,
                    "strict": False,
                }
            },
        }
        effort = settings.OPENAI_REASONING_EFFORT
        try:
            try:
                response = self._client.responses.create(**request, reasoning={"effort": effort})
            except TypeError:
                response = self._client.responses.create(**request)
            except APIError as exc:
                if getattr(exc, "status_code", None) == 400 and "reasoning" in str(exc):
                    response = self._client.responses.create(**request)
                else:
                    raise
        except RateLimitError as exc:
            raise AiProviderError(f"OpenAI 429: {type(exc).__name__}")
        except APITimeoutError:
            raise AiProviderError("OpenAI timeout.")
        except APIError as exc:
            raise AiProviderError(f"OpenAI error: {type(exc).__name__}")
        except Exception as exc:  # network etc.
            raise AiProviderError(f"OpenAI недоступен: {type(exc).__name__}")

        text = getattr(response, "output_text", "") or ""
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        model_id = str(getattr(response, "model", model))
        return AiRawResponse(
            text=text, model_id=model_id, input_tokens=input_tokens, output_tokens=output_tokens
        )


def get_ai_client() -> OpenAiResponsesClient:
    return OpenAiResponsesClient()
