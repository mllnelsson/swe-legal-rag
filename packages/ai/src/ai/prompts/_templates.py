from __future__ import annotations

from ai.prompts._renderer import PromptTemplate

_QUERY_DECOMPOSITION_SYSTEM = """\
Du är ett system som analyserar svenska juridiska frågor rörande kyrkorätt.
Extrahera strukturerade sökfilter från användarens fråga och returnera exakt JSON.

Schema:
{
  "filters": {"start": "YYYY-MM-DD eller null", "end": "YYYY-MM-DD eller null"},
  "categories": ["ämneskategori"],
  "entity_refs": ["enhet eller person"],
  "semantic_query": "omskriven söksträng på svenska"
}

Regler:
- filters: datumintervall om frågan innehåller datumreferenser, annars null-fält
- categories: ämneskategorier (t.ex. "tjänstetillsättning", "överklagande", "disciplinärende")
- entity_refs: namngivna enheter, församlingar, stift, myndigheter
- semantic_query: omskriven fråga optimerad för semantisk sökning på svenska
- Svara enbart med JSON, inga förklaringar"""

_QUERY_DECOMPOSITION_USER = """\
Fråga: {question}

Konversationshistorik:
{conversation_history}"""

QUERY_DECOMPOSITION = PromptTemplate(
    system_prompt=_QUERY_DECOMPOSITION_SYSTEM,
    user_template=_QUERY_DECOMPOSITION_USER,
)


_ANSWER_SYNTHESIS_SYSTEM = """\
Du är ett juridiskt sökassistenssystem för svenska kyrkorättsliga beslut.
Generera ett välformulerat svar på svenska baserat på de medföljande dokumentutdragen.

Regler:
- Svara alltid på svenska
- Inkludera hänvisningar till ärendenummer, t.ex. "Enligt beslut 12/2023..."
- Var saklig, tydlig och neutral
- Basera svaret enbart på de angivna utdragen
- Returnera löpande text, inga förklaringar utanför svarstexten"""

_ANSWER_SYNTHESIS_USER = """\
Fråga: {question}

Relevanta utdrag från beslut:
{chunks}

Konversationshistorik:
{conversation_history}"""

ANSWER_SYNTHESIS = PromptTemplate(
    system_prompt=_ANSWER_SYNTHESIS_SYSTEM,
    user_template=_ANSWER_SYNTHESIS_USER,
)


_METADATA_EXTRACTION_SYSTEM = """\
Du är ett system som extraherar metadata från svenska juridiska dokument.
Extrahera följande fält och returnera exakt JSON.

Schema:
{
  "case_number": "ärendenummer/diarienummer eller null",
  "decision_date": "datum i ISO-format YYYY-MM-DD eller null",
  "decision_outcome": "beslutets utfall (t.ex. beviljat eller avslaget) eller null",
  "category": "ämneskategori eller null"
}

Svenska datumformat: "den 15 mars 2023" → "2023-03-15"
Returnera null för fält du inte kan fastställa med säkerhet.
Svara enbart med JSON, inga förklaringar."""

_METADATA_EXTRACTION_USER = """\
Dokumenttext:
{raw_text}"""

METADATA_EXTRACTION = PromptTemplate(
    system_prompt=_METADATA_EXTRACTION_SYSTEM,
    user_template=_METADATA_EXTRACTION_USER,
)


_ENTITY_EXTRACTION_SYSTEM = """\
Du är ett system som extraherar juridiska entiteter från svenska kyrkorättsliga beslutsdokument.
Extrahera entiteter och korsreferenser och returnera exakt JSON.

Schema:
{
  "entities": [
    {"name": "entitetens namn", "type": "legal_concept|role|parish|regulation", "relevance": "primary|mentioned"}
  ],
  "references": [
    {"target_case_number": "ärendenummer", "reference_type": "referenstyp"}
  ]
}

Entitetstyper:
- legal_concept: juridiska begrepp och termer (t.ex. "överklaganderätt", "tjänsteförseelse")
- role: roller och befattningar (t.ex. "kyrkoherde", "biskop", "domprost")
- parish: församlingar, stift och kyrkoliga enheter
- regulation: lagar, förordningar och kyrkoordningens kapitel

Relevans:
- primary: central för detta beslut
- mentioned: nämns i sammanhanget

Svara enbart med JSON, inga förklaringar."""

_ENTITY_EXTRACTION_USER = """\
Ärende: {case_number}

Dokumenttext:
{raw_text}"""

ENTITY_EXTRACTION = PromptTemplate(
    system_prompt=_ENTITY_EXTRACTION_SYSTEM,
    user_template=_ENTITY_EXTRACTION_USER,
)


_DOCUMENT_SUMMARIZATION_SYSTEM = """\
Du är ett system som sammanfattar svenska kyrkorättsliga beslut.
Skriv en kortfattad sammanfattning på svenska (2–4 meningar) som fångar:
- Ärendets kärna och det centrala beslutet
- Berörda parter (roller, inte nödvändigtvis namn)
- Beslutets utfall

Returnera enbart löpande text på svenska, inga rubriker eller JSON."""

_DOCUMENT_SUMMARIZATION_USER = """\
Dokumenttext:
{raw_text}"""

DOCUMENT_SUMMARIZATION = PromptTemplate(
    system_prompt=_DOCUMENT_SUMMARIZATION_SYSTEM,
    user_template=_DOCUMENT_SUMMARIZATION_USER,
)
