"""Pydantic schema for structured LLM output, plus strict parsing.

The LLM must return exactly this JSON shape:

{
  "answer": "...",                       # non-empty string
  "citations": [{"page": 30, "quote": "..."}],  # pages it claims support the answer
  "confidence": 0.8,                     # 0.0 - 1.0
  "insufficient_context": false          # true if the context didn't contain the answer
}

parse_llm_output() is the single validation gate: anything the model emits
that does not match the schema raises SchemaValidationError. Tests in
tests/test_schemas.py assert that every known failure mode is rejected.
"""

import json
import re

from pydantic import BaseModel, ConfigDict, Field


class SchemaValidationError(ValueError):
    """Raised when LLM output cannot be parsed into a valid RAGAnswer."""

    def __init__(self, message: str, raw_output: str = ""):
        super().__init__(message)
        self.raw_output = raw_output


class Citation(BaseModel):
    # strict: reject type coercion ("30" -> 30, "no" -> False) — an LLM that
    # emits the wrong JSON type is breaking the contract, not approximating it
    model_config = ConfigDict(extra="forbid", strict=True)

    page: int = Field(ge=0, description="0-indexed PDF page the quote comes from")
    quote: str = Field(min_length=1, description="verbatim text copied from the context")


class RAGAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    answer: str = Field(min_length=1)
    citations: list[Citation]
    confidence: float = Field(ge=0.0, le=1.0)
    insufficient_context: bool = False


_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def strip_markdown_fence(text: str) -> str:
    """Remove a single wrapping ```json ... ``` fence if present.

    Fenced JSON is such a common LLM habit that we tolerate it as transport
    noise rather than a schema violation. Everything else must be pure JSON.
    """
    match = _FENCE_RE.match(text.strip())
    return match.group(1) if match else text


def parse_llm_output(raw: str) -> RAGAnswer:
    """Parse raw LLM text into a validated RAGAnswer or raise SchemaValidationError."""
    if not isinstance(raw, str) or not raw.strip():
        raise SchemaValidationError("LLM returned empty output", raw_output=str(raw))

    text = strip_markdown_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"Output is not valid JSON: {exc}", raw_output=raw) from exc

    if not isinstance(data, dict):
        raise SchemaValidationError(
            f"Expected a JSON object, got {type(data).__name__}", raw_output=raw
        )

    try:
        return RAGAnswer.model_validate(data)
    except Exception as exc:  # pydantic.ValidationError
        raise SchemaValidationError(f"JSON does not match schema: {exc}", raw_output=raw) from exc
