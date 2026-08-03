import uuid

from shared.search.rrf import DEFAULT_RRF_K, rrf_fuse, rrf_fuse_scored


def _ids(n: int) -> list[uuid.UUID]:
    return [uuid.UUID(int=i) for i in range(n)]


class TestRrfFuse:
    def test_empty_inputs_return_empty(self):
        assert rrf_fuse([]) == []

    def test_single_empty_ranking_returns_empty(self):
        assert rrf_fuse([[]]) == []

    def test_single_ranking_preserves_order(self):
        ids = _ids(3)
        result = rrf_fuse([ids])
        assert result == ids

    def test_identical_rankings_preserve_order(self):
        ids = _ids(4)
        result = rrf_fuse([ids, ids])
        assert result == ids

    def test_item_in_both_lists_outranks_item_in_one(self):
        a, b, c = _ids(3)
        # a is rank 1 in list 0; b is rank 1 in list 1; c is rank 2 in list 0 only
        # a: 1/(60+1) + 1/(60+2) ≈ 0.0164 + 0.0161 = 0.0325 (wait, a only appears once)
        # Actually: a=rank1 list0, b=rank1 list1, c=rank2 list0
        # a score = 1/61 ≈ 0.01639
        # b score = 1/61 ≈ 0.01639
        # c score = 1/62 ≈ 0.01613
        # a and b tie; c is last
        # Let a appear in both lists at rank 1 and 2 respectively → higher combined score
        result = rrf_fuse([[a, c], [a, b]])
        # a: 1/61 + 1/61 = 2/61 ≈ 0.0328; b: 1/62 ≈ 0.0161; c: 1/62 ≈ 0.0161
        assert result[0] == a

    def test_disjoint_lists_interleave_by_rank(self):
        a, b, c, d = _ids(4)
        # list0: [a, b], list1: [c, d]
        # scores: a=1/61, b=1/62, c=1/61, d=1/62
        # a and c tie at 1/61, b and d tie at 1/62
        result = rrf_fuse([[a, b], [c, d]])
        assert set(result[:2]) == {a, c}
        assert set(result[2:]) == {b, d}

    def test_k_parameter_affects_weighting(self):
        a, b = _ids(2)
        # With small k, rank differences matter more
        # a is rank1 in list0, rank1 in list1 → combined score
        # b is rank1 in list0 only
        result_low_k = rrf_fuse([[a, b], [a]], k=1)
        result_high_k = rrf_fuse([[a, b], [a]], k=10000)
        # a should still beat b in both cases since it appears twice
        assert result_low_k[0] == a
        assert result_high_k[0] == a

    def test_k_default_60(self):
        ids = _ids(2)
        result_default = rrf_fuse([ids])
        result_explicit = rrf_fuse([ids], k=60)
        assert result_default == result_explicit

    def test_multiple_rankings_accumulate_scores(self):
        a, b = _ids(2)
        # a appears at rank 1 in three lists; b appears at rank 1 in one list
        result = rrf_fuse([[a], [a], [a], [b]])
        assert result[0] == a


class TestRrfFuseScored:
    def test_empty_inputs_return_empty(self):
        assert rrf_fuse_scored([]) == []

    def test_scores_are_returned_in_descending_order(self):
        a, b, c = _ids(3)
        scored = rrf_fuse_scored([[a, b, c]])
        assert [doc_id for doc_id, _ in scored] == [a, b, c]
        scores = [score for _, score in scored]
        assert scores == sorted(scores, reverse=True)

    def test_score_matches_the_reciprocal_rank_formula(self):
        (a,) = _ids(1)
        [(_, score)] = rrf_fuse_scored([[a]])
        assert score == 1.0 / (DEFAULT_RRF_K + 1)

    def test_appearing_in_two_rankings_sums_both_contributions(self):
        a, b = _ids(2)
        scored = dict(rrf_fuse_scored([[a, b], [a]]))
        assert scored[a] == 1.0 / (DEFAULT_RRF_K + 1) * 2
        assert scored[b] == 1.0 / (DEFAULT_RRF_K + 2)

    def test_arbitrarily_many_rankings_fuse(self):
        """Query expansion relies on this: each variant is one more ranking."""
        a, b = _ids(2)
        scored = dict(rrf_fuse_scored([[a], [a], [a], [a], [b]]))
        assert scored[a] == 1.0 / (DEFAULT_RRF_K + 1) * 4
        assert scored[a] > scored[b]

    def test_rrf_fuse_returns_the_same_order_without_scores(self):
        a, b, c = _ids(3)
        rankings = [[a, c], [a, b]]
        assert rrf_fuse(rankings) == [doc_id for doc_id, _ in rrf_fuse_scored(rankings)]
