"""A structured-output LLM call is only as reliable as the model's
adherence to the schema. Even with `.with_structured_output()` constraining
generation, a field constraint (e.g. max_length) can still be violated by
the model's output and raise a pydantic ValidationError - live testing hit
exactly this (a supervisor `reason` string exceeded its max_length). This
wraps such calls with one retry (nudging the model toward compliance) and a
safe fallback, so a formatting slip in a self-critique field degrades
gracefully instead of crashing the whole pipeline - the guardrail
philosophy in docs/08-structured-outputs-guardrails.md applied to the
guardrail mechanism itself.
"""

from typing import Awaitable, Callable, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


async def safe_structured_call(call: Callable[[], Awaitable[T]], retry_call: Callable[[], Awaitable[T]], fallback: T) -> T:
    try:
        return await call()
    except ValidationError:
        try:
            return await retry_call()
        except ValidationError:
            return fallback
