from __future__ import annotations

import datetime

from pydantic import BaseModel

from llm_core import Message, Role, generate_structured

_FIELD_DESCRIPTIONS: dict[str, str] = {
    "case_number": "case/diary number (diarienummer/dnr)",
    "decision_date": "decision date in ISO format (YYYY-MM-DD)",
    "decision_outcome": "decision outcome phrase (e.g. whether the appeal was granted or rejected)",
    "category": "category or subject matter of the case",
}


class _LLMFields(BaseModel):
    case_number: str | None = None
    decision_date: str | None = None
    decision_outcome: str | None = None
    category: str | None = None


class MetadataLLMResult(BaseModel):
    case_number: str | None = None
    decision_date: datetime.date | None = None
    decision_outcome: str | None = None
    category: str | None = None


async def extract_metadata_llm(
    raw_text: str,
    missing_fields: list[str],
) -> MetadataLLMResult:
    fields_text = "\n".join(
        f"- {f}: {_FIELD_DESCRIPTIONS[f]}" for f in missing_fields if f in _FIELD_DESCRIPTIONS
    )
    prompt = (
        "Extract the following metadata from this Swedish legal document.\n"
        "Return null for fields you cannot find with confidence.\n\n"
        f"Fields to extract:\n{fields_text}\n\n"
        f"Document text:\n{raw_text[:6000]}"
    )

    raw = await generate_structured(
        [Message(role=Role.user, content=prompt)],
        _LLMFields,
    )

    decision_date: datetime.date | None = None
    if raw.decision_date:
        try:
            decision_date = datetime.date.fromisoformat(raw.decision_date)
        except ValueError:
            pass

    return MetadataLLMResult(
        case_number=raw.case_number,
        decision_date=decision_date,
        decision_outcome=raw.decision_outcome,
        category=raw.category,
    )
