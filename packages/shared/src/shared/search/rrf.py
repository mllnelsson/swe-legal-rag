import uuid

# Reciprocal-rank-fusion damping constant. The standard value from the original
# RRF paper; large enough that the top few ranks of any one ranking cannot
# dominate the fused order on their own.
DEFAULT_RRF_K = 60


def rrf_fuse_scored(
    rankings: list[list[uuid.UUID]], k: int = DEFAULT_RRF_K
) -> list[tuple[uuid.UUID, float]]:
    """Fuse any number of rankings into one, keeping the fused score.

    Each ranking contributes ``1/(k + rank)`` per id, so an id ranked well by
    several rankings outscores one ranked well by a single ranking. The number of
    rankings is deliberately unbounded: two search arms and N query variants fuse
    through exactly the same call.
    """
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def rrf_fuse(
    rankings: list[list[uuid.UUID]], k: int = DEFAULT_RRF_K
) -> list[uuid.UUID]:
    return [doc_id for doc_id, _ in rrf_fuse_scored(rankings, k)]
