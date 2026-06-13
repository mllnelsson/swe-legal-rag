from ai.prompts._renderer import PromptTemplate
from ai.prompts._templates import (
    ANSWER_SYNTHESIS,
    DOCUMENT_SUMMARIZATION,
    ENTITY_EXTRACTION,
    METADATA_EXTRACTION,
    QUERY_DECOMPOSITION,
)

__all__ = [
    "PromptTemplate",
    "QUERY_DECOMPOSITION",
    "ANSWER_SYNTHESIS",
    "METADATA_EXTRACTION",
    "ENTITY_EXTRACTION",
    "DOCUMENT_SUMMARIZATION",
]
