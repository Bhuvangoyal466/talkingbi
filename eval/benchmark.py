"""
TalkingBI benchmark runner (Phase 10 of structuredplan.md).

Runs a suite of test cases through the full pipeline and reports
aggregate metrics: SQL accuracy, data-prep success rate, insight F1,
chart eval score.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from core.logger import logger


@dataclass
class BenchmarkCase:
    case_id: str
    question: str
    expected_sql: Optional[str] = None
    expected_insight_keywords: List[str] = field(default_factory=list)
    db_path: Optional[str] = None


@dataclass
class BenchmarkResult:
    case_id: str
    sql_match: Optional[bool] = None
    insight_f1: Optional[float] = None
    chart_score: Optional[float] = None
    error: Optional[str] = None


class TalkingBIBenchmark:
    """
    Automated benchmark runner for TalkingBI.

    Usage
    -----
    bench = TalkingBIBenchmark(cases)
    results = bench.run(pipeline)
    bench.report(results)
    """

    def __init__(self, cases: List[BenchmarkCase]):
        self.cases = cases

    def run(self, pipeline) -> List[BenchmarkResult]:
        """
        Run all benchmark cases through the provided pipeline instance.

        Parameters
        ----------
        pipeline : TalkingBIPipeline
            Instantiated pipeline with a loaded data source.
        """
        results = []
        for case in self.cases:
            logger.info(f"[Benchmark] Running case: {case.case_id}")
            result = BenchmarkResult(case_id=case.case_id)
            try:
                response = pipeline.run(case.question)
                # SQL match check
                if case.expected_sql and "sql" in response:
                    from eval.metrics import token_overlap_f1
                    scores = token_overlap_f1(response["sql"], case.expected_sql)
                    result.sql_match = scores["f1"] >= 0.7

                # Insight keyword check
                if case.expected_insight_keywords and "insight" in response:
                    from eval.metrics import token_overlap_f1
                    combined_keywords = " ".join(case.expected_insight_keywords)
                    scores = token_overlap_f1(response.get("insight", ""), combined_keywords)
                    result.insight_f1 = scores["f1"]

                # Chart score
                if "chart_eval" in response:
                    eval_scores = response["chart_eval"]
                    result.chart_score = eval_scores.get("visual_score", 0.0)

            except Exception as e:
                result.error = str(e)
                logger.error(f"[Benchmark] Error in case {case.case_id}: {e}")

            results.append(result)
        return results

    def report(self, results: List[BenchmarkResult]) -> Dict[str, Any]:
        """Compute aggregate benchmark statistics."""
        total = len(results)
        errors = [r for r in results if r.error]
        sql_results = [r.sql_match for r in results if r.sql_match is not None]
        f1_results = [r.insight_f1 for r in results if r.insight_f1 is not None]
        chart_results = [r.chart_score for r in results if r.chart_score is not None]

        summary = {
            "total_cases": total,
            "error_count": len(errors),
            "sql_accuracy": sum(sql_results) / len(sql_results) if sql_results else None,
            "avg_insight_f1": sum(f1_results) / len(f1_results) if f1_results else None,
            "avg_chart_score": sum(chart_results) / len(chart_results) if chart_results else None,
        }

        logger.info(f"[Benchmark] Report: {json.dumps(summary, indent=2)}")
        return summary


# ---------------------------------------------------------------------------
# Quick smoke-test fixture
# ---------------------------------------------------------------------------

def _build_smoke_db() -> str:
    """Create a temporary SQLite DB with a sales table for smoke testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    conn = sqlite3.connect(tmp.name)
    conn.execute(
        "CREATE TABLE sales (id INTEGER PRIMARY KEY, product TEXT, amount REAL, month TEXT)"
    )
    conn.executemany(
        "INSERT INTO sales VALUES (?,?,?,?)",
        [
            (1, "Widget A", 1200.0, "Jan"),
            (2, "Widget B", 950.0, "Jan"),
            (3, "Widget A", 1400.0, "Feb"),
            (4, "Widget C", 300.0, "Feb"),
            (5, "Widget B", 1100.0, "Mar"),
            (6, "Widget A", 1600.0, "Mar"),
        ],
    )
    conn.commit()
    conn.close()
    return tmp.name


SMOKE_CASES = [
    BenchmarkCase(
        case_id="smoke_01",
        question="What is the total sales amount by product?",
        expected_sql="SELECT product, SUM(amount) FROM sales GROUP BY product",
        expected_insight_keywords=["Widget A", "highest", "total"],
    ),
    BenchmarkCase(
        case_id="smoke_02",
        question="Show me a bar chart of monthly revenue.",
        expected_insight_keywords=["Jan", "Feb", "Mar"],
    ),
]
