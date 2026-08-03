from shared.dtos.search import DocumentFilter


def is_empty_filter(document_filter: DocumentFilter) -> bool:
    """Whether this filter constrains anything at all.

    Derived from the model rather than enumerated field by field, so a filter
    field added later cannot silently go unconsidered here.
    """
    return not document_filter.model_dump(exclude_defaults=True)
