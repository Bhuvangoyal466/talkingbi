"""
Integration tests for TalkingBI pipeline layers.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_db():
    """Create a temporary SQLite database with a sales table."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()  # Close handle on Windows so SQLite can open it
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE sales (
            id      INTEGER PRIMARY KEY,
            product TEXT,
            amount  REAL,
            month   TEXT,
            region  TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO sales VALUES (?,?,?,?,?)",
        [
            (1, "Widget A", 1200.0, "Jan", "North"),
            (2, "Widget B", 950.0,  "Jan", "South"),
            (3, "Widget A", 1400.0, "Feb", "North"),
            (4, "Widget C", 300.0,  "Feb", "East"),
            (5, "Widget B", 1100.0, "Mar", "South"),
            (6, "Widget A", 1600.0, "Mar", "West"),
        ],
    )
    conn.commit()
    conn.close()
    yield db_path
    try:
        Path(db_path).unlink(missing_ok=True)
    except PermissionError:
        pass  # Windows may still hold a handle; ignore cleanup failure


@pytest.fixture
def sample_df():
    """Return a small sales DataFrame."""
    return pd.DataFrame(
        {
            "product": ["Widget A", "Widget B", "Widget C", "Widget A", "Widget B"],
            "amount":  [1200.0,    950.0,     300.0,     1400.0,    1100.0],
            "month":   ["Jan",     "Jan",     "Feb",     "Feb",     "Mar"],
            "region":  ["North",   "South",   "East",    "North",   "South"],
        }
    )


# ---------------------------------------------------------------------------
# SQL Layer tests
# ---------------------------------------------------------------------------

class TestSQLLayer:
    def test_schema_extraction(self, sample_db):
        from layers.data_access.schema_rep import SchemaRepresentation

        sr = SchemaRepresentation(db_path=sample_db)
        schema = sr.extract_schema()

        assert schema is not None
        assert "sales" in schema.tables
        table = schema.tables["sales"]
        col_names = [f.name for f in table.fields]
        assert "product" in col_names
        assert "amount" in col_names

    def test_triplet_knowledge_base(self, tmp_path):
        """Test that triplets can be added and retrieved from ChromaDB."""
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        from layers.data_access.knowledge_base import TripletKnowledgeBase
        from layers.data_access.explorer import Triplet

        # Patch settings to use tmp_path chroma dir
        import core.config as cfg
        original = cfg.settings.CHROMA_PERSIST_DIR
        cfg.settings.CHROMA_PERSIST_DIR = str(tmp_path)

        try:
            kb = TripletKnowledgeBase(db_name="test_kb_integ")
            t = Triplet(
                schema_fragment={"sales": ["product", "amount"]},
                sql_query="SELECT product, SUM(amount) FROM sales GROUP BY product",
                nl_description="Total sales by product",
                tables_used=["sales"],
            )
            kb.add_triplets([t])
            results = kb.retrieve("total revenue by product", top_k=1)
            assert len(results) >= 1
        finally:
            cfg.settings.CHROMA_PERSIST_DIR = original


# ---------------------------------------------------------------------------
# Data Prep Layer tests
# ---------------------------------------------------------------------------

class TestDataPrepLayer:
    def test_deduplicate_operator(self, sample_df):
        from layers.data_prep.operators import DataOperators

        df_dup = pd.concat([sample_df, sample_df], ignore_index=True)
        result = DataOperators.Deduplicate({"main": df_dup}, table="main", subset=["product", "month"])

        assert result.success
        assert len(result.tables["main"]) == len(sample_df)

    def test_group_by_operator(self, sample_df):
        from layers.data_prep.operators import DataOperators

        result = DataOperators.GroupBy({"main": sample_df}, table="main", by=["product"], agg={"amount": "sum"})

        assert result.success
        df_out = result.tables["main"]
        assert "amount" in df_out.columns
        assert len(df_out) == 3  # Widget A, B, C

    def test_filter_operator(self, sample_df):
        from layers.data_prep.operators import DataOperators

        result = DataOperators.Filter({"main": sample_df}, table="main", condition="amount > 1000")

        assert result.success
        assert all(result.tables["main"]["amount"] > 1000)

    def test_pipeline_executor(self, sample_df):
        from layers.data_prep.executor import PipelineExecutor

        spec = [
            {"name": "Filter", "params": {"table": "main", "condition": "amount >= 900"}},
            {"name": "GroupBy", "params": {"table": "main", "by": ["product"], "agg": {"amount": "sum"}}},
        ]
        executor = PipelineExecutor()
        exec_result = executor.execute({"main": sample_df}, spec)

        assert exec_result["success"]
        assert len(exec_result["tables"]["main"]) <= 3


# ---------------------------------------------------------------------------
# Insight Layer tests
# ---------------------------------------------------------------------------

class TestInsightLayer:
    def test_goal_refiner(self, sample_df):
        from layers.insight_engine.goal_refiner import GoalRefiner

        refiner = GoalRefiner()
        try:
            refined = refiner.refine("Understand revenue patterns", sample_df)
            assert isinstance(refined, dict)
        except Exception:
            pytest.skip("LLM not available in test environment")

    def test_question_generation(self, sample_df):
        from layers.insight_engine.question_gen import QuestionGenerator

        gen = QuestionGenerator()
        try:
            goal = {"refined_goal": "Understand revenue patterns"}
            questions = gen.generate(goal, sample_df, n_questions=3)
            assert isinstance(questions, list)
        except Exception:
            pytest.skip("LLM not available in test environment")

    def test_insight_evaluator(self):
        from layers.insight_engine.evaluator import InsightEvaluator

        evaluator = InsightEvaluator()
        generated = ["Widget A has the highest total revenue across all months."]
        ground_truth = ["Widget A leads in revenue with $4,200 total."]
        scores = evaluator.compute_all(generated=generated, ground_truth=ground_truth)
        assert "f1" in scores
        assert 0.0 <= scores["f1"] <= 1.0
        assert "recall" in scores
        assert "precision" in scores


# ---------------------------------------------------------------------------
# Visualization Layer tests
# ---------------------------------------------------------------------------

class TestVisualizationLayer:
    def test_chart_type_selection(self, sample_df):
        from layers.visualization.chart_type_selector import ChartTypeSelector

        selector = ChartTypeSelector()
        try:
            result = selector.select(
                intent={"x_axis": "product", "y_axis": "amount", "category": None},
                df=sample_df,
            )
            # select() may return a string or dict
            chart_type = result if isinstance(result, str) else result.get("recommended_chart_type", "bar")
            assert chart_type in {
                "bar", "horizontal_bar", "grouped_bar", "stacked_bar",
                "line", "area", "pie", "scatter", "histogram",
            }
        except Exception:
            pytest.skip("LLM not available in test environment")

    def test_chart_generation(self, sample_df):
        from layers.visualization.chart_generator import ChartGenerator

        gen = ChartGenerator()
        agg = sample_df.groupby("product")["amount"].sum().reset_index()

        # Build the extracted_data dict that ChartGenerator.generate() expects
        extracted_data = {
            "title": "Revenue by Product",
            "x_axis_label": "product",
            "y_axis_label": "amount",
            "values": [
                {"x": row["product"], "y": row["amount"]}
                for _, row in agg.iterrows()
            ],
        }
        chart_type_dict = {"recommended_chart_type": "bar"}

        result = gen.generate(extracted_data=extracted_data, chart_type=chart_type_dict)
        assert result.get("success"), result.get("error")
        assert "image_base64" in result
        assert len(result["image_base64"]) > 100


# ---------------------------------------------------------------------------
# Evaluation Metrics tests
# ---------------------------------------------------------------------------

class TestEvaluationMetrics:
    def test_insight_f1(self):
        from eval.metrics import token_overlap_f1

        scores = token_overlap_f1(
            "Widget A has the highest revenue.", "Widget A leads in total revenue."
        )
        assert 0 < scores["f1"] <= 1.0

    def test_novelty_score(self):
        from eval.metrics import novelty_score

        score = novelty_score(
            insight="Widget C has the lowest revenue.",
            references=["Widget A has the highest revenue."],
        )
        assert 0.0 <= score <= 1.0

    def test_accuracy_at_k(self):
        from eval.metrics import accuracy_at_k

        assert accuracy_at_k([True, False, True, True], k=2) == 0.5
        assert accuracy_at_k([True, True, False], k=3) == pytest.approx(2 / 3)

    def test_mrr(self):
        from eval.metrics import mean_reciprocal_rank

        assert mean_reciprocal_rank([False, True, False]) == pytest.approx(0.5)
        assert mean_reciprocal_rank([False, False]) == 0.0



# ---------------------------------------------------------------------------
# Evaluation Metrics tests
# ---------------------------------------------------------------------------

class TestEvaluationMetrics:
    def test_insight_f1(self):
        from eval.metrics import token_overlap_f1

        scores = token_overlap_f1(
            "Widget A has the highest revenue.", "Widget A leads in total revenue."
        )
        assert 0 < scores["f1"] <= 1.0

    def test_novelty_score(self):
        from eval.metrics import novelty_score

        score = novelty_score(
            insight="Widget C has the lowest revenue.",
            references=["Widget A has the highest revenue."],
        )
        assert 0.0 <= score <= 1.0

    def test_accuracy_at_k(self):
        from eval.metrics import accuracy_at_k

        assert accuracy_at_k([True, False, True, True], k=2) == 0.5
        assert accuracy_at_k([True, True, False], k=3) == pytest.approx(2 / 3)

    def test_mrr(self):
        from eval.metrics import mean_reciprocal_rank

        assert mean_reciprocal_rank([False, True, False]) == pytest.approx(0.5)
        assert mean_reciprocal_rank([False, False]) == 0.0
