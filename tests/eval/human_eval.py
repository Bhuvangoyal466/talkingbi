"""
Human evaluation stub for TalkingBI.

Provides a CLI-based interface for annotators to rate AI responses
on a 1-5 Likert scale across multiple dimensions.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class HumanEvalRating:
    case_id: str
    question: str
    response: str
    relevance: Optional[int] = None       # 1-5
    accuracy: Optional[int] = None        # 1-5
    clarity: Optional[int] = None         # 1-5
    helpfulness: Optional[int] = None     # 1-5
    notes: str = ""


@dataclass
class HumanEvalSession:
    annotator_id: str
    ratings: List[HumanEvalRating] = field(default_factory=list)

    def add(self, rating: HumanEvalRating):
        self.ratings.append(rating)

    def save(self, output_path: str):
        """Save ratings to a JSON file."""
        data = {
            "annotator_id": self.annotator_id,
            "ratings": [asdict(r) for r in self.ratings],
        }
        Path(output_path).write_text(json.dumps(data, indent=2))
        print(f"Saved {len(self.ratings)} ratings to {output_path}")

    def aggregate(self) -> dict:
        """Compute mean scores across all ratings."""
        dims = ["relevance", "accuracy", "clarity", "helpfulness"]
        agg = {}
        for dim in dims:
            vals = [getattr(r, dim) for r in self.ratings if getattr(r, dim) is not None]
            agg[dim] = round(sum(vals) / len(vals), 2) if vals else None
        return agg


def run_cli_eval(cases: List[dict], annotator_id: str, output_path: str):
    """
    Run an interactive CLI rating session.

    Parameters
    ----------
    cases : list of dicts with keys: case_id, question, response
    annotator_id : str
    output_path : str  path to save JSON output
    """
    session = HumanEvalSession(annotator_id=annotator_id)
    print(f"\n=== TalkingBI Human Evaluation ===")
    print(f"Annotator: {annotator_id}")
    print(f"Cases: {len(cases)}\n")

    for case in cases:
        print(f"\n--- Case: {case['case_id']} ---")
        print(f"Question: {case['question']}")
        print(f"Response:\n{case['response']}\n")

        rating = HumanEvalRating(
            case_id=case["case_id"],
            question=case["question"],
            response=case["response"],
        )

        for dim in ["relevance", "accuracy", "clarity", "helpfulness"]:
            while True:
                try:
                    val = int(input(f"  {dim.title()} (1-5): ").strip())
                    if 1 <= val <= 5:
                        setattr(rating, dim, val)
                        break
                    print("  Please enter a value between 1 and 5.")
                except ValueError:
                    print("  Invalid input. Please enter a number.")

        rating.notes = input("  Notes (optional): ").strip()
        session.add(rating)

    session.save(output_path)
    print("\nAggregated scores:", session.aggregate())


if __name__ == "__main__":
    import sys
    annotator = sys.argv[1] if len(sys.argv) > 1 else "annotator_01"
    out = sys.argv[2] if len(sys.argv) > 2 else "data/cache/human_eval.json"
    # Example stub cases
    stub_cases = [
        {
            "case_id": "test_01",
            "question": "What is the total revenue?",
            "response": "The total revenue across all products is $6,550.",
        }
    ]
    run_cli_eval(stub_cases, annotator, out)
