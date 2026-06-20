import uuid


def rrf_fuse(rankings: list[list[uuid.UUID]], k: int = 60) -> list[uuid.UUID]:
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.keys(), key=lambda d: scores[d], reverse=True)
