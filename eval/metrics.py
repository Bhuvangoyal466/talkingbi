"""
Evaluation metrics helpers for TalkingBI.
"""
from __future__ import annotations

import re
from typing import List


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokenizer."""
    return re.findall(r"\b\w+\b", text.lower())


def token_overlap_f1(prediction: str, reference: str) -> dict:
    """
    Compute token-level F1, Precision, and Recall between prediction and reference
    (similar to ROUGE-1 unigram matching).
    """
    pred_tokens = _tokenize(prediction)
    ref_tokens = _tokenize(reference)

    if not pred_tokens or not ref_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    pred_set = set(pred_tokens)
    ref_set = set(ref_tokens)
    common = pred_set & ref_set

    precision = len(common) / len(pred_set)
    recall = len(common) / len(ref_set)
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def novelty_score(insight: str, references: List[str]) -> float:
    """
    Estimate novelty as 1 - max(token_overlap_f1) across all references.
    A higher score means the insight is more novel.
    """
    if not references:
        return 1.0
    max_f1 = max(token_overlap_f1(insight, ref)["f1"] for ref in references)
    return round(1.0 - max_f1, 4)


def accuracy_at_k(results: List[bool], k: int) -> float:
    """Accuracy@K: fraction of correct predictions in the first k results."""
    if not results:
        return 0.0
    subset = results[:k]
    return sum(subset) / len(subset)


def mean_reciprocal_rank(ranked_correct: List[bool]) -> float:
    """MRR: 1/rank of the first correct result, 0 if none."""
    for rank, correct in enumerate(ranked_correct, start=1):
        if correct:
            return 1.0 / rank
    return 0.0
