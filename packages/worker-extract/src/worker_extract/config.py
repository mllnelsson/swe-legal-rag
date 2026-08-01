from enum import StrEnum, auto
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.enums import PipelineStep


class ExtractStrategyMode(StrEnum):
    """How entities and references are pulled out of a decision."""

    RULE_BASED = auto()
    LLM = auto()
    RULE_BASED_WITH_LLM_FALLBACK = auto()


class ExtractSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    extract_topic: PipelineStep = PipelineStep.EXTRACT
    extract_next_topic: PipelineStep = PipelineStep.CHUNK
    # Typed as the enum so an unrecognised EXTRACT_STRATEGY fails at startup
    # naming the bad value, rather than being silently swapped for the default.
    extract_strategy: ExtractStrategyMode = (
        ExtractStrategyMode.RULE_BASED_WITH_LLM_FALLBACK
    )


@lru_cache(maxsize=1)
def get_extract_settings() -> ExtractSettings:
    return ExtractSettings()
