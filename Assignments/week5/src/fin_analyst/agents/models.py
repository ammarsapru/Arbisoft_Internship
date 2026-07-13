from langchain_anthropic import ChatAnthropic

from fin_analyst.config import get_settings
from fin_analyst.tracing.callbacks import TracingCallbackHandler

_tracing_handler = TracingCallbackHandler()


def get_tracing_handler() -> TracingCallbackHandler:
    return _tracing_handler


def get_fast_model(max_tokens: int = 1024) -> ChatAnthropic:
    """Cheap/fast tier - mechanical, schema-shaped work (see docs/07)."""
    settings = get_settings()
    return ChatAnthropic(
        model=settings.model_fast,
        api_key=settings.anthropic_api_key,
        max_tokens=max_tokens,
        callbacks=[_tracing_handler],
    )


def get_strong_model(max_tokens: int = 2048) -> ChatAnthropic:
    """Stronger tier - judgment calls: supervisor validation gates and news
    impact classification (see docs/07)."""
    settings = get_settings()
    return ChatAnthropic(
        model=settings.model_strong,
        api_key=settings.anthropic_api_key,
        max_tokens=max_tokens,
        callbacks=[_tracing_handler],
    )
