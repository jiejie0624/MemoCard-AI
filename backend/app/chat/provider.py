"""DeepSeek chat-completion adapter with safe, bounded HTTP handling."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ChatProviderError(RuntimeError):
    """A safe provider failure that does not expose credentials or response bodies."""


class DeepSeekChatProvider:
    def complete(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, str] | None = None,
    ) -> str:
        payload_data = {
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            "messages": messages,
            "stream": False,
            "max_tokens": 1200,
            "temperature": 0.2,
        }
        if response_format is not None:
            payload_data["response_format"] = response_format
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ChatProviderError("DeepSeek is not configured")

        payload = json.dumps(payload_data).encode("utf-8")
        request = Request(
            "https://api.deepseek.com/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                body = response.read(1_000_001)
        except HTTPError as error:
            raise ChatProviderError(f"DeepSeek returned HTTP {error.code}") from error
        except (TimeoutError, URLError, OSError) as error:
            raise ChatProviderError("DeepSeek could not be reached") from error

        if len(body) > 1_000_000:
            raise ChatProviderError("DeepSeek returned an oversized response")
        try:
            result = json.loads(body)
            answer = result["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ChatProviderError("DeepSeek returned an invalid response") from error
        if not isinstance(answer, str) or not answer.strip():
            raise ChatProviderError("DeepSeek returned an empty answer")
        return answer.strip()
