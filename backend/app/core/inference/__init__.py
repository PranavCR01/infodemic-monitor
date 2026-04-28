from __future__ import annotations

from app.core.config import settings


def get_provider():
    name = settings.INFERENCE_PROVIDER
    if name == "anthropic":
        from app.core.inference.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY)
    # default: openai
    from app.core.inference.providers.openai_provider import OpenAIProvider
    return OpenAIProvider(api_key=settings.OPENAI_API_KEY)
