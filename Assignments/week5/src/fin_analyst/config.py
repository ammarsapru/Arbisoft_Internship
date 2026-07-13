from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    serpapi_key: str = Field(validation_alias=AliasChoices("SERPAPI_KEY", "SERP_API_KEY"))
    anthropic_api_key: str = Field(validation_alias=AliasChoices("ANTHROPIC_API_KEY"))

    model_fast: str = Field(default="claude-haiku-4-5-20251001", validation_alias=AliasChoices("MODEL_FAST"))
    model_strong: str = Field(default="claude-sonnet-5", validation_alias=AliasChoices("MODEL_STRONG"))

    serpapi_cache_ttl_seconds: int = Field(default=900, validation_alias=AliasChoices("SERPAPI_CACHE_TTL_SECONDS"))
    trace_log_dir: Path = Field(default=Path("./traces"), validation_alias=AliasChoices("TRACE_LOG_DIR"))
    report_output_dir: Path = Field(default=Path("./reports"), validation_alias=AliasChoices("REPORT_OUTPUT_DIR"))

    recursion_limit: int = 15


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.trace_log_dir.mkdir(parents=True, exist_ok=True)
        _settings.report_output_dir.mkdir(parents=True, exist_ok=True)
    return _settings
