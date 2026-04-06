"""
Unit tests for evaluation metrics.
"""
import pytest
from eval.metrics import (
    token_overlap_f1,
    novelty_score,
    accuracy_at_k,
    mean_reciprocal_rank,
)


class TestTokenOverlapF1:
    def test_identical_strings(self):
        s = token_overlap_f1("the cat sat on the mat", "the cat sat on the mat")
        assert s["f1"] == pytest.approx(1.0)

    def test_no_overlap(self):
        s = token_overlap_f1("apple banana cherry", "dog elephant frog")
        assert s["f1"] == pytest.approx(0.0)

    def test_partial_overlap(self):
        s = token_overlap_f1("revenue is high for Widget A", "Widget A has high revenue")
        assert 0 < s["f1"] < 1.0

    def test_empty_prediction(self):
        s = token_overlap_f1("", "reference text here")
        assert s["f1"] == 0.0


class TestNoveltyScore:
    def test_no_references_is_fully_novel(self):
        assert novelty_score("some insight", []) == 1.0

    def test_duplicate_is_not_novel(self):
        text = "Widget A has the highest total revenue"
        score = novelty_score(text, [text])
        assert score == pytest.approx(0.0)


class TestAccuracyAtK:
    def test_all_correct(self):
        assert accuracy_at_k([True, True, True], k=3) == pytest.approx(1.0)

    def test_none_correct(self):
        assert accuracy_at_k([False, False, False], k=3) == pytest.approx(0.0)

    def test_k_less_than_length(self):
        assert accuracy_at_k([True, False, True], k=2) == pytest.approx(0.5)


class TestMeanReciprocalRank:
    def test_first_correct(self):
        assert mean_reciprocal_rank([True, False, False]) == pytest.approx(1.0)

    def test_second_correct(self):
        assert mean_reciprocal_rank([False, True, False]) == pytest.approx(0.5)

    def test_none_correct(self):
        assert mean_reciprocal_rank([False, False, False]) == pytest.approx(0.0)
